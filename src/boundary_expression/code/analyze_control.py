"""Prospective descriptive analysis; no outcome-based selection."""
from __future__ import annotations
import argparse,collections,csv,hashlib,importlib.util,json,math,statistics
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(r'<LOCAL_PROJECT>');S=Path(__file__).resolve().parents[1];D=S/'data/EVAL';MODELS=['bm25','bge_small','e5_small','minilm_ce']
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def readj(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bytesha(x):return hashlib.sha256(x).hexdigest()
def jbytes(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def write(p,x):
 if p.exists():raise FileExistsError(p)
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def writej(p,rows):
 if p.exists():raise FileExistsError(p)
 p.write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in rows),encoding='utf-8')
def csvout(p,rows):
 if p.exists():raise FileExistsError(p)
 with p.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def mean(xs):return statistics.mean(xs)
def group(rows,keys):
 d=collections.defaultdict(list)
 for r in rows:d[tuple(r[k] for k in keys)].append(r)
 return d

def reconstruct():
 payloads=readj(D/'model_inputs.jsonl');index=readj(D/'private_payload_index.jsonl');blocks={b['block_id']:b for b in readj(D/'blocks.jsonl')};lookup={q['query_id']:(b,q) for b in blocks.values() for q in b['queries']};lock=read(S/'CONTROL_SCORE_LOCK.json')
 if len(payloads)!=len(index):raise RuntimeError('Private payload cardinality mismatch')
 for f in lock['file_locks']:
  if sha(S/f['path'])!=f['sha256']:raise RuntimeError('Lock file changed')
 raw=[];metrics=[];maxorder=0;cache_verified=0
 for model in MODELS:
  rp=S/f'scoring/raw_{model}.jsonl';mp=S/f'scoring/manifest_{model}.json';rows=readj(rp);manifest=read(mp)
  if sha(rp)!=manifest['raw_sha256'] or manifest['prospective_lock_sha256']!=sha(S/'CONTROL_SCORE_LOCK.json'):raise RuntimeError('Run manifest mismatch')
  if len(rows)!=len(payloads)*2:raise RuntimeError('Raw incomplete')
  byreq=collections.defaultdict(list);byq=collections.defaultdict(list);seenpair={};seenrequest={}
  for r in rows:
   if r['status']!='OK' or r['technical_error_code'] is not None or not math.isfinite(r['raw_score']):raise RuntimeError('Technical score error')
   ordinal=r['request_ordinal'];p=payloads[ordinal];ix=index[ordinal];pos=r['candidate_display_index'];doc=p['candidates'][pos]
   if set(p)!={'query','candidates'}:raise RuntimeError('Visible schema')
   ph=bytesha(jbytes(p))
   if r['payload_sha256']!=ph or ix['payload_sha256']!=ph:raise RuntimeError('Payloadhash mismatch')
   if r['query_text_sha256']!=bytesha(p['query'].encode()) or r['candidate_text_sha256']!=bytesha(doc.encode()):raise RuntimeError('Texthash mismatch')
   if len(r['tokenizer_input_sha256'])!=64 or min(r['query_token_length'],r['document_or_pair_token_length'])<=0 or max(r['query_token_length'],r['document_or_pair_token_length'])>512:raise RuntimeError('Token trace mismatch')
   if r['model_revision']!=manifest['model_revision']:raise RuntimeError('Revision mismatch')
   pair=(p['query'],doc);memo=seenpair.get(pair)
   if memo is not None:
    if r['raw_score']!=memo['raw_score'] or r['tokenizer_input_sha256']!=memo['tokenizer_input_sha256']:raise RuntimeError('Cached result mismatch')
    if r['execution_mode']!='reused_from_pair_cache' or r['cache_source_request_id']!=memo['request_id']:raise RuntimeError('Cache provenance mismatch')
    cache_verified+=1
   else:
    if r['execution_mode']!='executed_batched' or r['cache_source_request_id'] is not None:raise RuntimeError('Original provenance mismatch')
    seenpair[pair]=r
   byreq[ordinal].append(r)
  if set(byreq)!=set(range(len(payloads))):raise RuntimeError('Missing requests')
  for ordinal,rr in byreq.items():
   ix=index[ordinal]
   if {x['candidate_display_index'] for x in rr}!={0,1}:raise RuntimeError('Missing positions')
   roles={ix['position_to_role'][r['candidate_display_index']]:r['raw_score'] for r in rr}
   if set(roles)!={'gold','counterpart'}:raise RuntimeError('Role integrity')
   byq[ix['query_id']].append({'margin':roles['gold']-roles['counterpart'],'ordinal':ordinal,'roles':roles})
  if set(byq)!=set(lookup):raise RuntimeError('Query coverage')
  for qid,orientations in byq.items():
   if len(orientations)!=2:raise RuntimeError('Two orders missing')
   ords=[x['ordinal'] for x in orientations];p0,p1=[payloads[o] for o in ords]
   if p0['candidates']!=list(reversed(p1['candidates'])):raise RuntimeError('Order imbalance')
   diff=abs(orientations[0]['margin']-orientations[1]['margin']);maxorder=max(maxorder,diff)
   if diff>1e-4:raise RuntimeError('Order mismatch > tolerance')
   margin=mean([x['margin'] for x in orientations]);b,q=lookup[qid]
   metrics.append({'model_key':model,'block_id':b['block_id'],'query_id':qid,'template_id':b['template_id'],'instance':b.get('instance',b.get('numeric_instance',b.get('construction',{}).get('instance',0))),'condition':q['condition'],'wording':q['wording'],'margin':margin,'strict_success':int(margin>0),'exact_tie':int(margin==0),'near_tie_1e6':int(abs(margin)<=1e-6),'near_tie_1e5':int(abs(margin)<=1e-5),'orientation_margin_difference':diff,'technical_failure':0})
  raw.extend(rows)
 return raw,metrics,{'status':'PASS','queries':len(lookup),'model_query_results':len(metrics),'logical_requests':len(payloads)*len(MODELS),'raw_score_rows':len(raw),'cached_rows_independently_joined':cache_verified,'all_payload_text_revision_and_cache_hashes_verified':True,'maximum_order_margin_difference':maxorder,'token_trace_lengths_and_hash_format_verified':True,'technical_failures':0}

def stats(v):
 return {'queries':len(v),'correct':sum(x['margin']>0 for x in v),'incorrect':sum(x['margin']<0 for x in v),'exact_tie':sum(x['margin']==0 for x in v),'near_tie_1e6':sum(abs(x['margin'])<=1e-6 for x in v),'near_tie_1e5':sum(abs(x['margin'])<=1e-5 for x in v),'strict_success_rate':mean(x['margin']>0 for x in v),'mean_margin':mean(x['margin'] for x in v),'median_margin':statistics.median(x['margin'] for x in v)}
def paired(v):
 cells={c:[x for x in v if x['condition']==c] for c in ['LITERAL','RESOLVED']}
 assert len(cells['LITERAL'])==len(cells['RESOLVED'])
 a=stats(cells['LITERAL']);b=stats(cells['RESOLVED'])
 return {'literal_success_rate':a['strict_success_rate'],'resolved_success_rate':b['strict_success_rate'],'resolved_minus_literal_pp':100*(b['strict_success_rate']-a['strict_success_rate']),'literal_mean_margin':a['mean_margin'],'resolved_mean_margin':b['mean_margin'],'mean_margin_change':b['mean_margin']-a['mean_margin']}
def outputs(metrics):
 cells=[dict(zip(['model_key','condition'],k),**stats(v)) for k,v in sorted(group(metrics,['model_key','condition']).items())]
 templates=[dict(zip(['model_key','template_id','condition'],k),**stats(v)) for k,v in sorted(group(metrics,['model_key','template_id','condition']).items())]
 blocks=[dict(zip(['model_key','block_id','template_id','instance'],k),**paired(v)) for k,v in sorted(group(metrics,['model_key','block_id','template_id','instance']).items())]
 template_pairs=[dict(zip(['model_key','template_id'],k),**paired(v)) for k,v in sorted(group(metrics,['model_key','template_id']).items())]
 summary=[];loto=[]
 for (model,),v in sorted(group(metrics,['model_key']).items()):
  tp=[x for x in template_pairs if x['model_key']==model]
  for omitted in [x['template_id'] for x in tp]:
   rest=[x for x in tp if x['template_id']!=omitted]
   loto.append({'model_key':model,'excluded_template':omitted,'resolved_minus_literal_pp':mean(x['resolved_minus_literal_pp'] for x in rest),'mean_margin_change':mean(x['mean_margin_change'] for x in rest)})
  ll=[x for x in loto if x['model_key']==model]
  keyed={(x['block_id'],x['wording'],x['condition']):x for x in v};transitions=collections.Counter()
  label=lambda m:'correct' if m>0 else 'wrong' if m<0 else 'tie'
  for b,w in sorted({(x['block_id'],x['wording']) for x in v}):
   transitions[label(keyed[b,w,'LITERAL']['margin'])+'_to_'+label(keyed[b,w,'RESOLVED']['margin'])]+=1
  summary.append({'model_key':model,'templates':4,'blocks':12,'literal_success_rate':mean(x['literal_success_rate'] for x in tp),'resolved_success_rate':mean(x['resolved_success_rate'] for x in tp),'resolved_minus_literal_pp':mean(x['resolved_minus_literal_pp'] for x in tp),'mean_margin_change':mean(x['mean_margin_change'] for x in tp),'template_delta_pp_min':min(x['resolved_minus_literal_pp'] for x in tp),'template_delta_pp_max':max(x['resolved_minus_literal_pp'] for x in tp),'loto_delta_pp_min':min(x['resolved_minus_literal_pp'] for x in ll),'loto_delta_pp_max':max(x['resolved_minus_literal_pp'] for x in ll),'paired_wording_transitions':dict(transitions)})
 return cells,templates,blocks,template_pairs,summary,loto

def analyze():
 raw,metrics,replay=reconstruct()
 assert len(raw)==768 and len(metrics)==192
 cells,templates,blocks,tp,summary,loto=outputs(metrics)
 writej(S/'raw_control_scores.jsonl',raw);writej(S/'control_query_metrics.jsonl',metrics)
 csvout(S/'control_condition_summary.csv',cells);csvout(S/'control_template_summary.csv',templates)
 csvout(S/'control_paired_contrasts.csv',[{k:v for k,v in x.items() if k!='paired_wording_transitions'} for x in summary])
 csvout(S/'control_block_contrasts.csv',blocks);csvout(S/'control_template_contrasts.csv',tp);csvout(S/'control_loto_summary.csv',loto)
 result={'created_at_utc':datetime.now(timezone.utc).isoformat(),'design':'LITERAL_vs_RESOLVED_exact_integer_arithmetic','designation':'template_shared_exploratory','metrics':'strict margin>0 and separate wrong/tie/near-tie/margins; no significance criterion','aggregation':'two wordings/orders perblock,3instances pertemplate,4templates equally weighted','condition_summaries':cells,'model_summaries':summary,'old_data_used_as_intervention_control':False,'inferential_claims':False,'dataset_queries':48,'base_blocks':12,'templates':4}
 write(S/'CONTROL_RESULTS.json',result)
 replay['created_at_utc']=datetime.now(timezone.utc).isoformat();replay['raw_combined_sha256']=sha(S/'raw_control_scores.jsonl')
 replay['output_hashes']={p.name:sha(p) for p in [S/'control_query_metrics.jsonl',S/'control_condition_summary.csv',S/'control_template_summary.csv',S/'control_paired_contrasts.csv',S/'control_block_contrasts.csv',S/'control_template_contrasts.csv',S/'control_loto_summary.csv']}
 write(S/'replay_verification.json',replay);print(json.dumps({'replay':'PASS','models':summary}))

def replay_only():
 raw,m,replay=reconstruct();assert readj(S/'control_query_metrics.jsonl')==m
 cells,templates,blocks,tp,summary,loto=outputs(m)
 prior=read(S/'CONTROL_RESULTS.json');assert prior['condition_summaries']==cells and prior['model_summaries']==summary
 for name in read(S/'replay_verification.json')['output_hashes']:
  assert sha(S/name)==read(S/'replay_verification.json')['output_hashes'][name]
 print(json.dumps({'status':'PASS','raw_rows':len(raw),'query_model_results':len(m),'recomputed_metrics_and_summaries_match':True,'new_forward_calls':0}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--replay-only',action='store_true');a=p.parse_args()
 if a.replay_only:replay_only()
 else:analyze()