"""Check exact pair cache, text/token provenance and actual forward receipts; no new model calls."""
from pathlib import Path
import json,hashlib,re,collections
R=Path(__file__).resolve().parents[1]
def jb(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(x):return hashlib.sha256(x).hexdigest()
def jl(p):return [json.loads(v) for v in (R/p).read_text(encoding='utf-8-sig').splitlines() if v]
def read(p):return json.loads((R/p).read_text(encoding='utf-8-sig'))
lock=read('CONTROL_LOCK.json');request={v['request_id']:v for v in jl('private/request_map.jsonl')};diagnostics={(v['model_key'],v['item_id']):v for v in jl('data/eval_tokenizer_diagnostics.jsonl')}
checks={};totalcached=0
for key in ['bm25','bge_small','e5_small','minilm_ce']:
 raw=jl(f'scoring/raw_{key}.jsonl');forward=read(f'scoring/forward_audit_{key}.json');seen={};cached=0
 for row in raw:
  pairkey=row['cache_key_sha256'];source=seen.get(pairkey)
  if source:
   assert source['request_id']==row['cache_source_request_id'] and source['candidate_display_index']==row['cache_source_candidate_display_index']
   for field in ['query_text','candidate_text','raw_score','configuration_sha256','tokenizer_input_sha256','query_token_length','document_or_pair_token_length']:assert source[field]==row[field]
   assert row['execution_mode']=='reused_from_exact_pair_cache';cached+=1
  else:
   assert row['cache_source_request_id'] is None;seen[pairkey]=row
  contract=lock['models'][key]['model_contract'];qp=contract.get('query_prefix','');dp=contract.get('document_prefix','')
  assert row['encoder_input_sha256']==digest(jb({'query':qp+row['query_text'],'document':dp+row['candidate_text']}))
  assert pairkey==digest(jb({'configuration_sha256':row['configuration_sha256'],'query':row['query_text'],'document':row['candidate_text']}))
  if key=='bm25':
   term=lambda s:re.findall(r'\d+(?:\.\d+)?|[A-Za-z]+',s.lower())
   assert row['tokenizer_input_sha256']==digest(jb({'query_terms':term(row['query_text']),'document_terms':term(row['candidate_text'])}))
   assert row['query_token_length']==len(term(row['query_text'])) and row['document_or_pair_token_length']==len(term(row['candidate_text']))
  else:
   diag=diagnostics[(key,request[row['request_id']]['item_id'])];doc=next(v for v in diag['candidate_diagnostics'] if v['candidate_text_sha256']==row['candidate_text_sha256'])
   if key=='minilm_ce':
    assert row['pair_token_sha256']==doc['pair_token_hash']==row['tokenizer_input_sha256']
    assert row['document_or_pair_token_length']==doc['pair_token_length']
    sources=[('pair_forward_source','pair_token_sha256')]
   else:
    assert row['query_token_sha256']==diag['query_token_hash'] and row['document_token_sha256']==doc['token_hash']
    assert row['tokenizer_input_sha256']==digest(jb([diag['query_token_hash'],doc['token_hash']]))
    assert row['query_token_length']==diag['query_token_length'] and row['document_or_pair_token_length']==doc['token_length']
    sources=[('query_forward_source','query_token_sha256'),('document_forward_source','document_token_sha256')]
   for sourcefield,hashfield in sources:
    s=row[sourcefield];assert s['unpadded_input_ids_sha256']==row[hashfield]
    b=forward['forward_batches'][s['batch_id']];assert b['batch_id']==s['batch_id'] and s['batch_row']<b['sequences'] and s['nonpadding_tokens']<=b['padded_width']<=512
 for mode in ['precheck','score']:
  receipt=read(f'scoring/resources_{mode}_{key}.json');assert receipt['status']=='COMPLETE' and receipt['process_RAM_fraction']<=.6
  if 'total_cuda_bytes' in receipt:assert max(receipt['max_cuda_allocated_bytes'],receipt['max_cuda_reserved_bytes'],receipt['max_total_cuda_used_bytes'])<=.8*receipt['total_cuda_bytes']
 assert len(seen)==144 and cached==144
 checks[key]={'candidate_score_rows':len(raw),'distinct_query_document_pairs':len(seen),'exact_cache_reuses':cached,'actual_target_forward_calls':forward['actual_model_forward_calls'],'actual_target_sequence_occurrences':forward['actual_model_sequence_occurrences'],'text_token_source_checks':'PASS','resource_checks':'PASS'};totalcached+=cached
receipt={'status':'PASS','models':checks,'cached_score_occurrences':totalcached,'new_model_calls':0,'paid_API_calls':0}
if (R/'analysis/provenance_replay.json').exists():assert read('analysis/provenance_replay.json')==receipt
else:
 with (R/'analysis/provenance_replay.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
print(json.dumps(checks))
