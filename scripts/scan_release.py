"""Best-effort local candidate scan; findings never include secret values."""
import argparse,collections,csv,hashlib,io,json,pathlib,re,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
ALLOWED_EMAILS={'qiu.haot@northeastern.edu','qibaic@alumni.cmu.edu'}
PATTERNS={'secret_openai_anthropic':re.compile(r'\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{18,}'),'secret_google':re.compile(r'\bAIza[0-9A-Za-z_-]{30,}'),'secret_aws':re.compile(r'\bAKIA[0-9A-Z]{16}\b'),'secret_github':re.compile(r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}'),'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),'local_user_path':re.compile(r'(?i)(?:[A-Z]:[\\/]+Users[\\/]+[^\\/\s<>"\x27]+|/home/[^/\s<>"\x27]+)'),'credential_literal':re.compile(r'(?i)(?:api[_-]?key|access[_-]?token|authorization)["\x27]?\s*[:=]\s*["\x27](?:Bearer\s+)?([A-Za-z0-9_-]{24,})["\x27]'),'email':re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')}
PRIVATE_KEYS={'account_id','organization_id','workspace_id','conversation_id','thread_id','safety_identifier','anthropic_workspace_id'}
def scan():
 findings=[];formats=collections.Counter();checked=[];intentional=collections.Counter();embedded=[]
 def textscan(text,file,field='text'):
  for category,pat in PATTERNS.items():
   for m in pat.finditer(text):
    value=m.group()
    if category=='email' and value in ALLOWED_EMAILS:intentional[value]+=1;continue
    if category=='email' and file.endswith('.py') and value.startswith('n') and value[1:] in ALLOWED_EMAILS and m.start()>0 and text[m.start()-1]=='\\':intentional[value[1:]]+=1;continue
    if category=='local_user_path' and file=='scripts/scan_release.py' and any(c in value for c in '[^'):continue
    findings.append({'file':file,'field':field,'category':category,'value_sha256':hashlib.sha256(value.encode()).hexdigest(),'length':len(value)})
 def walk(v,file,field='$'):
  if isinstance(v,dict):
   for k,x in v.items():
    k=k.decode('utf-8',errors='replace') if isinstance(k,bytes) else str(k)
    if k.lower() in PRIVATE_KEYS and x not in [None,'',False]:findings.append({'file':file,'field':field+'.'+k,'category':'private_identifier_field','value_sha256':hashlib.sha256(str(x).encode()).hexdigest()})
    walk(x,file,field+'.'+k)
  elif isinstance(v,(list,tuple)):
   for i,x in enumerate(v):walk(x,file,field+'['+str(i)+']')
  elif isinstance(v,str):textscan(v,file,field)
  elif isinstance(v,bytes):textscan(v.decode('utf-8',errors='replace'),file,field)
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file() or '.git' in p.relative_to(ROOT).parts:continue
  name=p.relative_to(ROOT).as_posix();ext=p.suffix.lower();formats[ext]+=1;checked.append({'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
  if ext in ['.zip','.7z','.tar','.gz']:
   findings.append({'file':name,'field':'archive','category':'nested_archive_not_allowlisted'});continue
  if ext=='.parquet':
   import pyarrow.parquet as pq
   t=pq.read_table(p);walk(t.to_pylist(),name);walk(t.schema.metadata or {},name,'metadata');embedded.append({'file':name,'rows':t.num_rows,'format':'parquet','status':'scanned_decoded_cells_and_schema_metadata'})
  elif ext=='.npz':
   import numpy as np
   with np.load(p,allow_pickle=False) as z:
    for key in z.files:
     a=z[key]
     if a.dtype.kind in 'US':walk(a.tolist(),name,key)
    embedded.append({'file':name,'arrays':len(z.files),'format':'npz','status':'numeric_arrays_no_pickle'})
  elif ext=='.pdf':
   from pypdf import PdfReader
   r=PdfReader(p);walk({str(k):str(v) for k,v in (r.metadata or {}).items()},name,'PDF_metadata')
   for i,pg in enumerate(r.pages):
    textscan(pg.extract_text() or '',name,'page'+str(i+1))
    aa=pg.get('/Annots',[]);aa=aa.get_object() if hasattr(aa,'get_object') else aa
    for an in aa:
     a=an.get_object().get('/A',{});a=a.get_object() if hasattr(a,'get_object') else a
     if a.get('/URI'):textscan(str(a['/URI']),name,'annotation_URI')
   attachments=list(r.attachments) if hasattr(r,'attachments') else []
   if attachments:findings.append({'file':name,'field':'PDF_attachments','category':'unexpected_embedded_attachment','count':len(attachments)})
   embedded.append({'file':name,'pages':len(r.pages),'format':'pdf','status':'metadata_text_URIs_and_attachment_inventory_scanned'})
  elif ext=='.png':
   from PIL import Image
   with Image.open(p) as im:walk({str(k):str(v) for k,v in im.info.items()},name,'image_metadata')
  else:
   try:
    text=p.read_text('utf-8-sig')
    if ext=='.json':walk(json.loads(text),name)
    elif ext=='.jsonl':
     for i,line in enumerate(text.splitlines()):
      if line.strip():walk(json.loads(line),name,'line'+str(i+1))
    else:textscan(text,name)
   except UnicodeError:findings.append({'file':name,'field':'binary','category':'unhandled_binary_format'})
 # Deduplicate observations without disclosing their values.
 unique={json.dumps(x,sort_keys=True):x for x in findings}
 return {'status':'PASS' if not unique else 'REVIEW_REQUIRED','scope':'repository_payload_excluding_git_metadata','files_checked':len(checked),'formats':dict(formats),'findings':list(unique.values()),'intentional_public_author_contacts':[{'email':e,'occurrences':n} for e,n in intentional.items()],'decoded_binary_checks':embedded,'file_inventory':checked,'limitations':['Pattern-based and decoded metadata scan, not a formal secret-free certification.','Scored text was not changed. Suspicious scored content must be quarantined, not rewritten.','No audit of unrelated machine directories or external accounts.']}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();r=scan();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({'status':r['status'],'files':r['files_checked'],'findings':len(r['findings']),'categories':dict(collections.Counter(x['category'] for x in r['findings']))}));return 0 if r['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
