"""Offline Stage22 transport reusing immutable validated baseline functions."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(r'<LOCAL_PROJECT>');S=Path(__file__).resolve().parents[1]
os.environ.update(PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',HF_HOME=str(ROOT/'model_cache'),TOKENIZERS_PARALLELISM='false')
sys.path.insert(0,str(ROOT/'src'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,x):
 if p.exists():raise FileExistsError(p)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.now(timezone.utc).isoformat()
def adapter():
 p=ROOT/'tools/local_score.py';pre=read(ROOT/'source_and_model_locks/ADAPTER_PREFLIGHT_LOCK.json')
 if pre['status']!='PASS' or sha(p)!=pre['code_sha256']:raise RuntimeError('Inherited adapter changed')
 spec=importlib.util.spec_from_file_location('locked_local_adapter',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def verify_lock():
 lock=read(S/'CONTROL_SCORE_LOCK.json')
 if lock['status']!='LOCKED_BEFORE_TARGET_SCORING':raise RuntimeError('No prospective score lock')
 for row in lock['file_locks']:
  p=S/row['path']
  if sha(p)!=row['sha256']:raise RuntimeError('Changed locked file '+row['path'])
 return lock

def score(key):
 lock=verify_lock();m=adapter();folder=S/'data/EVAL';payloads=m.readj(folder/'model_inputs.jsonl');corpus=[x['text'] for x in m.readj(folder/'score_visible_corpus.jsonl')]
 for p in payloads:
  if set(p)!={'query','candidates'} or len(p['candidates'])!=2 or not all(isinstance(d,str) for d in p['candidates']):raise RuntimeError('Visible allowlist mismatch')
 pairs=sorted({(p['query'],d) for p in payloads for d in p['candidates']});outdir=S/'scoring';out=outdir/f'raw_{key}.jsonl';mp=outdir/f'manifest_{key}.json'
 if out.exists() or mp.exists():raise FileExistsError('No target result overwrite')
 start=time.perf_counter()
 if key=='bm25':scored=m.bm25_scores(pairs,corpus);device='cpu';revision='deterministic_bm25_v1';dtype='float64';scale='bm25';peak=0
 else:
  tok,model,device,entry=m.load_neural(key);scored=m.neural_scores(key,pairs,tok,model,device);revision=entry['revision'];dtype='float32';scale='raw_logit' if key=='minilm_ce' else 'cosine_unscaled' if key=='e5_small' else 'cosine'
  import torch
  peak=int(torch.cuda.max_memory_allocated(0)) if device=='cuda' else 0
  if device=='cuda' and peak>torch.cuda.get_device_properties(0).total_memory*.8:raise RuntimeError('GPU cap')
 elapsed=(time.perf_counter()-start)*1000
 if set(scored)!=set(pairs) or any(not math.isfinite(x[0]) for x in scored.values()):raise RuntimeError('Missing/nonfinite')
 from factgap_followup.boundary import payload_hash
 rows=[];seen={}
 for ordinal,p in enumerate(payloads):
  rid=f'control-eval-{key}-{ordinal:06d}'
  for pos,d in enumerate(p['candidates']):
   pair=(p['query'],d);value,th,qlen,dlen=scored[pair];cached=seen.get(pair)
   rows.append({'run_id':'stage22b_control_eval_v001_local4','dataset_version':'stage22b-control-eval-v001','split':'control_eval','model_key':key,'model_revision':revision,'request_ordinal':ordinal,'request_id':rid,'payload_sha256':payload_hash(p),'orientation':ordinal%2,'candidate_display_index':pos,'candidate_text_sha256':m.sha(d.encode()),'query_text_sha256':m.sha(p['query'].encode()),'encoder_input_sha256':m.sha((m.prefix(key,p['query'],True)+'\0'+m.prefix(key,d,False)).encode()),'tokenizer_input_sha256':th,'query_token_length':qlen,'document_or_pair_token_length':dlen,'raw_score':value,'score_scale':scale,'dtype':dtype,'elapsed_ms_amortized':elapsed/len(pairs),'execution_mode':'executed_batched' if cached is None else 'reused_from_pair_cache','cache_source_request_id':cached,'status':'OK','technical_error_code':None})
   if cached is None:seen[pair]=rid
 outdir.mkdir(parents=True,exist_ok=True);out.write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows),encoding='utf-8')
 manifest={'created_at_utc':now(),'status':'COMPLETE','model_key':key,'model_revision':revision,'dtype':dtype,'score_scale':scale,'logical_ranking_requests':len(payloads),'score_rows':len(rows),'unique_forward_pairs':len(pairs),'elapsed_ms':elapsed,'peak_gpu_bytes':peak,'device':device,'raw_sha256':sha(out),'input_sha256':sha(folder/'model_inputs.jsonl'),'corpus_sha256':sha(folder/'score_visible_corpus.jsonl'),'adapter_sha256':sha(ROOT/'tools/local_score.py'),'wrapper_sha256':sha(Path(__file__)),'prospective_lock_sha256':sha(S/'CONTROL_SCORE_LOCK.json')};save(mp,manifest);print(json.dumps(manifest))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--model',choices=['bm25','bge_small','e5_small','minilm_ce'],required=True);a=ap.parse_args();score(a.model)
