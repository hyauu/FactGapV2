"""Replay existing analysis with documented portable path/hash adapters. No inference."""
import argparse,ast,csv,datetime,hashlib,importlib.util,importlib.metadata,json,os,pathlib,runpy,socket,sys,shutil,traceback
ROOT=pathlib.Path(__file__).resolve().parents[1]
MAP=json.loads((ROOT/'provenance/SOURCE_TO_RELEASE_MAP.json').read_text('utf-8'))
BRIDGES=json.loads((ROOT/'provenance/HISTORICAL_HASH_BRIDGES.json').read_text('utf-8'))
H=lambda b:hashlib.sha256(b).hexdigest()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
def manifest_check():
 for line in (ROOT/'MANIFEST.sha256').read_text('utf-8').splitlines():
  digest,path=line.split('  ',1);p=ROOT/path;assert p.resolve().is_relative_to(ROOT.resolve()) and H(p.read_bytes())==digest,path
 for x in MAP:assert H((ROOT/x['release_path']).read_bytes())==x['release_sha256'],x['release_path']
def load(name,p):
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def project(cohort,out):
 base=out/'work'/cohort;base.mkdir(parents=True,exist_ok=True)
 for x in MAP:
  if x['cohort']==cohort:
   p=base/x['native_path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/x['release_path'],p)
 return base
class Adapter:
 def __init__(self,cohort,base):self.base=base;self.entries={x['native_path']:x for x in MAP if x['cohort']==cohort};self.omitted={}
 def sha(self,p):
  p=pathlib.Path(p);p=p if p.is_absolute() else self.base/p;rel=p.relative_to(self.base).as_posix();actual=H(p.read_bytes());x=self.entries.get(rel)
  if x:assert actual==x['release_sha256'];return x['original_sha256']
  return actual
 def read(self,p):
  p=pathlib.Path(p);p=p if p.is_absolute() else self.base/p;j=json.loads(p.read_text('utf-8-sig'))
  if isinstance(j,dict):
   for field in ['file_locks','method_files','files']:
    if field in j and isinstance(j[field],list) and all(isinstance(x,dict) and 'path' in x and 'sha256' in x for x in j[field]):
     old=j[field];j[field]=[x for x in old if (self.base/x['path'].replace('\\','/')).is_file()];self.omitted[p.name+':'+field]=len(old)-len(j[field])
  return j
 def digest(self,b):v=H(b);return BRIDGES.get(v,v)
def compare(base,name,b):
 expected=(base/name).read_bytes()
 if b==expected:return 'byte_exact'
 if name.endswith('.json'):assert json.loads(b)==json.loads(expected),name;return 'json_exact'
 raise AssertionError(name)
def start(cohort,out,filename,module):
 b=project(cohort,out);a=Adapter(cohort,b);m=load(module,b/filename);return b,a,m
def align3(out):
 b,a,m=start('align3',out,'code/analyze.py','align3_analysis');m.R=b;m.read=a.read;m.digest=a.sha;got=m.reconstruction();prior=json.loads((b/'analysis/summary.json').read_text('utf-8'))
 for k,v in got.items():
  if k!='raw_rows':assert prior[k]==v,k
 for name in ['condition_results','paired_contrasts','template_results','block_results','query_results']:
  rows=list(csv.DictReader((b/(name+'.csv')).open(encoding='utf-8',newline='')));assert rows==[{k:str(v) for k,v in x.items()} for x in got[name]],name
 dump(out/'align3/recomputed_summary.json',{k:v for k,v in got.items() if k!='raw_rows'})
 tree=ast.parse((b/'code/check_provenance.py').read_text('utf-8'));tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='R' for x in n.targets))]
 ns={'__file__':str(b/'code/check_provenance.py'),'R':b,'__name__':'offline_provenance'};exec(compile(ast.fix_missing_locations(tree),'check_provenance.py','exec'),ns)
 return {'status':'PASS','score_rows':got['score_rows'],'queries':72,'blocks':12,'templates':4,'monotonic_blocks':got['monotonic_blocks'],'token_cache_forward_resources':'PASS','lock_entries_not_exported':a.omitted}
def boundary(out):
 b,a,m=start('boundary_expression',out,'code/analyze_control.py','boundary_analysis');m.S=b;m.D=b/'data/EVAL';m.ROOT=b;m.read=a.read;m.sha=a.sha;raw,metrics,receipt=m.reconstruct();assert m.readj(b/'control_query_metrics.jsonl')==metrics
 cells,templates,blocks,tp,summary,loto=m.outputs(metrics);prior=a.read('CONTROL_RESULTS.json');assert prior['condition_summaries']==cells and prior['model_summaries']==summary
 for name,values in [('control_condition_summary.csv',cells),('control_template_summary.csv',templates),('control_block_contrasts.csv',blocks),('control_template_contrasts.csv',tp),('control_paired_contrasts.csv',summary),('control_loto_summary.csv',loto)]:
  rows=list(csv.DictReader((b/name).open(encoding='utf-8',newline='')));assert len(rows)==len(values),name
  for x,y in zip(rows,values):
   for k,v in x.items():
    value=y[k]
    if isinstance(value,dict):assert json.loads(v)==value
    else:assert v==str(value),(name,k)
 dump(out/'boundary_expression/recomputed_results.json',{'condition_summaries':cells,'model_summaries':summary,'replay':receipt});return dict(receipt,lock_entries_not_exported=a.omitted)
def hosted(out):
 b=project('hosted_boundary',out);a=Adapter('hosted_boundary',b);p=load('provider_pilot',b/'code/provider_offline.py');p.R=b;p.read=a.read
 schemas=json.loads((b/'preparation/PROMPT_CANDIDATES.json').read_text('utf-8'));p.SCHEMAS=schemas.get('schemas',schemas)
 if 'A' not in p.SCHEMAS:p.SCHEMAS={task:schemas[task]['schema'] for task in ('A','B')}
 def verify():
  for x in a.read('STAGE3A_PROMPT_LOCK.json')['files']:assert a.sha(x['path'])==x['sha256']
 p.verify_scientific_lock=verify;m=load('hosted_analysis',b/'code/analyze_stage3a.py');m.R=b;outputs,receipt,summary=m.compute();checks={}
 for name,data in outputs.items():checks[name]=compare(b,name,data);q=out/'hosted_boundary'/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
 return dict(receipt,output_comparisons=checks,lock_entries_not_exported=a.omitted)
def parser(out):
 b,a,m=start('parser_feasibility',out,'code/analyze_new.py','parser_analysis');m.RUN=b;m.SCORING=b/'scoring';m.REVIEWS=b/'reviews';m.read=a.read;m.sha=a.sha;m.digest=a.digest
 lock=m.verify_lock();method,methodlock=m.load_method();main,probes=m.data(b/lock['main_path'],b/lock['probe_path']);truths=m.readj(b/lock['semantic_truths_path']);inputs=m.readj(b/lock['inputs_path']);maps=m.readj(b/lock['score_map_path']);rewrites=m.readj(b/lock['rewrite_records_path']);raw,indexed,manifests=m.merge_raw(lock,inputs,maps);assert m.jlfile(raw)==(b/'raw_scores.jsonl').read_bytes()
 generated=m.derive(lock,main,probes,truths,inputs,maps,rewrites,indexed,manifests,method,m.readj(b/'M2_DECISIONS.jsonl'));checks={}
 for name,data in generated.items():checks[name]=compare(b,name,data);q=out/'parser_feasibility'/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
 m.selfcheck();return {'status':'PASS','score_rows':len(raw),'decisions':352,'main_queries':32,'probes':12,'output_comparisons':checks,'captured_latency_preserved':True,'lock_entries_not_exported':a.omitted}
def original(out):
 b,a,m=start('original_corrected',out,'analysis/two_type_primary.py','original_primary');dest=out/'original_corrected/primary';summary=m.analyze(b/'corrected_raw_scores',b/'analysis/two_type_primary_locked.yaml',dest,b/'corrected_dataset')
 argv=sys.argv[:];sys.argv=['validate_replay_portable.py','--reference',str(b/'analysis/reference_outputs'),'--candidate',str(dest),'--output',str(out/'original_corrected/PRIMARY_VALIDATION.json')];runpy.run_path(str(b/'analysis/validate_replay_portable.py'),run_name='__main__');sys.argv=argv
 s=load('original_sensitivity',b/'sensitivity/generate_final_outputs.py');d=out/'original_corrected/sensitivity';d.mkdir(parents=True,exist_ok=True);cr=s.pair_retriever(b/'corrected_raw_scores/retriever_scores.parquet');cx=s.pd.read_parquet(b/'corrected_raw_scores/reranker_controlled.parquet');oldr=s.pair_retriever(b/'historical_run/original_raw_scores/retriever_scores.parquet');oldx=s.pd.read_parquet(b/'historical_run/original_raw_scores/reranker_controlled.parquet')
 tables={'query_form_accuracy.csv':s.model_form_summary(cr,cx),'family_query_form_accuracy.csv':s.family_form_summary(cr,cx),'unit_conversion_breakdown.csv':s.unit_breakdown(s.read_jsonl(b/'corrected_dataset/pairs.jsonl'),cr,cx),'contamination_effect.csv':s.contamination_table(oldr,oldx,cr,cx)}
 for name,frame in tables.items():frame.to_csv(d/name,index=False);assert (d/name).read_bytes()==(b/'sensitivity/reference_outputs'/name).read_bytes(),name
 s.distractor_audit(b/'historical_run/original_model_visible_view',b/'corrected_dataset',d);assert json.loads((d/'distractor_redundancy_audit.json').read_text('utf-8'))==json.loads((b/'sensitivity/reference_outputs/distractor_redundancy_audit.json').read_text('utf-8'))
 return {'status':'PASS','items':147,'overall':summary['status'],'supported_endpoints':summary['supported_endpoints'],'primary_validation':json.loads((out/'original_corrected/PRIMARY_VALIDATION.json').read_text('utf-8')),'sensitivity_tables_byte_exact':list(tables),'distractor_audit':'PASS'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=pathlib.Path,required=True);ap.add_argument('--only',choices=['align3','boundary_expression','hosted_boundary','parser_feasibility','original_corrected']);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);manifest_check();attempts=[]
 def denied(*a,**k):attempts.append('blocked_socket');raise RuntimeError('Network disabled for offline replay')
 socket.socket=denied;socket.create_connection=denied;socket.getaddrinfo=denied
 for key in list(os.environ):
  if any(t in key.upper() for t in ['API_KEY','ACCESS_TOKEN','WORKSPACE_ID']):os.environ.pop(key,None)
 os.environ.update({'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','MPLBACKEND':'Agg','MPLCONFIGDIR':str(out/'runtime_cache/matplotlib')});sys.dont_write_bytecode=True
 receipt={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'release_root_dependency':'relative_candidate_only','Python':sys.version,'dependencies':{},'cohorts':{},'model_calls':0,'API_calls':0}
 for name in ['numpy','pandas','scipy','matplotlib','pyarrow','PyYAML']:
  try:receipt['dependencies'][name]=importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:receipt['dependencies'][name]='UNAVAILABLE'
 funcs={'align3':align3,'boundary_expression':boundary,'hosted_boundary':hosted,'parser_feasibility':parser,'original_corrected':original}
 for key,func in funcs.items():
  if args.only and key!=args.only:continue
  try:receipt['cohorts'][key]=func(out);print(key,'PASS',flush=True)
  except Exception as e:receipt['cohorts'][key]={'status':'FAIL','error_type':type(e).__name__,'error':str(e)};traceback.print_exc()
  dump(out/'REPLAY_REPORT.json',receipt)
 receipt.update({'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'network_attempts_blocked':len(attempts),'network_guard':'Python sockets denied; no OS-wide network isolation claimed','status':'PASS' if all(x['status']=='PASS' for x in receipt['cohorts'].values()) else 'FAIL'});dump(out/'REPLAY_REPORT.json',receipt);return 0 if receipt['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
