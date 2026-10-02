"""Tokenizer-only preflight and independent raw token/hash reconstruction."""
import argparse,hashlib,json,os,pathlib,re
ROOT=pathlib.Path(r'<LOCAL_PROJECT>');R=pathlib.Path(__file__).resolve().parent.parent
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',PYTHONDONTWRITEBYTECODE='1',TOKENIZERS_PARALLELISM='false')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def jb(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def h(x):return hashlib.sha256(x).hexdigest()
def main(replay):
 payloads=rows(R/'data/EVAL/model_inputs.jsonl');pairs=sorted({(p['query'],d) for p in payloads for d in p['candidates']})
 lock=read(ROOT/'stage22/STAGE22_STAGE2_REPAIR_SCORE_LOCK.json')['target_models'];report={'status':'PASS','target_forward_calls':0,'silent_truncation':False,'models':{}}
 for key in ['bm25','bge_small','e5_small','minilm_ce']:
  qp=lock[key].get('query_prefix','');dp=lock[key].get('document_prefix','');token_data={};maxlen=0
  if key=='bm25':
   for q,d in pairs:
    qt=re.findall(r'\d+(?:\.\d+)?|[A-Za-z]+',q.lower());dt=re.findall(r'\d+(?:\.\d+)?|[A-Za-z]+',d.lower());token_data[q,d]=(h(jb({'query_terms':qt,'document_terms':dt})),len(qt),len(dt))
    assert all(n in qt for n in re.findall(r'\d+',q)) and all(n in dt for n in re.findall(r'\d+',d))
  else:
   from transformers import AutoTokenizer
   tok=AutoTokenizer.from_pretrained(lock[key]['snapshot_path'],local_files_only=True,trust_remote_code=False)
   for q,d in pairs:
    if key=='minilm_ce':
     ids=tok(q,d,truncation=False)['input_ids'];token_data[q,d]=(h(jb(ids)),len(ids),len(ids));decoded=re.sub(r'\s+','',tok.decode(ids,skip_special_tokens=True))
     assert all(n in decoded for n in re.findall(r'\d+',q+' '+d))
    else:
     qs=qp+q;ds=dp+d
     if qp:assert qs.count(qp)==1
     if dp:assert ds.count(dp)==1
     qi=tok(qs,truncation=False)['input_ids'];di=tok(ds,truncation=False)['input_ids'];token_data[q,d]=(h(jb([h(jb(qi)),h(jb(di))])),len(qi),len(di))
     assert all(n in re.sub(r'\s+','',tok.decode(qi,skip_special_tokens=True)) for n in re.findall(r'\d+',q))
     assert all(n in re.sub(r'\s+','',tok.decode(di,skip_special_tokens=True)) for n in re.findall(r'\d+',d))
  assert max(max(v[1:]) for v in token_data.values())<=512
  info={'unique_pairs':len(pairs),'unique_queries':len({q for q,d in pairs}),'unique_pair_documents':len({d for q,d in pairs}),'max_token_length':max(max(v[1:]) for v in token_data.values()),'all_explicit_numeric_tokens_retained':True,'prefix_contract_once':True}
  if replay:
   raw=rows(R/f'scoring/raw_{key}.jsonl')
   for row in raw:
    p=payloads[row['request_ordinal']];q=p['query'];d=p['candidates'][row['candidate_display_index']];th,qn,dn=token_data[q,d]
    assert row['tokenizer_input_sha256']==th and row['query_token_length']==qn and row['document_or_pair_token_length']==dn
    assert row['encoder_input_sha256']==h((qp+q+'\0'+dp+d).encode()) and row['model_revision']==lock[key]['revision']
   info['verified_raw_rows']=len(raw)
  report['models'][key]=info
 dest=R/('TOKEN_HASH_REPLAY.json' if replay else 'TOKENIZER_PREFLIGHT.json')
 assert not dest.exists();dest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--replay',action='store_true');a=p.parse_args();main(a.replay)