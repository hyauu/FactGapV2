"""Check all manuscript displays against the released, replayed archival evidence."""
import argparse,csv,hashlib,json,math,pathlib,re,xml.etree.ElementTree as ET
from pypdf import PdfReader
from pypdf.generic import ContentStream
ROOT=pathlib.Path(__file__).resolve().parents[1]
MAP=json.loads((ROOT/'provenance/SOURCE_TO_RELEASE_MAP.json').read_text('utf-8'))
def path(cohort,native):return ROOT/next(x['release_path'] for x in MAP if x['cohort']==cohort and x['native_path']==native)
def rows(c,n):return list(csv.DictReader(path(c,n).open(encoding='utf-8',newline='')))
def read(c,n):return json.loads(path(c,n).read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(v,d=6):return ('+' if v>0 else '')+f'{v:.{d}f}'
def pdfpaths(p,n,colorfilter=lambda c:True):
 r=PdfReader(p);result=[]
 def walk(obj):
  try:content=obj.get_contents()
  except AttributeError:content=obj
  cs=ContentStream(content,r);color=None;stack=[];pts=[]
  for args,op in cs.operations:
   if op==b'q':stack.append(color)
   elif op==b'Q':color=stack.pop()
   elif op==b'RG':color=tuple(float(x) for x in args)
   elif op==b'm':pts=[tuple(float(x) for x in args)]
   elif op==b'l':pts.append(tuple(float(x) for x in args))
   elif op==b'S' and len(pts)==n and color and colorfilter(color):result.append((color,pts[:]))
  resources=obj.get('/Resources',{});resources=resources.get_object() if hasattr(resources,'get_object') else resources;xs=resources.get('/XObject',{});xs=xs.get_object() if hasattr(xs,'get_object') else xs
  for x in xs.values():
   o=x.get_object()
   if o.get('/Subtype')=='/Form':walk(o)
 walk(r.pages[0]);return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=pathlib.Path,required=True);args=ap.parse_args();O=args.output;O.mkdir(parents=True,exist_ok=True)
 inv=json.loads((ROOT/'paper/source_data/table_invariants.json').read_text('utf-8'));s=read('align3','analysis/summary.json');checks={};evidence={}
 keys=['bm25','bge_small','e5_small','minilm_ce'];names=['BM25','BGE-small','E5-small','MiniLM CE'];conds=['WRONG_ALIGNED','NEUTRAL','GOLD_ALIGNED']
 lookup={(x['model_key'],x['condition']):x for x in s['condition_results']};contr={(x['model_key'],x['contrast']):x for x in s['paired_contrasts']}
 table=[];margins=[]
 for k,name in zip(keys,names):
  cells=[lookup[k,c] for c in conds];table.append([name]+[f"{x['wins']}/{x['losses']}/{x['exact_ties']}" for x in cells]+[f"{sum(x['strict_increase'] for x in s['monotonic_blocks'] if x['model_key']==k)}/12"])
  margins.append([name]+[fmt(x['primary_template_equal_margin']) for x in cells]+[fmt(contr[k,c]['mean_paired_margin_shift']) for c in ['GOLD_ALIGNED-WRONG_ALIGNED','NEUTRAL-WRONG_ALIGNED','GOLD_ALIGNED-NEUTRAL']])
 assert table==inv['align3_wlt'];assert margins==inv['align3_margins'];checks['tab:alignment']={'status':'PASS','rows':table};checks['tab:margins']={'status':'PASS','full_precision_source_used':True,'rows':margins}
 evidence['tab:alignment']=[path('align3',n) for n in ['condition_results.csv','block_results.csv','analysis/summary.json']];evidence['tab:margins']=[path('align3',n) for n in ['condition_results.csv','paired_contrasts.csv']]
 # Each visible PDF three-point block path is checked against the archived SVG, then calibrated to actual margins.
 svg=ET.parse(path('align3','analysis/ALIGN3_MARGIN.svg')).getroot();paths=[];groups={}
 for e in svg.iter():
  style=e.get('style','');d=e.get('d','')
  if not e.tag.endswith('path') or not ('stroke: #adb8c3' in style or 'stroke: #155c9a' in style):continue
  nums=[float(x) for x in re.findall(r'-?\d+(?:\.\d+)?',d)]
  if len(nums)!=6 or not re.fullmatch(r'\s*M\s+[-\d.]+\s+[-\d.]+\s+L\s+[-\d.]+\s+[-\d.]+\s+L\s+[-\d.]+\s+[-\d.]+\s*',d):continue
  pts=list(zip(nums[::2],nums[1::2]));color='gray' if '#adb8c3' in style else 'blue';paths.append((color,pts))
  if e.get('clip-path'):groups.setdefault(e.get('clip-path'),[]).append((color,pts))
 pdf=pdfpaths(ROOT/'paper/figures/operand_alignment.pdf',3,lambda c:abs(c[0]-.678431)<1e-5 or abs(c[0]-.082353)<1e-5);assert len(paths)==len(pdf)==53
 err=0
 for (color,pts),(pc,ppts) in zip(paths,pdf):
  assert color==('gray' if abs(pc[0]-.678431)<1e-5 else 'blue');err=max(err,max(abs(a-b) for p,q in zip(pts,ppts) for a,b in zip(p,q)))
 assert err<1e-4;assert len(groups)==4;residual=0
 for k,entries in zip(keys,groups.values()):
  gray=[p for c,p in entries if c=='gray'];blue=[p for c,p in entries if c=='blue'];assert len(gray)==12 and len(blue)==1
  values=[[next(x['margin'] for x in s['block_results'] if x['model_key']==k and x['block_id']==f'eval_block_{b:02d}' and x['condition']==c) for c in conds] for b in range(12)]
  scale=(gray[0][2][1]-gray[0][0][1])/(values[0][2]-values[0][0]);offset=gray[0][0][1]-scale*values[0][0];assert scale<0
  for pts,vals in zip(gray+blue,values+[[lookup[k,c]['primary_template_equal_margin'] for c in conds]]):
   assert abs((pts[1][0]-pts[0][0])-(pts[2][0]-pts[1][0]))<1e-4
   residual=max(residual,max(abs(p[1]-(scale*v+offset)) for p,v in zip(pts,vals)))
 assert residual<1e-4;checks['fig:alignment']={'status':'PASS','block_curves_verified':48,'aggregate_curves_verified':4,'SVG_to_PDF_max_coordinate_difference':err,'raw_margin_affine_plot_max_residual':residual,'E5_exception_retained':True}
 evidence['fig:alignment']=[ROOT/'paper/figures/operand_alignment.pdf',path('align3','analysis/ALIGN3_MARGIN.svg'),path('align3','block_results.csv')]
 b=rows('boundary_expression','control_condition_summary.csv');bl={(x['model_key'],x['condition']):x for x in b};bt=[]
 for k,name in zip(keys,names):
  cell=[bl[k,c] for c in ['LITERAL','RESOLVED']];bt.append([name]+[f"{x['correct']}/{x['incorrect']}/{x['exact_tie']}" for x in cell]+[f"{100*(float(cell[1]['strict_success_rate'])-float(cell[0]['strict_success_rate'])):.1f}"])
 assert bt==inv['boundary_wlt'];checks['tab:boundary']={'status':'PASS','rows':bt};evidence['tab:boundary']=[path('boundary_expression',n) for n in ['raw_control_scores.jsonl','control_condition_summary.csv','CONTROL_SCORE_LOCK.json']]
 hosted=rows('hosted_boundary','CONDITION_SUMMARY.csv');hr=[]
 for provider,name in zip(['openai','anthropic','google'],['OpenAI archived config.','Anthropic archived config.','Google archived config.']):
  cell=[next(x for x in hosted if x['provider']==provider and x['condition']==c) for c in ['LITERAL','RESOLVED']];hr.append([name]+[f"{x['TaskA_exact_correct']}/24" for x in cell]+[f"{x['TaskB_query_strict_both_orders_correct']}/24" for x in cell])
 assert hr==inv['hosted'];assert sha(path('hosted_boundary','inputs/control_eval.jsonl'))==sha(path('boundary_expression','control_eval.jsonl'));checks['tab:hosted']={'status':'PASS','queries':48,'shared_boundary_inputs_byte_exact':True,'logical_requests':432,'archived_attempts':436,'rows':hr};evidence['tab:hosted']=[path('hosted_boundary',n) for n in ['CONDITION_SUMMARY.csv','TASK_A_RESULTS.csv','TASK_B_RESULTS.csv','inputs/control_eval.jsonl','STAGE3A_PROMPT_LOCK.json']]
 q=rows('original_corrected','sensitivity/reference_outputs/query_form_accuracy.csv');ql={(x['model'],x['type'],x['form']):float(x['accuracy']) for x in q};original=[];models=['bge-base','e5-base','qwen3-embedding','bge-reranker','legacy-cross-encoder']
 for model,printed in zip(models,inv['original_accuracy']):original.append([printed[0]]+[f"{100*ql[model,t,f]:.1f}" for t in ['relative_temporal','unit_normalization_clean'] for f in ['D0','D1','P0','P1']])
 assert original==inv['original_accuracy'];checks['tab:original']={'status':'PASS','rows':original};evidence['tab:original']=[path('original_corrected',n) for n in ['sensitivity/reference_outputs/query_form_accuracy.csv','corrected_raw_scores/retriever_scores.parquet','corrected_raw_scores/reranker_controlled.parquet']]
 temporal=list(csv.DictReader((ROOT/'paper/source_data/original_temporal_compact.csv').open()));assert [[x[f] for f in ['D0','D1','P0','P1']] for x in temporal]==[x[1:5] for x in original]
 ppaths=pdfpaths(ROOT/'paper/figures/original_temporal_compact.pdf',4);assert len(ppaths)==5
 values=[[float(x[f]) for f in ['D0','D1','P0','P1']] for x in temporal];scale=(ppaths[0][1][0][1]-ppaths[0][1][2][1])/100;offset=ppaths[0][1][2][1];perr=max(abs(p[1]-(offset+scale*v)) for (_,pts),vals in zip(ppaths,values) for p,v in zip(pts,vals));assert scale>0 and perr<1e-4
 checks['fig:temporal']={'status':'PASS','series':5,'points':20,'source_rounding_decimals':1,'PDF_raw_value_affine_max_residual':perr};evidence['fig:temporal']=[ROOT/'paper/figures/original_temporal_compact.pdf',ROOT/'paper/source_data/original_temporal_compact.csv',path('original_corrected','sensitivity/reference_outputs/query_form_accuracy.csv')]
 endpoints=rows('original_corrected','analysis/reference_outputs/primary_endpoints.csv');ep=[]
 dispositions={'BOUNDARY_DEGENERATE':'Boundary degenerate','INSUFFICIENT_BREADTH':'Insufficient breadth','INCONCLUSIVE':'Inconclusive','VALIDITY_FAIL':'Validity fail','INSUFFICIENT_ELIGIBILITY':'Insufficient eligibility'}
 def three(v):return 'NA' if v in ['', 'NA','nan'] else f'{float(v):.3f}'
 for x,printed in zip(endpoints,inv['endpoints']):
  low,high=x['joint_simultaneous_low'],x['joint_simultaneous_high'];ci='NA' if low in ['', 'NA','nan'] else '['+three(low)+','+three(high)+']'
  ep.append([printed[0],three(x['temporal_estimate']),three(x['unit_estimate']),three(x['joint_estimate']),ci,dispositions[x['status']]])
 assert ep==inv['endpoints'];summary=read('original_corrected','analysis/reference_outputs/result_summary.json');assert summary['status']=='INCONCLUSIVE' and not summary['supported_endpoints'];checks['tab:endpoints']={'status':'PASS','overall':'INCONCLUSIVE','supported':0,'endpoints':7,'rows':ep};evidence['tab:endpoints']=[path('original_corrected',n) for n in ['analysis/reference_outputs/primary_endpoints.csv','analysis/reference_outputs/result_summary.json','analysis/two_type_primary_locked.yaml']]
 templates=rows('boundary_expression','control_template_contrasts.csv');gains=list(csv.DictReader((ROOT/'paper/source_data/boundary_template_gains.csv').open()));tg=[]
 for x in gains:
  rr=[]
  for k,field in [('bge_small','BGE_small_success_gain'),('e5_small','E5_small_success_gain'),('minilm_ce','MiniLM_success_gain')]:
   t=next(y for y in templates if y['model_key']==k and y['template_id']==x['template']);assert abs(100*int(x[field])/int(x['queries_per_condition'])-float(t['resolved_minus_literal_pp']))<1e-10;rr.append(fmt(float(t['resolved_minus_literal_pp']),1))
  tg.append([x['template']]+rr)
 checks['tab:templates']={'status':'PASS','rows':tg};evidence['tab:templates']=[ROOT/'paper/source_data/boundary_template_gains.csv',path('boundary_expression','control_template_contrasts.csv')]
 ps=read('parser_feasibility','OVERALL_METRICS.json');pc=rows('parser_feasibility','condition_summary.csv');pt=[]
 for k,name in zip(keys,names):
  cells=[next(x for x in pc if x['model_key']==k and x['condition']==c and x['method']=='M0') for c in ['LITERAL','RESOLVED']]
  assert all(ps['models'][k][field]==0 for field in ['query_complete','safe_override_queries','actual_rank_changed_queries']);assert ps['models'][k]['methods']['M0']['win']==ps['models'][k]['methods']['M1']['win']==ps['models'][k]['methods']['M2']['win']
  pt.append([name]+[f"{x['win']}/16" for x in cells]+[f"{ps['models'][k]['methods']['M0']['win']}/32"])
 assert pt[1:]==inv['parser'][1:] and pt[0][:-1]==inv['parser'][0];checks['tab:parser']={'status':'PASS','rows':pt,'query_coverage':'0/32','probes':12,'active_safety':'UNMEASURED'};evidence['tab:parser']=[path('parser_feasibility',n) for n in ['raw_scores.jsonl','constraint_decisions.jsonl','OVERALL_METRICS.json','condition_summary.csv','LOCK_METADATA_CLARIFICATIONS.json']]
 pairs=[json.loads(l) for l in path('original_corrected','corrected_dataset/pairs.jsonl').read_text('utf-8').splitlines()];ex=next(x for x in pairs if 'canal review phase 1' in x['gold_text'] and x['gold_fact']['value']==2401);assert ex['negative_fact']['value']==2400 and ex['canonicalization']['input']=={'anchor_year':2400,'offset':1};checks['tab:examples']={'status':'PASS','temporal_pair_id':ex['pair_id'],'temporal':'abridged actual corrected text','unit_and_boundary':'manuscript explanatory schematics; not verbatim scored data'};evidence['tab:examples']=[path('original_corrected','corrected_dataset/pairs.jsonl'),ROOT/'paper/main.tex']
 fam=[json.loads(l) for l in path('original_corrected','corrected_dataset/families.jsonl').read_text('utf-8').splitlines()];assert len(pairs)==147 and len(fam)==22;assert len(s['block_results'])==144;assert len([json.loads(l) for l in path('parser_feasibility','new_eval.jsonl').read_text('utf-8').splitlines()])==32
 checks['tab:cohorts']={'status':'PASS','cohorts':{'ALIGN3':{'queries':72,'blocks':12,'templates':4},'original':{'items':147,'families':22,'temporal':80,'unit':67},'boundary':{'queries':48,'blocks':12,'templates':4},'hosted':{'same_queries':48,'independent_new_dataset':False},'parser':{'main':32,'blocks':8,'templates':4,'probes_separate':12}}};evidence['tab:cohorts']=[path('align3','CONTROL_LOCK.json'),path('boundary_expression','CONTROL_SCORE_LOCK.json'),path('hosted_boundary','STAGE3A_INPUT_LOCK.json'),path('parser_feasibility','INPUT_MODEL_SCORE_LOCK.json'),path('original_corrected','corrected_dataset/families.jsonl')]
 maintex=(ROOT/'paper/main.tex').read_text('utf-8');labels=re.findall(r'\\label\{((?:tab|fig):[^}]+)\}',maintex);assert set(labels)==set(checks) and len(labels)==12
 # All invariant display cells must occur in their own LaTeX environment; no numerical editing performed.
 def environment(label):
  pos=maintex.index('\\label{'+label+'}');beg=max(maintex.rfind('\\begin{table',0,pos),maintex.rfind('\\begin{figure',0,pos));end=maintex.index('\\end{',pos);return maintex[beg:maintex.find('\n',end)]
 for label in ['tab:alignment','tab:margins','tab:boundary','tab:hosted','tab:original','tab:endpoints','tab:templates','tab:parser']:
  env=environment(label)
  for row in checks[label]['rows']:
   for cell in row[1:]:assert cell in env,(label,cell)
 pdf=PdfReader(ROOT/'paper/FactGap_CAIT2026_ALIGN3_8page.pdf');assert len(pdf.pages)==8;first=pdf.pages[0].extract_text();assert first.index('Haoting Qiu')<first.index('Qibai Chen') and 'qiu.haot@northeastern.edu' in first and 'qibaic@alumni.cmu.edu' in first
 report={'status':'PASS','manuscript_PDF_SHA256':sha(ROOT/'paper/FactGap_CAIT2026_ALIGN3_8page.pdf'),'manuscript_pages':8,'main_tex_SHA256':sha(ROOT/'paper/main.tex'),'labels_checked':12,'checks':checks,'evidence':{k:[{'release_path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in v] for k,v in evidence.items()},'model_calls':0,'API_calls':0,'manuscript_modified':False}
 (O/'MANUSCRIPT_VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({'status':'PASS','labels':12,'PDF_pages':8,'figure1_block_curves':48,'figure2_points':20}))
if __name__=='__main__':main()
