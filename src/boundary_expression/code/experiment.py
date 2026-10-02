"""Small run-specific material, review packet and gate helpers; no scheduler."""
import argparse, collections, datetime, hashlib, json, pathlib, random, re
ROOT=pathlib.Path(r'<LOCAL_PROJECT>')
RUN=pathlib.Path(__file__).resolve().parent.parent
SEED=440917
TOPICS=[('warehouse inventory','item count'),('library shipment','book count'),('orchard survey','tree count'),('museum catalog','object count')]
def now():return datetime.datetime.now(datetime.timezone.utc)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def jb(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(x):return hashlib.sha256(jb(x)).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def save(p,x,replace=False):
 if p.exists() and not replace:raise FileExistsError(p)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def savej(p,x):
 if p.exists():raise FileExistsError(p)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(z,ensure_ascii=False,separators=(',',':'))+'\n' for z in x),encoding='utf-8')
def active():
 l=read(RUN/'ACTIVE_TIME_LEDGER.json');return l['carried_active_work_seconds']+(now()-datetime.datetime.fromisoformat(l['active_segment_started_utc'])).total_seconds()
def checkpoint(phase,**fields):
 elapsed=active()
 if elapsed>=14400:raise RuntimeError('Active work budget reached; report only')
 s=read(RUN/'STATE.json');s.update(phase=phase,ACTIVE_WORK_ELAPSED=elapsed,updated_at_utc=now().isoformat(),**fields);save(RUN/'STATE.json',s,True)
 l=read(RUN/'ACTIVE_TIME_LEDGER.json');l['ACTIVE_WORK_ELAPSED']=elapsed;l['last_checkpoint_utc']=now().isoformat();save(RUN/'ACTIVE_TIME_LEDGER.json',l,True)
 with (RUN/'PROGRESS.md').open('a',encoding='utf-8') as f:f.write(f'\n- {now().isoformat()} / active{elapsed/60:.1f}min: {phase}; {json.dumps(fields,ensure_ascii=False)}\n')
 return elapsed

def spec():
 return {'seed':SEED,'conditions':['LITERAL','RESOLVED'],'wordings':[0,1],
 'templates':4,'DEV_blocks':4,'EVAL_blocks':12,'queries_per_block':4,
 'data_designation':'template-shared exploratory; score-blind numeric allocation',
 'topic_frames':TOPICS,'counts_only':True,'candidate_rule':'Correct strictly interior lower+3; counterpart excluded endpoint; auxiliary upper+23',
 'numeric_rule':'DEV lower=3100+template*101; EVAL lower=7100+template*503+instance*107; width=11+((template+instance)%3)*2; distinct nonzero integer operands chosen before scoring',
 'nuisance_allocation':{'DEV_excluded':['upper','lower','upper','lower'],'DEV_arithmetic':['add','sub','sub','add'],
 'EVAL_excluded':[['upper','upper','lower'],['lower','lower','upper'],['upper','lower','lower'],['lower','upper','upper']],
 'EVAL_arithmetic':[['add','sub','add'],['sub','add','sub'],['add','sub','add'],['sub','add','sub']]},
 'analysis':{'success':'margin>0; tie fails','primary':'RESOLVED-LITERAL within new matched block; average2wordings/orders then3instances/template then equal4templates','near_ties':[1e-6,1e-5],'metrics':['correct','incorrect','exact_tie','near_tie','mean/median margin','paired change','block/template','leave-one-template-out'],
 'old_scores':'Descriptive historical context only; not intervention contrast across datasets or BM25 indices','statistical_inference':'NONE; no selection/significance criterion'},
 'scope':'Specified exact endpoint-expression substitution plus arithmetic and length changes; not pure internal reasoning isolation',
 'fallback_used':False,'no_outcome_driven_selection':True,'material_repair_cap':1,'context_cap':64,'new_blocks_cap':32}

def render(t,w,entity,prop,L,U,excluded):
 if excluded=='upper':
  lower=[f'at least {L}',f'no smaller than {L}'][w]
  upper=[f'strictly below {U}',f'less than {U}'][w]
  inclusivity='including the lower boundary and excluding the upper boundary'
 else:
  lower=[f'greater than {L}',f'strictly above {L}'][w]
  upper=[f'at most {U}',f'no greater than {U}'][w]
  inclusivity='excluding the lower boundary and including the upper boundary'
 if t==0:return [f'Select the {entity} record whose {prop} is {lower} and {upper}.',f'Find the {entity} record with a {prop} {lower} but {upper}.'][w]
 if t==1:return [f'A {entity} record is eligible exactly when its {prop} is {lower} and {upper}. Return an eligible record.',f'Return a qualifying {entity} record. Qualification means that its {prop} is {lower} and {upper}.'][w]
 if t==2:return [f'Find the {entity} record with a {prop} between {L} and {U}, {inclusivity}.',f'The requested {entity} record has a {prop} in the range from {L} to {U}, {inclusivity}. Select that record.'][w]
 return [f'For a {entity} record, apply both tests to its {prop}: (1) it is {lower}; (2) it is {upper}. Select a record passing both.',f'Select a {entity} record passing both requirements on its {prop}: the value is {lower}; the value is {upper}.'][w]

def old_queries():
 out=[];files=sorted((ROOT/'data').rglob('blocks.jsonl'))+[ROOT/'stage22/data/stage2_eval_repair/v002/blocks.jsonl']
 for p in files:
  for b in rows(p):
   for q in b.get('queries',[]):
    text=q.get('text',q.get('query'))
    if isinstance(text,str):out.append(text)
 return out,files

def build(split):
 elapsed=active()
 if split=='EVAL':
  if elapsed>=10800:raise RuntimeError('EVAL build cutoff reached')
  gate=read(RUN/'QA_DEV.json')
  if gate['status']!='PASS' or gate['design_status']!='PASS_LIMITED':raise RuntimeError('DEV not fully clean')
 else:
  if elapsed>=7200:raise RuntimeError('DEV validity stoploss reached')
 if not (RUN/'CONTROL_SPEC_LOCK.json').exists():save(RUN/'CONTROL_SPEC_LOCK.json',dict(spec(),locked_at_utc=now().isoformat(),new_target_scores_observed=False))
 s=read(RUN/'CONTROL_SPEC_LOCK.json');blocks=[]
 for t,(entity,prop) in enumerate(TOPICS):
  for i in range(1 if split=='DEV' else 3):
   L=3100+t*101 if split=='DEV' else 7100+t*503+i*107
   U=L+11+((t+i)%3)*2;good=L+3;aux=U+23
   exc=s['nuisance_allocation']['DEV_excluded'][t] if split=='DEV' else s['nuisance_allocation']['EVAL_excluded'][t][i]
   op=s['nuisance_allocation']['DEV_arithmetic'][t] if split=='DEV' else s['nuisance_allocation']['EVAL_arithmetic'][t][i]
   wrong=U if exc=='upper' else L
   for small in [5,7,9,6,8]:
    a=wrong-small if op=='add' else wrong+small
    if not {a,small}&{good,wrong,L,U,aux}:break
   else:raise RuntimeError('No operands')
   expression=f'the sum of {a} and {small}' if op=='add' else f'the difference of {a} minus {small}'
   value=a+small if op=='add' else a-small
   assert value==wrong
   bid=f'{split}-T{t}-I{i}'
   docs=[{'candidate_id':bid+'-d0','text':f'The {entity} record reports {prop}: {good}.','value':good,'private_role':'gold'},
         {'candidate_id':bid+'-d1','text':f'The {entity} record reports {prop}: {wrong}.','value':wrong,'private_role':'counterpart'},
         {'candidate_id':bid+'-d2','text':f'The {entity} record reports {prop}: {aux}.','value':aux,'private_role':'auxiliary'}]
   qs=[]
   for condition in s['conditions']:
    ll=expression if condition=='RESOLVED' and exc=='lower' else str(L)
    uu=expression if condition=='RESOLVED' and exc=='upper' else str(U)
    for w in [0,1]:
     text=render(t,w,entity,prop,ll,uu,exc)
     qs.append({'query_id':f'{bid}-{condition}-W{w}','condition':condition,'wording':w,'text':text})
   blocks.append({'block_id':bid,'template_id':f'T{t}','instance':i,'entity':entity,'property':prop,'lower':L,'upper':U,'include_lower':exc=='upper','include_upper':exc=='lower','excluded_endpoint':exc,'arithmetic':op,'operands':[a,small],'expression':expression,'documents':docs,'queries':qs})
 old,oldfiles=old_queries()
 if split=='EVAL':old += [q['text'] for b in rows(RUN/'data/DEV/blocks.jsonl') for q in b['queries']]
 normalize=lambda x:re.sub(r'\s+',' ',x.lower()).strip()
 oldset=set(old);oldnorm=set(map(normalize,old));seen=set();seennorm=set();descriptors=[]
 for b in blocks:
  satisfying=[d for d in b['documents'] if (d['value']>b['lower'] or b['include_lower'] and d['value']==b['lower']) and (d['value']<b['upper'] or b['include_upper'] and d['value']==b['upper'])]
  assert [d['private_role'] for d in satisfying]==['gold']
  for q in b['queries']:
   text=q['text'];assert b['property'] in text
   assert text not in oldset and normalize(text) not in oldnorm and text not in seen and normalize(text) not in seennorm
   assert not re.search(r'\b(gold|counterpart|correct candidate|incorrect candidate)\b',text,re.I)
   seen.add(text);seennorm.add(normalize(text));nums=re.findall(r'\d+',text)
   wrong=str(b['documents'][1]['value']);good=str(b['documents'][0]['value'])
   assert (wrong in nums)==(q['condition']=='LITERAL')
   if q['condition']=='RESOLVED':assert wrong not in text
   assert good not in nums
   descriptors.append({'query_id':q['query_id'],'condition':q['condition'],'query_chars':len(text),'regex_tokens':len(re.findall(r'\d+|[A-Za-z]+',text)),
    'excluded_endpoint_complete_token':wrong in nums,'excluded_endpoint_substring':wrong in text,'correct_value_complete_token':good in nums,
    'numeric_tokens':nums,'residual_cues':'Other endpoint, arithmetic operands, digits and possible subword matches remain; no full cue-removal claim'})
 assert len(blocks)==(4 if split=='DEV' else 12)
 assert collections.Counter(b['excluded_endpoint'] for b in blocks)=={'upper':len(blocks)//2,'lower':len(blocks)//2}
 assert collections.Counter(b['arithmetic'] for b in blocks)=={'add':len(blocks)//2,'sub':len(blocks)//2}
 folder=RUN/'data'/split;savej(folder/'blocks.jsonl',blocks)
 records=[dict(block_id=b['block_id'],template_id=b['template_id'],**q,candidates=[d['text'] for d in b['documents'][:2]]) for b in blocks for q in b['queries']]
 savej(RUN/('control_dev.jsonl' if split=='DEV' else 'control_eval.jsonl'),records)
 payloads=[];index=[]
 for b in blocks:
  for q in b['queries']:
   for orientation in [0,1]:
    ds=b['documents'][:2] if orientation==0 else list(reversed(b['documents'][:2]))
    p={'query':q['text'],'candidates':[d['text'] for d in ds]};payloads.append(p)
    index.append({'query_id':q['query_id'],'block_id':b['block_id'],'template_id':b['template_id'],'condition':q['condition'],'wording':q['wording'],'orientation':orientation,'position_to_role':[d['private_role'] for d in ds],'payload_sha256':digest(p)})
 savej(folder/'model_inputs.jsonl',payloads);savej(folder/'private_payload_index.jsonl',index)
 savej(folder/'score_visible_corpus.jsonl',[{'text':d['text']} for b in blocks for d in b['documents']])
 savej(folder/'lexical_overlap_descriptors.jsonl',descriptors)
 save(folder/'MECHANICAL_QA.json',{'status':'PASS','split':split,'blocks':len(blocks),'queries':len(records),'pair_answer_uniqueness':True,'auxiliary_fails':True,'exact_arithmetic_equivalence':True,'fixed_candidate_texts_across_cells':True,'all_cells_complete':True,'body_role_leakage':False,'raw_or_normalized_duplicates':0,'numeric_redaction_structure_reuse':'Expected within each linguistic template; exploratory shared-template design','old_comparison_files_checked':[str(p) for p in oldfiles],'nuisance_allocation_actual':[{'block_id':b['block_id'],'excluded':b['excluded_endpoint'],'operation':b['arithmetic']} for b in blocks],'generated_at_utc':now().isoformat(),'no_new_score_selection':True})
 checkpoint(split+'_BUILT',**{f'new_{split}_blocks':len(blocks)},material_repair_campaigns=0)
 packets(split,'semantic')
 print(json.dumps({'split':split,'blocks':len(blocks),'queries':len(records),'mechanical':'PASS','packets_ready':True}))

SEM_SCHEMA={'cases':[{'id':'packet case id','constraint':{'lower':0,'upper':0,'include_lower':True,'include_upper':False,'property':'parsed property'},'satisfaction':[{'id':'candidate id','satisfies':'true|false|UNKNOWN'}],'selected':['zero/one/two candidate ids'],'clarity':'CLEAR|AWKWARD_BUT_CLEAR|AMBIGUOUS','evidence':'brief quote plus exact arithmetic/comparator checks','verdict':'PASS|REJECT|UNCERTAIN','issues':[]}]}
DES_SCHEMA={'blocks':[{'id':'packet block id','verdict':'PASS_LIMITED|REJECT|UNCERTAIN','equivalence':True,'fixed_candidates':True,'unique_pair_answer':True,'auxiliary_fails':True,'evidence':'short check','issues':[]}],'limitations':['short']}

def packets(split,kind):
 blocks=rows(RUN/'data'/split/'blocks.jsonl')
 if kind=='design' and read(RUN/f'SEMANTIC_{split}.json')['status']!='PASS':raise RuntimeError('Initial raw split not fully clean and sealed')
 for role in ['A','B']:
  rng=random.Random(SEED+(split=='EVAL')*177+(role=='B')*51+(kind=='design')*63)
  mapping={};groups=[]
  if kind=='semantic':
   shuffled=list(blocks);rng.shuffle(shuffled);size=4 if split=='DEV' else 6
   for cell in range(4):
    for start in range(0,len(shuffled),size):
     group=[]
     for b in shuffled[start:start+size]:
      # A different random cell permutation for each block; no sibling in one context.
      br=random.Random(SEED+(role=='B')*317+int(hashlib.sha256(b['block_id'].encode()).hexdigest()[:8],16))
      order=list(range(4));br.shuffle(order);q=b['queries'][order[cell]]
      cid='q'+hashlib.sha256((split+role+q['query_id']).encode()).hexdigest()[:12]
      ds=list(b['documents'][:2]);rng.shuffle(ds)
      cands=[];cm={}
      for d in ds:
       did='d'+hashlib.sha256((role+q['query_id']+d['text']).encode()).hexdigest()[:12]
       cands.append({'id':did,'text':d['text']});cm[did]=d['private_role']
      group.append({'id':cid,'query':q['text'],'candidates':cands})
      mapping[cid]={'query_id':q['query_id'],'block_id':b['block_id'],'candidate_map':cm}
     rng.shuffle(group);groups.append(group)
  else:
   shuffled=list(blocks);rng.shuffle(shuffled)
   for start in range(0,len(shuffled),4):
    group=[]
    for b in shuffled[start:start+4]:
     bid='b'+hashlib.sha256((role+b['block_id']).encode()).hexdigest()[:12]
     group.append({'id':bid,'queries':[{'condition':q['condition'],'wording':q['wording'],'text':q['text']} for q in b['queries']],
      'candidates':[{'id':f'c{i}','text':d['text']} for i,d in enumerate(b['documents'][:2])],
      'auxiliary':b['documents'][2]['text']})
     mapping[bid]={'block_id':b['block_id']}
    groups.append(group)
  for i,group in enumerate(groups,1):
   job=f'{split}_{kind}_{role}_{i:02d}'
   packet={'task':('Independently solve each query' if role=='A' else 'Independently solve and seek comparator/boundary/arithmetic or ambiguity counterexamples') if kind=='semantic' else 'Independently examine full matched blocks for semantic equivalence,fixed items,actual intervention,pair uniqueness,auxiliary exclusion and narrow interpretable scope',
    'instructions':'Read only this packet; no parent/sibling files, old scores, source labels, or other reviews. Return exactly one compact JSON final answer; no file writes. Allow zero/one/two selections and UNKNOWN satisfaction. Do not infer gold positions. Do not request a pure mechanism experiment.',
    'output_schema':SEM_SCHEMA if kind=='semantic' else DES_SCHEMA,
    'cases' if kind=='semantic' else 'blocks':group}
   if kind=='design':packet['scope']='Specified excluded endpoint Arabic numeral vs exact integer arithmetic expression; length/arithmetic changes included; complete numeral token removed but other cues remain; shared templates exploratory'
   save(RUN/'packets'/f'{job}.json',packet)
  save(RUN/'private'/f'{split}_{kind}_{role}_map.json',mapping)
 print('packets',split,kind)

def seal_semantic(split):
 blocks=rows(RUN/'data'/split/'blocks.jsonl');lookup={q['query_id']:(b,q) for b in blocks for q in b['queries']};answers={};receipts=[];issues=[]
 for role in ['A','B']:
  mp=read(RUN/'private'/f'{split}_semantic_{role}_map.json');roleout={}
  paths=sorted((RUN/'packets').glob(f'{split}_semantic_{role}_*.json'))
  for path in paths:
   job=path.stem;rawpath=RUN/'reviews/raw'/f'{job}.txt'
   if not rawpath.exists():raise RuntimeError('Missing '+job)
   text=rawpath.read_text(encoding='utf-8');obj=json.loads(text)
   expected={c['id'] for c in read(path)['cases']};cases=obj['cases']
   if {c['id'] for c in cases}!=expected or len(cases)!=len(expected):raise RuntimeError('Format coverage '+job)
   receipts.append({'job':job,'packet_sha256':sha(path),'raw_sha256':sha(rawpath),'native_task':job.lower(),'model_revision':'UNKNOWN','full_tool_trace':'UNKNOWN','format':('native final review JSON preserved by coordinator' if split=='DEV' else 'complete reviewer-authored structured payload exclusively saved; final metadata receipt separately retained; prewrite trace UNKNOWN')})
   for c in cases:
    mm=mp[c['id']];qid=mm['query_id'];b,q=lookup[qid]
    if c['verdict'] not in ['PASS','REJECT','UNCERTAIN'] or c['clarity'] not in ['CLEAR','AWKWARD_BUT_CLEAR','AMBIGUOUS']:raise RuntimeError('Format enum '+job)
    cm=mm['candidate_map'];sats={z['id']:({'true':True,'false':False}.get(z['satisfies'],z['satisfies']) if isinstance(z['satisfies'],str) else z['satisfies']) for z in c['satisfaction']}
    if set(sats)!=set(cm) or any(v not in [True,False,'UNKNOWN'] for v in sats.values()):raise RuntimeError('Format satisfaction '+job)
    if not set(c['selected'])<=set(cm) or len(set(c['selected']))!=len(c['selected']):raise RuntimeError('Format selection '+job)
    cp=c['constraint'];canonical={'lower':b['lower'],'upper':b['upper'],'include_lower':b['include_lower'],'include_upper':b['include_upper'],'property':b['property']}
    private_selected=[cm[x] for x in c['selected']]
    canonfields=['lower','upper','include_lower','include_upper']
    predicate_match=all(cp[k]==canonical[k] for k in canonfields) and cp['property'].strip().lower()==canonical['property']
    good=c['verdict']=='PASS' and c['clarity']!='AMBIGUOUS' and predicate_match and private_selected==['gold'] and all(v==(cm[k]=='gold') for k,v in sats.items())
    if not good:issues.append({'role':role,'query_id':qid,'case_id':c['id'],'verdict':c['verdict'],'source_predicate_match':predicate_match,'raw_verdict':c,'non_authoritative_canonical':canonical,'reasons':['nonPASS_or_selection_predicate_satisfaction_source_conflict']})
    roleout[qid]=c
    parsed=dict(c,normalized_satisfaction=[{'id':k,'satisfies':v} for k,v in sats.items()],source_query_id=qid,source_block_id=b['block_id'])
    pp=RUN/'reviews/parsed'/f'{job}.jsonl';pp.parent.mkdir(parents=True,exist_ok=True)
    with pp.open('a',encoding='utf-8') as pf:pf.write(json.dumps(parsed,ensure_ascii=False)+'\n')
  if set(roleout)!=set(lookup):raise RuntimeError('Role full coverage')
  answers[role]=roleout
 for qid in lookup:
  aa,bb=answers['A'][qid],answers['B'][qid]
  if any(aa['constraint'][k]!=bb['constraint'][k] for k in ['lower','upper','include_lower','include_upper']):issues.append({'query_id':qid,'reasons':['A_B_predicate_conflict']})
 save(RUN/f'SEMANTIC_{split}.json',{'status':'PASS' if not issues else 'ROUTED_C','queries':len(lookup),'role_judgments':2*len(lookup),'raw_sealed_at_utc':now().isoformat(),'raw_receipts':receipts,'issues':issues,'source_truth':'Checked only after all A/B final responses received; nonauthoritative; conflicts require C'},False)
 checkpoint(split+'_SEMANTIC_SEALED',**{f'{split}_semantic_status':'PASS' if not issues else 'ROUTED_C'})
 print(json.dumps({'split':split,'semantic':'PASS' if not issues else 'ROUTED_C','issues':len(issues)}))
 if not issues:packets(split,'design')

def seal_design(split):
 sem=read(RUN/f'SEMANTIC_{split}.json');assert sem['status']=='PASS'
 blocks=rows(RUN/'data'/split/'blocks.jsonl');issues=[];receipts=[]
 for role in ['A','B']:
  mapping=read(RUN/'private'/f'{split}_design_{role}_map.json');seen=set()
  for path in sorted((RUN/'packets').glob(f'{split}_design_{role}_*.json')):
   job=path.stem;rp=RUN/'reviews/raw'/f'{job}.txt';obj=json.loads(rp.read_text(encoding='utf-8'))
   expected={b['id'] for b in read(path)['blocks']}
   if {x['id'] for x in obj['blocks']}!=expected:raise RuntimeError('Design coverage '+job)
   receipts.append({'job':job,'packet_sha256':sha(path),'raw_sha256':sha(rp),'model_revision':'UNKNOWN','full_tool_trace':'UNKNOWN'})
   for x in obj['blocks']:
    bid=mapping[x['id']]['block_id'];seen.add(bid)
    if x['verdict']!='PASS_LIMITED' or not all(x[k] is True for k in ['equivalence','fixed_candidates','unique_pair_answer','auxiliary_fails']):issues.append({'block_id':bid,'role':role,'judgment':x})
  assert seen=={b['block_id'] for b in blocks}
 result={'status':'PASS' if not issues else 'ROUTED_C','design_status':'PASS_LIMITED' if not issues else 'ROUTED_C','split':split,'semantic_queries':len(blocks)*4,'semantic_role_judgments':len(blocks)*8,'design_blocks':len(blocks),'design_role_judgments':len(blocks)*2,'all_initial_raw_sealed_before_design':True,'raw_receipts':receipts,'issues':issues,'mechanical_QA_sha256':sha(RUN/'data'/split/'MECHANICAL_QA.json'),'semantic_seal_sha256':sha(RUN/f'SEMANTIC_{split}.json'),'sealed_at_utc':now().isoformat(),'material_version':'v001'}
 save(RUN/f'QA_{split}.json',result);checkpoint(split+'_QA_COMPLETE',**{f'{split}_QA_status':result['status']});print(json.dumps({'split':split,'QA':result['status'],'issues':len(issues)}))

def score_lock():
 if active()>=12600:raise RuntimeError('Scoring launch cutoff')
 for split in ['DEV','EVAL']:assert read(RUN/f'QA_{split}.json')['status']=='PASS'
 old=read(ROOT/'stage22/STAGE22_STAGE2_REPAIR_SCORE_LOCK.json');old['target_models']['bm25']['corpus']='All36 unique new EVAL documents,auxiliary included;fixed across conditions'
 files=[RUN/'TOKENIZER_PREFLIGHT.json',RUN/'RUNTIME_IMPORT_PREFLIGHT.json',RUN/'PRE_SCORE_BUDGET.json',RUN/'audit_summary.json',RUN/'REVIEW_TRANSPORT_v002.json',RUN/'FORMAT_COMPATIBILITY_RECORD.json',RUN/'CONTROL_DESIGN_DECISION.md',RUN/'CONTROL_SPEC_LOCK.json',RUN/'control_dev.jsonl',RUN/'control_eval.jsonl',RUN/'QA_DEV.json',RUN/'QA_EVAL.json',RUN/'SEMANTIC_DEV.json',RUN/'SEMANTIC_EVAL.json']
 files+=sorted(p for p in (RUN/'data').rglob('*') if p.is_file())
 files+=sorted(p for p in (RUN/'reviews').rglob('*') if p.is_file())
 files+=sorted(p for p in (RUN/'code').glob('*.py') if p.name not in ['verify_baseline_binding_v001.py'])
 lock={'status':'LOCKED_BEFORE_TARGET_SCORING','created_at_utc':now().isoformat(),'design':'LITERAL_vs_RESOLVED_exact_arithmetic','data_designation':'template_shared_exploratory','DEV_blocks':4,'EVAL_blocks':12,'EVAL_queries':48,'target_models':old['target_models'],'fixed_corpus':'36 unique new EVAL documents,includes auxiliary,same forbothconditions','analysis':read(RUN/'CONTROL_SPEC_LOCK.json')['analysis'],'technical_tolerance_order':1e-4,'no_outcome_driven_selection':True,'no_new_target_scores_observed':True,'active_work_elapsed':active(),'budget_remaining_seconds':14400-active(),'file_locks':[{'path':p.relative_to(RUN).as_posix(),'sha256':sha(p)} for p in files],'inherited_adapter_sha256':sha(ROOT/'tools/local_score.py'),'baseline_binding_sha256':sha(RUN/'BASELINE_BINDING.json')}
 save(RUN/'CONTROL_SCORE_LOCK.json',lock);checkpoint('SCORE_LOCKED',target_scoring_started=False);print('Prospective score lock created.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['build','semantic','design','lock','checkpoint']);p.add_argument('--split',choices=['DEV','EVAL']);a=p.parse_args()
 if a.action=='build':build(a.split)
 elif a.action=='semantic':seal_semantic(a.split)
 elif a.action=='design':seal_design(a.split)
 elif a.action=='lock':score_lock()
 else:print(checkpoint('CHECKPOINT'))