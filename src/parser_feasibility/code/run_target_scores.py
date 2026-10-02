"""Run the four locked local scorers sequentially. No retries, models, data edits, or API calls in coordinator."""
import pathlib,json,datetime,subprocess,sys,time,hashlib,os
R=pathlib.Path(__file__).resolve().parent.parent
PYTHON=pathlib.Path(r'<LOCAL_HOME>\Documents\ChatGPT\捉摸\.venv\Scripts\python.exe')
KEYS=('bm25','bge_small','e5_small','minilm_ce')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def exclusive(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
lock=json.loads((R/'INPUT_MODEL_SCORE_LOCK.json').read_text(encoding='utf-8'))
assert lock['status']=='LOCKED_BEFORE_TARGET_SCORING'
for row in lock['file_locks']:assert sha(R/row['path'])==row['sha256'],row['path']
assert PYTHON.is_file()
for k in KEYS:assert not (R/'scoring'/f'manifest_{k}.json').exists()
os.environ['PYTHONDONTWRITEBYTECODE']='1';os.environ['PYTHONUTF8']='1'
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['OMP_NUM_THREADS']='8';os.environ['MKL_NUM_THREADS']='8'
receipt={'status':'RUNNING','created_at_utc':now(),'coordinator_source_sha256':sha(pathlib.Path(__file__)),'input_lock_sha256':sha(R/'INPUT_MODEL_SCORE_LOCK.json'),'single_target_model':True,'credential_variables_read':False,'paid_API_calls':0,'attempts':[]}
for k in KEYS:
    assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime(2026,9,30,22,39,tzinfo=datetime.timezone.utc)
    start=time.perf_counter();startutc=now()
    args=[str(PYTHON),'-X','utf8','-B',str(R/'code/score_new.py'),'--model',k,'--input-sha256',lock['input_sha256'],'--corpus-sha256',lock['corpus_sha256']]
    print(json.dumps({'event':'START_MODEL','model':k,'timestamp':startutc}),flush=True)
    so=R/'scoring'/f'process_{k}_attempt0.stdout.txt';se=R/'scoring'/f'process_{k}_attempt0.stderr.txt'
    with so.open('x',encoding='utf-8') as out,se.open('x',encoding='utf-8') as err:
        completed=subprocess.run(args,stdout=out,stderr=err,cwd=R,shell=False)
    attempt={'model_key':k,'attempt':0,'started_at_utc':startutc,'ended_at_utc':now(),'elapsed_seconds':time.perf_counter()-start,'exit_code':completed.returncode,'stdout_path':str(so.relative_to(R)),'stdout_sha256':sha(so),'stderr_path':str(se.relative_to(R)),'stderr_sha256':sha(se)}
    receipt['attempts'].append(attempt)
    print(json.dumps({'event':'END_MODEL','model':k,'exit_code':completed.returncode,'elapsed_seconds':round(attempt['elapsed_seconds'],3),'stdout':so.read_text(encoding='utf-8')[-1000:]}),flush=True)
    if completed.returncode:
        receipt.update(status='STOPPED_TECHNICAL_ERROR',ended_at_utc=now())
        exclusive(R/'scoring/TARGET_EXECUTION_RECEIPT.json',receipt)
        raise SystemExit(completed.returncode)
receipt.update(status='COMPLETE',ended_at_utc=now(),target_logical_requests=704,score_rows=1408,technical_retries=0,background_continuation=False)
exclusive(R/'scoring/TARGET_EXECUTION_RECEIPT.json',receipt)
print(json.dumps({'event':'ALL_TARGET_MODELS_COMPLETE','target_logical_requests':704,'score_rows':1408}),flush=True)