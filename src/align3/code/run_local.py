"""Local-only sequential execution with immutable receipts; no remote clients."""
from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib,sys,os,time
R=Path(__file__).resolve().parents[1]
PY=r'<LOCAL_HOME>\Documents\ChatGPT\捉摸\.venv\Scripts\python.exe'
KEYS=['bm25','bge_small','e5_small','minilm_ce']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
mode=sys.argv[1]
os.environ.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='8',MKL_NUM_THREADS='8',TEMP=str(R/'cache'),TMP=str(R/'cache'))
if mode=='score':
 lock=json.loads((R/'CONTROL_LOCK.json').read_text(encoding='utf-8'))
 assert lock['status']=='LOCKED_BEFORE_TARGET_SCORING'
 for row in lock['file_locks']:assert sha(R/row['path'])==row['sha256'],row['path']
receipt={'mode':mode,'start_utc':datetime.now(timezone.utc).isoformat(),'attempts':[],'paid_API_calls':0,'downloads':0,'one_model_at_a_time':True,'credential_variables_read':False}
for key in KEYS:
 assert datetime.now(timezone.utc)<datetime(2026,10,1,5,46,tzinfo=timezone.utc)
 args=[PY,'-X','utf8','-B',str(R/'code/score_local.py'),'--model',key]
 if mode=='precheck':args+=['--precheck']
 else:args+=['--input-sha256',lock['input_sha256'],'--corpus-sha256',lock['corpus_sha256']]
 so=R/'scoring'/f'{mode}_{key}.stdout.txt';se=R/'scoring'/f'{mode}_{key}.stderr.txt'
 start=time.perf_counter()
 with so.open('x',encoding='utf-8') as fo,se.open('x',encoding='utf-8') as fe:p=subprocess.run(args,stdout=fo,stderr=fe,cwd=R,shell=False)
 attempt={'model':key,'exit_code':p.returncode,'elapsed_seconds':time.perf_counter()-start,'stdout_sha256':sha(so),'stderr_sha256':sha(se)}
 receipt['attempts'].append(attempt);print(json.dumps(attempt),flush=True)
 if p.returncode:break
receipt['end_utc']=datetime.now(timezone.utc).isoformat();receipt['status']='COMPLETE' if len(receipt['attempts'])==4 and all(a['exit_code']==0 for a in receipt['attempts']) else 'TECHNICAL_FAILURE'
with (R/'scoring'/f'{mode}_execution_receipt.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
if receipt['status']!='COMPLETE':raise SystemExit(2)
