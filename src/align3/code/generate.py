"""Deterministic ALIGN3 construction and minimal blinded packets; no model scores read."""
from pathlib import Path
from datetime import datetime,timezone
import json,random,re,hashlib,sys
R=Path(__file__).resolve().parents[1]
CONDS=['WRONG_ALIGNED','NEUTRAL','GOLD_ALIGNED']
SEEDS={'dev':431730,'eval':851906}
TEMPLATES=[
['Find the record for the {e} batch whose item count is {lw} the result of {lo} and {uw} the result of {hi}.','Which record describes the {e} batch with an item count {uw} the result of {hi} and {lw} the result of {lo}?'],
['Select the statement about the {e} batch with an item count {lw} the result of {lo} and {uw} the result of {hi}.','For the {e} batch, choose the statement whose item count is {uw} the result of {hi} and {lw} the result of {lo}.'],
['Retrieve the statement for the {e} batch if its item count is {lw} the result of {lo} and {uw} the result of {hi}.','For the {e} batch, find a record with an item count {uw} the result of {hi} and {lw} the result of {lo}.'],
['Identify the record describing the {e} batch with an item count {lw} the result of {lo} and {uw} the result of {hi}.','Choose the record for the {e} batch whose item count is {uw} the result of {hi} and {lw} the result of {lo}.']]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x,jl=False):
 p=R/p;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8',newline='\n') as f:
  if jl:
   for v in x:f.write(json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n')
  else:json.dump(x,f,ensure_ascii=False,indent=2)
def load(p):return json.loads((R/p).read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(s) for s in (R/p).read_text(encoding='utf-8-sig').splitlines() if s]
def build(split):
 if split=='dev':
  for p in ['audit/dev_semantic_seal.json','audit/initial_design_seal.json']:
   if p.endswith('initial_design_seal.json'): assert load(p)['status']=='PASS_LIMITED'
 else:assert load('audit/dev_final_seal.json')['status']=='PASS_LIMITED'
 rng=random.Random(SEEDS[split]);n=4 if split=='dev' else 12
 entities=['fir','alder','birch','beech'] if split=='dev' else ['spruce','maple','oak','pine','willow','elm','ash','hazel','larch','yew','walnut','poplar']
 pub=[];private=[];blocks=[];draws=[]
 for bi in range(n):
  ti=bi if split=='dev' else bi//3;inst=0 if split=='dev' else bi%3
  closed=bi%2==0;pos=['below_both','between','above_both'][bi%3]
  e=entities[bi];bid=f'{split}_block_{bi:02d}'
  for trial in range(200):
   L=rng.randint(130,650);width=rng.randint(60,85);U=L+width;G=L+rng.randint(20,width-20);W=U if closed else L
   if closed:
    nr={'below_both':(L+10,G-1),'between':(G+1,U-1),'above_both':(U+1,L+99)}[pos]
   else:nr={'below_both':(U-99,L-1),'between':(L+1,G-1),'above_both':(G+1,U-10)}[pos]
   N=rng.randint(*nr);a=rng.randint(11,60);h=U-a if closed else L+a
   vals=[W,N,G];compl=[v-L if closed else U-v for v in vals]
   reasons=[]
   if not all(100<=x<=999 for x in vals+[h]):reasons.append('leading_operand_width')
   if not all(10<=x<=99 for x in compl+[a]):reasons.append('complement_width')
   if any(x in [G,W] for x in [h,a]+compl):reasons.append('incidental_candidate_numeral')
   if len(set([G,W,N]))!=3 or not L<G<U:reasons.append('role_or_interval')
   params=dict(L=L,U=U,G=G,W=W,N=N,h=h,a=a,lower_inclusive=closed,upper_inclusive=not closed)
   draws.append(dict(block_id=bid,seed=SEEDS[split],trial=trial,parameters=params,rejected=bool(reasons),reasons=reasons))
   if not reasons:break
  else:raise RuntimeError('STRUCTURE_INFEASIBLE '+bid)
  gold_index=rng.randrange(2);candidate_values=[G,W] if gold_index==0 else [W,G]
  candidates=[f'The {e} batch has an item count of {v}.' for v in candidate_values]
  blockitems=[]
  for cond,x in zip(CONDS,vals):
   lo=f'{x} minus {x-L}' if closed else f'{h} minus {a}'
   hi=f'{h} plus {a}' if closed else f'{x} plus {U-x}'
   for wi,frame in enumerate(TEMPLATES[ti]):
    query=frame.format(e=e,lw='at least' if closed else 'greater than',uw='below' if closed else 'at most',lo=lo,hi=hi)
    item_id='q_'+f'{rng.getrandbits(64):016x}'
    p={'item_id':item_id,'query':query,'candidates':candidates};pub.append(p)
    spans=[{'start':m.start(),'end':m.end(),'text':m.group()} for m in re.finditer(r'\d+',query)]
    target=x-L if closed else U-x
    changing=[j for j,s in enumerate(spans) if int(s['text']) in [x,target]]
    # Explicit changing pair positions from lower/upper clause order; no text-value inference.
    changing=[0,1] if (closed and wi==0) or (not closed and wi==1) else [2,3]
    pr=dict(item_id=item_id,block_id=bid,template_id=f'template_{ti+1}',instance=inst,condition=cond,wording=wi,entity=e,property='item count',gold_index=gold_index,candidate_values=candidate_values,**params,neutral_relative_position=pos,gold_lower_distance=G-L,gold_upper_distance=U-G,numeral_spans=spans,changing_numeral_span_indices=changing,operand=x,complement=target,frame=re.sub(r'\d+','<NUM>',query),split=split,split_type='template_shared_exploratory' if split=='eval' else 'design_development')
    private.append(pr);blockitems.append(item_id)
  blocks.append(dict(block_id=bid,template_id=f'template_{ti+1}',item_ids=blockitems,parameters=params,neutral_relative_position=pos))
 # Mechanical invariants independently from model outcome.
 check=[]
 for b in blocks:
  prs=[p for p in private if p['block_id']==b['block_id']]
  for wi in [0,1]:
   rr=[p for p in prs if p['wording']==wi];qs=[next(x['query'] for x in pub if x['item_id']==p['item_id']) for p in rr]
   assert len(set(p['frame'] for p in rr))==1
   assert len(set(map(len,qs)))==1 and len(set(len(q.split()) for q in qs))==1
   assert len(set(tuple(len(s['text']) for s in p['numeral_spans']) for p in rr))==1
   for p,q in zip(rr,qs):
    nums=[int(s['text']) for s in p['numeral_spans']]
    expect=p['W'] if p['condition']=='WRONG_ALIGNED' else p['G'] if p['condition']=='GOLD_ALIGNED' else None
    assert nums.count(p['W'])==(1 if expect==p['W'] else 0)
    assert nums.count(p['G'])==(1 if expect==p['G'] else 0)
    assert q.count(' minus ')==1 and q.count(' plus ')==1
    sats=[(p['L']<=v if p['lower_inclusive'] else p['L']<v) and (v<=p['U'] if p['upper_inclusive'] else v<p['U']) for v in p['candidate_values']]
    assert sats.count(True)==1 and sats[p['gold_index']]
    assert p['operand']-p['complement']==p['L'] if p['lower_inclusive'] else p['operand']+p['complement']==p['U']
    other=[nums[j] for j in range(4) if j not in p['changing_numeral_span_indices']]
    assert sum(other)==p['U'] if p['lower_inclusive'] else other[0]-other[1]==p['L']
   check.append(dict(block_id=b['block_id'],wording=wi,characters=len(qs[0]),space_words=len(qs[0].split()),digit_widths=[len(s['text']) for s in rr[0]['numeral_spans']],status='PASS'))
 rng.shuffle(pub)
 save(f'data/{split}_queries.jsonl',pub,True);save(f'private/{split}_map.jsonl',private,True)
 save(f'private/{split}_blocks.json',blocks);save(f'private/{split}_draw_ledger.jsonl',draws,True)
 save(f'data/{split}_structural_check.json',{'status':'PASS','queries':len(pub),'blocks':n,'checks':check,'score_based_selection':False,'seed':SEEDS[split]})
 # One item/block per packet. Each split has six cyclic variants/block.
 groups=[blocks] if split=='dev' else [blocks[:6],blocks[6:]]
 pnum=0
 for group in groups:
  perms={b['block_id']:rng.sample(b['item_ids'],6) for b in group}
  for vi in range(6):
   items=[next(x for x in pub if x['item_id']==perms[b['block_id']][vi]) for b in group];rng.shuffle(items)
   save(f'audit/prompts/{split}_p{pnum:02d}.json',items)
   pnum+=1
 for gi in range((n+3)//4):
  bp=[]
  for b in blocks[gi*4:gi*4+4]:
   items=[next(x for x in pub if x['item_id']==iid) for iid in b['item_ids']];rng.shuffle(items)
   bp.append({'block_id':b['block_id'],'views':items})
  save(f'audit/prompts/{split}_design{gi}.json',bp)
 print(json.dumps({'split':split,'queries':len(pub),'blocks':n,'semantic_packets':pnum,'design_packets':(n+3)//4}))
if __name__=='__main__':build(sys.argv[1])
