"""Conditional general template repair. No apply without recorded C evidence and scope authorization."""
from __future__ import annotations
import argparse,copy,hashlib,importlib.util,json,re
from fractions import Fraction
from pathlib import Path
S=Path(__file__).resolve().parents[1];ROOT=S.parent;OLD=ROOT/'data/stage2_eval_exploratory/v1';OUT=S/'data/stage2_eval_repair/v002'
spec=importlib.util.spec_from_file_location('audit',S/'tools/audit_tools.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
def jbytes(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(x):return hashlib.sha256(x).hexdigest()
def transform(b):
 out=copy.deepcopy(b)
 assert b['transformation']=='temporal' and b['style']==2
 for q in out['queries']:
  old=q['text']
  if q['wording']==0:
   matches=list(re.finditer(r'Among (.+?) files, retain the one stamped ([^.]+)\.',old));assert len(matches)==1
   m=matches[0];topic,expr=m.groups();new=f'Among {topic} files, retain the one whose recorded calendar year equals {expr}.'
  else:
   matches=list(re.finditer(r'Which (.+?) file bears the stamp ([^?]+)\?',old));assert len(matches)==1
   m=matches[0];topic,expr=m.groups();new=f'Which {topic} file has a recorded calendar year equal to {expr}?'
  assert topic==b['topic'];q['text']=old[:m.start()]+new+old[m.end():]
  # Independent exact calculation from the retained rendered expression.
  if expr.isdigit():value=int(expr)
  else:
   terms=re.fullmatch(r'the result of (\d+) plus (\d+) years',expr);assert terms,expr;value=sum(map(int,terms.groups()))
  assert Fraction(value)==Fraction(b['canonical_predicate']['value'])
  assert q['n']==next(x['n'] for x in b['queries'] if x['query_id']==q['query_id'])
  assert 'stamp' not in q['text'].lower()
 for d in out['model_visible_documents']:
  match=re.fullmatch(r'A date of (\d+) appears on the (.+) entry\.',d['text']);assert match,d['text'];value,topic=match.groups();assert topic==b['topic']
  d['text']=f'The recorded calendar year for the {topic} entry is {value}.'
  pos=d['text'].rfind(value);d['semantic_spans']=[[pos,pos+len(value)]];d['render_path']='stage22_temporal_recorded_calendar_year_clarification_v2'
  f=next(x for x in out['candidate_facts'] if x['candidate_id']==d['candidate_id']);assert Fraction(value)==Fraction(f['display_value'])
 assert out['candidate_facts']==b['candidate_facts'] and out['canonical_predicate']==b['canonical_predicate']
 assert sum(Fraction(f['display_value'])==Fraction(b['canonical_predicate']['value']) for f in out['candidate_facts'])==1
 out['schema_version']='stage2-v2-stage22-temporal-property-clarification';out['repair_provenance']={'status':'post_score_repaired_exploratory','root_cause':'uniform temporal property/anchor clarification','prior_block_id':b['block_id'],'numeric_truth_and_factor_allocation_unchanged':True}
 out['validation_records'].append({'checker':'stage22_exact_preserved_expression_and_explicit_calendar_year_property','independent_reviewer':False,'status':'PASS'})
 return out

def build(auth_path):
 auth=a.read(Path(auth_path));assert auth['accepted_by']=='root' and auth['root_cause']=='temporal_stamp_date_property_ambiguity'
 if OUT.exists():raise FileExistsError('New version must be exclusive; no overwrite')
 ledger=a.readj(S/'adjudication_ledger.jsonl');ids=set(auth['C_issue_ids']);records=[x for x in ledger if x['issue_id'] in ids]
 assert ids and {x['issue_id'] for x in records}==ids
 assert all(x['scope']=='full' and x['kind'] in ['semantic','design'] and x['verdict'] in ['CONFIRMED_DEFECT','UNRESOLVED'] for x in records)
 if any(x['verdict']=='UNRESOLVED' for x in records):assert auth['explicit_ambiguity_evidenced'] is True
 old=a.readj(OLD/'blocks.jsonl');affected=[b for b in old if b['transformation']=='temporal' and b['style']==2];assert len(affected)==3
 bids={b['block_id'] for b in affected};assert set(auth['affected_blocks'])==bids
 assert all(x['block_id'] in bids for x in records)
 changed={b['block_id']:transform(b) for b in affected};full=[changed.get(b['block_id'],b) for b in old]
 assert len(full)==48 and sum(len(b['queries']) for b in full)==336
 assert all(x==y for x,y in zip(old,full) if x['block_id'] not in bids)
 # Uniformly rebuild all affected siblings; retain every unmodified block's original serialized line.
 lines=(OLD/'blocks.jsonl').read_text(encoding='utf-8-sig').splitlines();newlines=[]
 for line in lines:
  b=json.loads(line);newlines.append(jbytes(changed[b['block_id']]).decode() if b['block_id'] in bids else line)
 OUT.mkdir(parents=True);(OUT/'blocks.jsonl').write_text('\n'.join(newlines)+'\n',encoding='utf-8')
 a.writej(OUT/'affected_blocks.jsonl',list(changed.values()))
 oldp=a.readj(OLD/'model_inputs.jsonl');oldix=a.readj(OLD/'private_payload_index.jsonl');payloads=[];index=[];querymap={q['query_id']:q for b in full for q in b['queries']};docmap={d['candidate_id']:d['text'] for b in full for d in b['model_visible_documents']}
 for ordinal,(p,ix) in enumerate(zip(oldp,oldix)):
  new={'query':querymap[ix['query_id']]['text'],'candidates':[docmap[x] for x in ix['position_to_candidate_id']]};ni=copy.deepcopy(ix);ni['payload_sha256']=digest(jbytes(new));payloads.append(new);index.append(ni)
  if ix['block_id'] not in bids:assert p==new and ix==ni
  else:assert p!=new
 a.writej(OUT/'model_inputs.jsonl',payloads);a.writej(OUT/'private_payload_index.jsonl',index)
 texts=sorted({d['text'] for b in full for d in b['model_visible_documents']});assert len(texts)==144
 a.writej(OUT/'score_visible_corpus.jsonl',[{'text':t} for t in texts])
 ords=[i for i,x in enumerate(index) if x['block_id'] in bids];assert len(ords)==48
 assert len(oldp)==len(payloads)==672
 scope={'bm25':list(range(672)),'bge_small':ords,'e5_small':ords,'minilm_ce':ords}
 manifest={'created_at_utc':a.now(),'dataset_version':'stage2-eval-v2-stage22-temporal-property','designation':'post_score_repaired_exploratory','source_version':'stage2-eval-v1','repair_attempt_per_root_cause':1,'material_campaign':True,'affected_blocks':sorted(bids),'affected_queries':24,'full_queries':336,'full_blocks':48,'fresh_QA_scope':'full_repair','carry_forward_blocks':45,'carry_forward_queries':312,'numeric_truth_and_candidate_ids_unchanged':True,'all_unaffected_payloads_identical':True,'rerun_request_ordinals':scope,'new_logical_ranking_requests':sum(map(len,scope.values())),'BM25_dependency':'Entire new split corpus changes; all 672 BM25 two-order requests rerun. Other models depend only on query/document pairs.','authorization_sha256':a.sha(Path(auth_path)),'C_records':records,'old_source_hashes':{f:a.sha(OLD/f) for f in ['blocks.jsonl','model_inputs.jsonl','private_payload_index.jsonl','score_visible_corpus.jsonl']},'new_source_hashes':{f:a.sha(OUT/f) for f in ['blocks.jsonl','affected_blocks.jsonl','model_inputs.jsonl','private_payload_index.jsonl','score_visible_corpus.jsonl']},'target_scores_used_for_repair':False,'fresh_review_status':'PENDING'}
 a.write(OUT/'REPAIR_MANIFEST.json',manifest)
 registry=S/'private/audit_scope_registry.json';mapping=a.read(registry) if registry.exists() else {};assert 'full_repair' not in mapping;mapping['full_repair']={'source':str((OUT/'affected_blocks.jsonl').relative_to(S)).replace('\\','/')};registry.parent.mkdir(parents=True,exist_ok=True);registry.write_text(json.dumps(mapping,indent=2)+'\n',encoding='utf-8')
 a.write(S/'TEMPORAL_PROPERTY_REPAIR_REGRESSION.json',{'status':'PASS','queries_checked':24,'documents_checked':9,'original_expressions_preserved_and_exactly_recalculated':True,'all_other_blocks_and_payloads_identical':True,'new_full_corpus_documents':144,'source_hash':a.sha(OUT/'blocks.jsonl'),'fresh_agent_QA_not_replaced_by_regression':True})
 with (S/'repair_history.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'created_at_utc':a.now(),'kind':'POST_SCORE_VERSIONED_TEMPLATE_PROPERTY_CLARIFICATION','manifest_sha256':a.sha(OUT/'REPAIR_MANIFEST.json'),'C_issue_ids':sorted(ids),'affected_blocks':sorted(bids),'new_version':manifest['dataset_version'],'target_scores_used_for_repair':False},separators=(',',':'))+'\n')
 print(json.dumps({'new_version':manifest['dataset_version'],'fresh_QA_queries':24,'new_logical_ranking_requests':manifest['new_logical_ranking_requests']}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--authorization',required=True);x=p.parse_args();build(x.authorization)
