"""Reconstruct all ALIGN3 results solely from complete raw scoring receipts plus sealed private join."""
from pathlib import Path
import json,csv,math,hashlib,collections,statistics,sys,re
R=Path(__file__).resolve().parents[1]
KEYS=['bm25','bge_small','e5_small','minilm_ce'];CONDS=['WRONG_ALIGNED','NEUTRAL','GOLD_ALIGNED'];CONTRASTS=[('GOLD_ALIGNED','WRONG_ALIGNED'),('NEUTRAL','WRONG_ALIGNED'),('GOLD_ALIGNED','NEUTRAL')]
def jl(p):return [json.loads(x) for x in (R/p).read_text(encoding='utf-8-sig').splitlines() if x]
def read(p):return json.loads((R/p).read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256((R/p).read_bytes()).hexdigest()
def cat(v):return 'WIN' if v>0 else 'LOSE' if v<0 else 'TIE'
def mean(v):return statistics.mean(v)
def reconstruction():
 lock=read('CONTROL_LOCK.json');assert lock['status']=='LOCKED_BEFORE_TARGET_SCORING'
 for row in lock['file_locks']:assert digest(row['path'])==row['sha256']
 # Check all four complete scorers before reading gold/condition labels.
 for k in KEYS:
  m=read(f'scoring/manifest_{k}.json');assert m['status']=='COMPLETE' and m['score_rows']==288 and m['logical_ranking_requests']==144
  assert m['raw_sha256']==digest(f'scoring/raw_{k}.jsonl')
 pub={p['item_id']:p for p in jl('data/eval_queries.jsonl')};requests={p['request_id']:p for p in jl('private/request_map.jsonl')}
 gold={p['item_id']:p for p in jl('private/eval_map.jsonl')}
 conditions=[];blockrows=[];templaterows=[];contrasts=[];transitions=[];monotonic=[];queryrows=[];errors=[];raw_all=[];max_order_diff=0
 for k in KEYS:
  raw=jl(f'scoring/raw_{k}.jsonl');raw_all+=raw;groups=collections.defaultdict(list)
  for v in raw:
   assert v['status']=='OK' and math.isfinite(v['raw_score']) and v['request_id'] in requests
   rq=requests[v['request_id']];p=pub[rq['item_id']]
   assert v['query_text']==p['query'] and v['query_text_sha256']==hashlib.sha256(p['query'].encode()).hexdigest()
   assert v['candidate_text_sha256']==hashlib.sha256(v['candidate_text'].encode()).hexdigest()
   assert v['candidate_text'] in p['candidates']
   assert v['candidate_text_sha256']==rq['candidate_text_sha256_in_display_order'][v['candidate_display_index']]
   assert v['corpus_sha256']==lock['corpus_sha256']
   groups[(rq['item_id'],rq['orientation'])].append(v)
  assert len(groups)==144
  qmargin={}
  for iid,p in pub.items():
   pr=gold[iid];gdoc=p['candidates'][pr['gold_index']];wdoc=p['candidates'][1-pr['gold_index']];ms=[]
   for orientation in [0,1]:
    rr=groups[(iid,orientation)];assert len(rr)==2 and {x['candidate_text'] for x in rr}=={gdoc,wdoc}
    scores={x['candidate_text']:x['raw_score'] for x in rr};ms.append(scores[gdoc]-scores[wdoc])
   diff=abs(ms[0]-ms[1]);max_order_diff=max(max_order_diff,diff)
   if diff>1e-4:errors.append({'model':k,'item_id':iid,'error':'ORDER_DIFFERENCE','difference':diff})
   # Use forward order, do not average a technical disagreement away.
   qmargin[iid]=ms[0]
   queryrows.append(dict(model_key=k,item_id=iid,block_id=pr['block_id'],template_id=pr['template_id'],wording=pr['wording'],condition=pr['condition'],margin=ms[0],outcome=cat(ms[0]),order_max_abs_difference=diff))
  blockvalues={};templatevalues={}
  for bi in range(12):
   bid=f'eval_block_{bi:02d}';tt=gold[next(i for i in gold if gold[i]['block_id']==bid)]['template_id']
   for c in CONDS:
    vals=[qmargin[i] for i,p in gold.items() if p['block_id']==bid and p['condition']==c];assert len(vals)==2
    blockvalues[(bid,c)]=mean(vals);blockrows.append(dict(model_key=k,block_id=bid,template_id=tt,condition=c,margin=mean(vals),wording1_margin=vals[0],wording2_margin=vals[1]))
  for ti in range(1,5):
   tt=f'template_{ti}'
   for c in CONDS:
    vals=[v['margin'] for v in blockrows if v['model_key']==k and v['template_id']==tt and v['condition']==c];assert len(vals)==3
    templatevalues[(tt,c)]=mean(vals);templaterows.append(dict(model_key=k,template_id=tt,condition=c,margin=mean(vals),blocks=3))
  for c in CONDS:
   vals=[qmargin[i] for i,p in gold.items() if p['condition']==c];assert len(vals)==24
   conditions.append(dict(model_key=k,condition=c,n_queries=24,n_blocks=12,n_templates=4,wins=sum(v>0 for v in vals),losses=sum(v<0 for v in vals),exact_ties=sum(v==0 for v in vals),mean_margin=mean(vals),median_margin=statistics.median(vals),primary_template_equal_margin=mean([templatevalues[(f'template_{t}',c)] for t in range(1,5)]),near_tie_1e_6=sum(abs(v)<=1e-6 for v in vals),near_tie_1e_5=sum(abs(v)<=1e-5 for v in vals)))
  for hi,lo in CONTRASTS:
   tv=[templatevalues[(f'template_{t}',hi)]-templatevalues[(f'template_{t}',lo)] for t in range(1,5)]
   bv=[blockvalues[(f'eval_block_{b:02d}',hi)]-blockvalues[(f'eval_block_{b:02d}',lo)] for b in range(12)]
   loto=[mean([x for j,x in enumerate(tv) if j!=t]) for t in range(4)]
   contrasts.append(dict(model_key=k,contrast=hi+'-'+lo,mean_paired_margin_shift=mean(tv),positive_blocks=sum(x>0 for x in bv),negative_blocks=sum(x<0 for x in bv),zero_blocks=sum(x==0 for x in bv),positive_templates=sum(x>0 for x in tv),negative_templates=sum(x<0 for x in tv),zero_templates=sum(x==0 for x in tv),loto_min=min(loto),loto_max=max(loto),template1=tv[0],template2=tv[1],template3=tv[2],template4=tv[3]))
   tr=collections.Counter()
   for b in range(12):
    for wi in [0,1]:
     lookup={p['condition']:qmargin[i] for i,p in gold.items() if p['block_id']==f'eval_block_{b:02d}' and p['wording']==wi}
     tr[cat(lookup[lo])+'->'+cat(lookup[hi])]+=1
   transitions.append(dict(model_key=k,contrast=hi+'-'+lo,transitions=dict(sorted(tr.items())),paired_queries=24))
  for b in range(12):
   w,n,g=[blockvalues[(f'eval_block_{b:02d}',c)] for c in CONDS]
   monotonic.append(dict(model_key=k,block_id=f'eval_block_{b:02d}',nondecreasing=w<=n<=g,strict_increase=w<n<g,equality_present=(w==n or n==g),m_wrong=w,m_neutral=n,m_gold=g))
 # BM25 term-by-term independent analytic expectation for symmetric docs.
 corpus=[v['text'] for v in jl('scoring/scoring_corpus.jsonl')];terms=lambda s:re.findall(r'\d+(?:\.\d+)?|[A-Za-z]+',s.lower())
 counters=[collections.Counter(terms(d)) for d in corpus];N=len(counters);avgdl=mean([sum(d.values()) for d in counters]);df=collections.Counter(t for d in counters for t in d)
 analytic=[]
 for p in queryrows:
  if p['model_key']!='bm25':continue
  pr=gold[p['item_id']];q=pub[p['item_id']]['query'];qt=set(terms(q))
  contrib=[]
  for d in pub[p['item_id']]['candidates']:
   dc=collections.Counter(terms(d));dl=sum(dc.values());cs={}
   for t in qt:
    tf=dc[t]
    if tf:cs[t]=math.log(1+(N-df[t]+.5)/(df[t]+.5))*(tf*2.2)/(tf+1.2*(1-.75+.75*dl/avgdl))
   contrib.append(cs)
  gi=pr['gold_index'];pred=sum(contrib[gi].values())-sum(contrib[1-gi].values());err=abs(pred-p['margin']);assert err<=1e-10
  expected_sign={'WRONG_ALIGNED':'LOSE','NEUTRAL':'TIE','GOLD_ALIGNED':'WIN'}[pr['condition']]
  analytic.append(dict(item_id=p['item_id'],condition=pr['condition'],expected_outcome=expected_sign,actual_outcome=p['outcome'],matches_expected=p['outcome']==expected_sign,analytic_margin=pred,raw_margin=p['margin'],absolute_error=err,candidate_term_contributions=contrib))
 return {'condition_results':conditions,'paired_contrasts':contrasts,'template_results':templaterows,'block_results':blockrows,'query_results':queryrows,'transitions':transitions,'monotonic_blocks':monotonic,'bm25_analytic':analytic,'technical_errors':errors,'max_order_abs_difference':max_order_diff,'score_rows':len(raw_all),'raw_rows':raw_all}
def csvwrite(p,rr):
 with (R/p).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
def jsonwrite(p,x):
 if (R/p).exists():
  assert read(p)==x,p
  return
 with (R/p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
if __name__=='__main__':
 out=reconstruction()
 if len(sys.argv)>1 and sys.argv[1]=='--replay':
  previous=read('analysis/summary.json');compare={k:v for k,v in out.items() if k!='raw_rows'}
  assert compare==previous
  for name in ['condition_results','paired_contrasts','template_results','block_results','query_results']:
   with (R/(name+'.csv')).open(encoding='utf-8',newline='') as f:actual=list(csv.DictReader(f))
   expected=[{k:str(v) for k,v in x.items()} for x in out[name]];assert actual==expected,name
  jsonwrite('replay_check.json',{'status':'PASS','source':'complete original score rows plus private locked maps; no model calls','raw_score_rows':out['score_rows'],'all_summary_fields_equal':True,'all_CSV_rows_equal':True,'model_forward_calls':0,'maximum_order_abs_difference':out['max_order_abs_difference'],'technical_errors':out['technical_errors'],'bm25_termwise_checks':len(out['bm25_analytic']),'bm25_expected_sign_checks_pass':all(x['matches_expected'] for x in out['bm25_analytic'])})
 else:
  assert out['score_rows']==1152
  for name in ['condition_results','paired_contrasts','template_results','block_results','query_results']:csvwrite(name+'.csv',out[name])
  with (R/'raw_scores.jsonl').open('x',encoding='utf-8') as f:
   for x in out['raw_rows']:f.write(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n')
  jsonwrite('analysis/summary.json',{k:v for k,v in out.items() if k!='raw_rows'})
  print(json.dumps({'rows':out['score_rows'],'condition_results':out['condition_results'],'paired_contrasts':out['paired_contrasts'],'technical_errors':out['technical_errors']},ensure_ascii=False))
