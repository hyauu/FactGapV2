"""Actual tokenizer diagnostics only; no model weights or score computations."""
from pathlib import Path
import json,re,hashlib,os,sys,importlib.util
R=Path(__file__).resolve().parents[1];ROOT=R.parents[2]
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HOME=str(R/'cache/hf'),TEMP=str(R/'cache'),TMP=str(R/'cache'))
from transformers import AutoTokenizer
KEYS=['bge_small','e5_small','minilm_ce']
lock=json.loads((ROOT/'source_and_model_locks/model_local_lock.json').read_text(encoding='utf-8'))
def jb(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def jl(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x]
def prefix(k,s,q):return ('Represent this sentence for searching relevant passages: ' if k=='bge_small' and q else 'query: ' if k=='e5_small' and q else 'passage: ' if k=='e5_small' else '')+s
def numeric(tok,s):
 enc=tok(s,add_special_tokens=True,truncation=False,return_offsets_mapping=True)
 spans=[(m.start(),m.end(),m.group()) for m in re.finditer(r'\d+',s)]
 out=[]
 for tid,(a,b) in zip(enc['input_ids'],enc['offset_mapping']):
  linked=[i for i,(x,y,t) in enumerate(spans) if a<y and b>x]
  if linked:out.append({'token_id':tid,'piece':tok.convert_ids_to_tokens(tid),'start':a,'end':b,'numeral_span_indices':linked})
 return enc,out
split=sys.argv[1];pub=jl(R/f'data/{split}_queries.jsonl');private={x['item_id']:x for x in jl(R/f'private/{split}_map.jsonl')};allout=[]
for k in KEYS:
 tok=AutoTokenizer.from_pretrained(lock['models'][k]['snapshot_path'],local_files_only=True,trust_remote_code=False)
 for p in pub:
  qs=prefix(k,p['query'],True);qe,qn=numeric(tok,qs);docs=[]
  for d in p['candidates']:
   ds=prefix(k,d,False);de,dn=numeric(tok,ds)
   pe=tok(p['query'],d,truncation=False) if k=='minilm_ce' else None
   lengths=[len(qe['input_ids']),len(de['input_ids'])]+([len(pe['input_ids'])] if pe else [])
   assert max(lengths)<=512
   value=re.findall(r'\d+',d)[0];numerals=re.findall(r'\d+',p['query'])
   substrings=sorted({value[a:b] for a in range(len(value)) for b in range(a+1,len(value)+1) if any(value[a:b] in z for z in numerals)},key=lambda x:(len(x),x))
   docs.append({'candidate_text_sha256':hashlib.sha256(d.encode()).hexdigest(),'token_length':len(de['input_ids']),'numeric_tokens':dn,'shared_numeric_token_ids':sorted({x['token_id'] for x in qn}&{x['token_id'] for x in dn}),'shared_digit_substrings':substrings,'complete_numeral_match_count':numerals.count(value),'pair_token_length':len(pe['input_ids']) if pe else None,'token_hash':hashlib.sha256(jb(de['input_ids'])).hexdigest(),'pair_token_hash':hashlib.sha256(jb(pe['input_ids'])).hexdigest() if pe else None})
  allout.append({'model_key':k,'item_id':p['item_id'],'query_token_length':len(qe['input_ids']),'query_numeric_tokens':qn,'query_token_hash':hashlib.sha256(jb(qe['input_ids'])).hexdigest(),'candidate_diagnostics':docs,'truncation':False})
with (R/f'data/{split}_tokenizer_diagnostics.jsonl').open('x',encoding='utf-8') as f:
 for x in allout:f.write(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n')
summary={}
for k in KEYS:
 rr=[x for x in allout if x['model_key']==k];groups={}
 for x in rr:
  p=private[x['item_id']];groups.setdefault((p['block_id'],p['wording']),[]).append(x['query_token_length'])
 summary[k]={'queries':len(rr),'min_query_tokens':min(x['query_token_length'] for x in rr),'max_query_tokens':max(x['query_token_length'] for x in rr),'block_wording_groups_with_condition_length_difference':sum(len(set(v))>1 for v in groups.values()),'largest_condition_token_length_range':max(max(v)-min(v) for v in groups.values()),'max_candidate_or_pair_tokens':max(d['pair_token_length'] or d['token_length'] for x in rr for d in x['candidate_diagnostics']),'numeric_subword_overlaps_retained':True}
with (R/f'data/{split}_tokenizer_summary.json').open('x',encoding='utf-8') as f:json.dump({'status':'PASS_NO_TRUNCATION','model_weight_loads':0,'model_forward_calls':0,'diagnostics':summary},f,indent=2)
print(json.dumps(summary))
