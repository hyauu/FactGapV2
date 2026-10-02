"""Join corrected executions and proven identical inherited pairs; never relabel cached scores as new forwards."""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,math,statistics
from pathlib import Path
S=Path(__file__).resolve().parents[1];ROOT=S.parent;D=S/'data/stage2_eval_repair/v002';OLD=ROOT/'data/stage2_eval_exploratory/v1';MODELS=['bm25','bge_small','e5_small','minilm_ce']
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def readj(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def jb(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def hs(x):return hashlib.sha256(x).hexdigest()
def write(p,x):
 if p.exists():raise FileExistsError(p)
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def writej(p,x):
 if p.exists():raise FileExistsError(p)
 p.write_text(''.join(json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n' for v in x),encoding='utf-8')
def csvout(p,rows):
 if p.exists():raise FileExistsError(p)
 with p.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def groups(rows,keys):
 out=collections.defaultdict(list)
 for r in rows:out[tuple(r[k] for k in keys)].append(r)
 return out

def reconstruct():
 lock=read(S/'STAGE22_STAGE2_REPAIR_SCORE_LOCK.json')
 for f in lock['file_locks']:
  if sha(ROOT/f['path'])!=f['sha256']:raise RuntimeError('Corrected score lock drift')
 payloads=readj(D/'model_inputs.jsonl');index=readj(D/'private_payload_index.jsonl');oldp=readj(OLD/'model_inputs.jsonl');oldix=readj(OLD/'private_payload_index.jsonl');blocks={b['block_id']:b for b in readj(D/'blocks.jsonl')};lookup={q['query_id']:(b,q) for b in blocks.values() for q in b['queries']}
 if len(payloads)!=len(index) or len(payloads)!=672:raise RuntimeError('Corrected full input shape')
 rawold=readj(ROOT/'raw_local_scores.jsonl');oldrows={(r['model_key'],r['request_ordinal'],r['candidate_display_index']):r for r in rawold if r['split']=='eval'};oldsha=sha(ROOT/'raw_local_scores.jsonl');combined=[];metrics=[];newcount=0;carrycount=0;maxdiff=0.0;new_cache_checks=0
 for model in MODELS:
  scope=set(lock['rerun_request_ordinals'][model]);rp=S/f'runs/stage2_repair_v2/raw_{model}.jsonl';mp=S/f'runs/stage2_repair_v2/manifest_{model}.json';manifest=read(mp);rows=readj(rp)
  if sha(rp)!=manifest['raw_sha256'] or manifest['prospective_lock_sha256']!=sha(S/'STAGE22_STAGE2_REPAIR_SCORE_LOCK.json'):raise RuntimeError('Corrected model receipt drift')
  newrows={(r['request_ordinal'],r['candidate_display_index']):r for r in rows}
  if len(newrows)!=len(rows) or set(newrows)!={(o,p) for o in scope for p in [0,1]}:raise RuntimeError('Incomplete/duplicate rerun matrix')
  seen={}
  for r in rows:
   p=payloads[r['request_ordinal']];pair=(p['query'],p['candidates'][r['candidate_display_index']]);prior=seen.get(pair)
   if prior is None:
    if r['execution_mode']!='executed_batched' or r['cache_source_request_id'] is not None:raise RuntimeError('Fresh pair origin mismatch')
    seen[pair]=r
   else:
    if r['execution_mode']!='reused_from_pair_cache' or r['cache_source_request_id']!=prior['request_id'] or r['raw_score']!=prior['raw_score'] or r['tokenizer_input_sha256']!=prior['tokenizer_input_sha256']:raise RuntimeError('Fresh cache chain mismatch')
    new_cache_checks+=1
  byq=collections.defaultdict(list)
  for ordinal,(p,ix) in enumerate(zip(payloads,index)):
   if set(p)!={'query','candidates'} or ix['payload_sha256']!=hs(jb(p)):raise RuntimeError('Visible input hash/schema')
   scored={}
   for pos,d in enumerate(p['candidates']):
    if ordinal in scope:
     r=dict(newrows[ordinal,pos]);r['transport_origin']='stage22_reexecuted';newcount+=1
    else:
     if model=='bm25':raise RuntimeError('BM25 cannot carry across changed corpus')
     if p!=oldp[ordinal] or ix!=oldix[ordinal]:raise RuntimeError('Changed input cannot reuse inherited score')
     original=oldrows[model,ordinal,pos]
     if original['query_id_private']!=ix['query_id'] or original['block_id_private']!=ix['block_id'] or original['role_private']!=ix['position_to_role'][pos]:raise RuntimeError('Inherited private link mismatch')
     r={k:v for k,v in original.items() if not k.endswith('_private')};r.update({'transport_origin':'inherited_unchanged_pair','source_raw_sha256':oldsha,'source_row_sha256':hs(jb(original)),'source_request_id':original['request_id'],'source_run_id':original['run_id'],'source_dataset_version':original['dataset_version'],'inherited_execution_mode':original['execution_mode'],'inherited_cache_source_request_id':original['cache_source_request_id'],'execution_mode':'reused_from_inherited_identical_pair','cache_source_request_id':original['request_id'],'run_id':'stage22_corrected_eval_join','dataset_version':lock['dataset_version'],'split':'eval_repaired','request_id':f'carry-eval-{model}-{ordinal:06d}'})
     carrycount+=1
    if r['status']!='OK' or r['technical_error_code'] is not None or not math.isfinite(r['raw_score']):raise RuntimeError('Technical/nonfinite score')
    if r['model_revision']!=lock['target_models'][model]['revision']:raise RuntimeError('Model revision mismatch')
    if r['payload_sha256']!=ix['payload_sha256'] or r['query_text_sha256']!=hs(p['query'].encode()) or r['candidate_text_sha256']!=hs(d.encode()):raise RuntimeError('Raw query/document/payload hash mismatch')
    if r['orientation']!=ordinal%2 or max(r['query_token_length'],r['document_or_pair_token_length'])>512 or min(r['query_token_length'],r['document_or_pair_token_length'])<=0:raise RuntimeError('Order/token metadata mismatch')
    combined.append(r);scored[ix['position_to_role'][pos]]=r['raw_score']
   if set(scored)!={'gold','counterpart'}:raise RuntimeError('Role coverage')
   byq[ix['query_id']].append({'ordinal':ordinal,'margin':scored['gold']-scored['counterpart']})
  if set(byq)!=set(lookup):raise RuntimeError('Query coverage mismatch')
  for qid,rs in byq.items():
   if len(rs)!=2:raise RuntimeError('Both orientations required')
   p0,p1=[payloads[x['ordinal']] for x in rs]
   if p0['query']!=p1['query'] or p0['candidates']!=list(reversed(p1['candidates'])):raise RuntimeError('Candidate order imbalance')
   diff=abs(rs[0]['margin']-rs[1]['margin']);maxdiff=max(maxdiff,diff)
   if diff>1e-4:raise RuntimeError('Order margin exceeds tolerance')
   margin=statistics.mean(x['margin'] for x in rs);b,q=lookup[qid]
   metrics.append({'model_key':model,'transformation':b['transformation'],'template_id':b['semantic_template_id'],'block_id':b['block_id'],'query_id':qid,'n':q['n'],'l':q.get('l',0),'wording':q['wording'],'margin':margin,'strict_success':int(margin>0),'exact_tie':int(margin==0),'near_tie_1e6':int(abs(margin)<=1e-6),'near_tie_1e5':int(abs(margin)<=1e-5),'orientation_margin_difference':diff,'technical_failure':0})
 if len(combined)!=5376 or len(metrics)!=1344 or newcount!=2*lock['new_logical_ranking_requests'] or carrycount!=5376-newcount:raise RuntimeError('Corrected total matrix cardinality')
 replay={'status':'PASS','raw_rows':len(combined),'query_model_pairs':len(metrics),'full_queries':336,'current_matrix_logical_requests':2688,'new_executed_logical_requests':lock['new_logical_ranking_requests'],'new_score_rows':newcount,'inherited_identical_score_rows':carrycount,'new_pair_cache_links_verified':new_cache_checks,'maximum_order_margin_difference':maxdiff,'technical_failures':0,'scope':'All four current models; all336 current queries; both candidate orders. Retokenization separately recorded; inherited identical neural pairs explicitly reused.','old_raw_sha256':oldsha}
 return combined,metrics,replay

def stats(rows):return {'queries':len(rows),'strict_success':sum(r['strict_success'] for r in rows),'success_rate':statistics.mean(r['strict_success'] for r in rows),'exact_ties':sum(r['exact_tie'] for r in rows),'near_tie_1e6':sum(r['near_tie_1e6'] for r in rows),'near_tie_1e5':sum(r['near_tie_1e5'] for r in rows),'mean_margin':statistics.mean(r['margin'] for r in rows),'technical_failures':sum(r['technical_failure'] for r in rows)}
def main(replay_only=False):
 raw,metrics,replay=reconstruct()
 if replay_only:
  if readj(S/'raw_stage2_repaired_scores.jsonl')!=raw or readj(S/'stage2_repaired_query_metrics.jsonl')!=metrics:raise RuntimeError('Corrected raw/analysis replay mismatch')
  print(json.dumps(replay));return
 writej(S/'raw_stage2_repaired_scores.jsonl',raw);writej(S/'stage2_repaired_query_metrics.jsonl',metrics)
 summaries=[]
 for fields,name in [(['model_key','transformation'],'STAGE2_REPAIRED_MODEL_SUMMARY.csv'),(['model_key','transformation','template_id'],'STAGE2_REPAIRED_TEMPLATE_SUMMARY.csv'),(['model_key','transformation','block_id'],'STAGE2_REPAIRED_INSTANCE_SUMMARY.csv')]:
  out=[dict(zip(fields,k),**stats(v)) for k,v in sorted(groups(metrics,fields).items())];csvout(S/name,out)
  if len(fields)==2:summaries=out
 write(S/'STAGE2_REPAIRED_RESULTS.json',{'designation':'post_score_repaired_exploratory','primary_metric':'Mean two-order gold-minus-counterpart margin>0; exact ties fail','per_transformation_summaries':summaries,'no_universal_reasoning_score':True,'new_score_rows':replay['new_score_rows'],'inherited_identical_neural_rows':replay['inherited_identical_score_rows'],'outcome_driven_selection':False})
 write(S/'STAGE2_REPAIR_REPLAY_VERIFICATION.json',replay);print(json.dumps({'replay':replay,'summaries':summaries}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--replay-only',action='store_true');x=p.parse_args();main(x.replay_only)
