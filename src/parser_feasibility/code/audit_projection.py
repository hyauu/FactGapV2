"""Project-scoped construction projection, blinded packet packing, and sealed review reduction. No methods or models."""
import argparse,collections,datetime as dt,hashlib,json,pathlib
R=pathlib.Path(__file__).resolve().parent.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v):
    with p.open('x',encoding='utf-8') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def jsonl(p,v):
    with p.open('x',encoding='utf-8') as f:
        for x in v:f.write(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n')
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def boolean(v):
    if type(v) is bool:return v
    if isinstance(v,str) and v.strip().lower() in ('true','false'):return v.strip().lower()=='true'
    if isinstance(v,str) and v.strip().upper()=='UNKNOWN':return 'UNKNOWN'
    raise ValueError('Invalid boolean/UNKNOWN transport')
def prepare():
    assert (R/'METHOD_AND_SCOPE_LOCK.json').is_file()
    builder=R/'private'/'builder_v1.json';b=read(builder)
    assert len(b['blocks'])==8 and len(b['probes'])==12
    assert collections.Counter(x['template_id'] for x in b['blocks']).values()=={2} if False else len(set(x['template_id'] for x in b['blocks']))==4
    assert all(v==2 for v in collections.Counter(x['template_id'] for x in b['blocks']).values())
    data=[];maprows=[];perblock=[]
    for i,block in enumerate(b['blocks']):
        assert len(block['queries'])==4 and len(block['candidates'])==2
        assert {(q['condition'],q['wording']) for q in block['queries']}=={(c,w) for c in ('LITERAL','RESOLVED') for w in (0,1)}
        assert (block['include_lower'],block['include_upper']) in ((True,False),(False,True))
        assert 0<block['lower']<block['upper']
        values=block['candidate_values']
        satisfies=lambda v:(v>=block['lower'] if block['include_lower'] else v>block['lower']) and (v<=block['upper'] if block['include_upper'] else v<block['upper'])
        ss=[satisfies(v) for v in values];assert sum(ss)==1 and ss[block['gold_candidate_index']]
        assert len(set(block['candidates']))==2 and all(0<len(t)<=220 for t in block['candidates'])
        chunk=[]
        for q in sorted(block['queries'],key=lambda q:(q['condition'],q['wording'])):
            assert 0<len(q['text'])<=320
            iid='n'+f'{len(data)+1:03d}'
            row={'query_id':iid,'block_id':block['block_id'],'template_id':block['template_id'],'condition':q['condition'],'wording':q['wording'],'query':q['text'],'candidates':block['candidates'],'gold_candidate_index':block['gold_candidate_index'],'canonical':{k:block[k] for k in ('subject','property','lower','upper','include_lower','include_upper')},'data_designation':'template_related_exploratory'}
            data.append(row);chunk.append(row)
            maprows.append({'neutral_id':iid,'kind':'main','query_id':iid,'block_id':block['block_id'],'expected_satisfaction':ss})
        perblock.append(chunk)
    probes=[]
    types=collections.Counter()
    for probe in b['probes']:
        types[probe['probe_type']]+=1
        assert 0<len(probe['query'])<=320 and len(probe['candidates'])==2 and all(0<len(t)<=220 for t in probe['candidates'])
        assert all(boolean(v) in (True,False,'UNKNOWN') for v in probe['expected_satisfaction'])
        iid='n'+f'{len(data)+len(probes)+1:03d}'
        row={**probe,'query_id':iid};probes.append(row)
        maprows.append({'neutral_id':iid,'kind':'probe','query_id':iid,'block_id':None,'expected_satisfaction':[boolean(v) for v in probe['expected_satisfaction']]})
    assert types=={'no_constraint_no_numbers':2,'no_constraint_identifier':2,'ambiguous_or_unsupported':4,'both_satisfy':2,'both_violate':2},types
    jsonl(R/'new_eval.jsonl',data);jsonl(R/'safety_probes.jsonl',probes);jsonl(R/'private'/'REVIEW_MAP.jsonl',maprows)
    shards=[[] for _ in range(8)]
    for j in range(4):
        for half in range(2):
            shard=shards[j*2+half]
            for chunk in perblock[half*4:half*4+4]:shard.append(chunk[j])
    for i,probe in enumerate(probes):shards[i%8].append(probe)
    packet_index=[]
    for role in ('A','B'):
        for i,shard in enumerate(shards):
            assert len(shard)<=6 and len([x['block_id'] for x in shard if 'block_id' in x])==len(set(x['block_id'] for x in shard if 'block_id' in x))
            folder=R/'reviews'/f'semantic_{role}_{i:02d}';folder.mkdir()
            items=[{'id':x['query_id'],'query':x['query'],'candidates':x['candidates']} for x in shard]
            write(folder/'input.json',{'items':items})
            packet_index.append({'role':role,'shard':i,'items':[x['id'] for x in items],'path':str((folder/'input.json').relative_to(R)),'sha256':sha(folder/'input.json'),'output':str((folder/'raw.json').relative_to(R))})
    write(R/'reviews'/'SEMANTIC_PACKET_LOCK.json',{'created_at_utc':now(),'packets':packet_index,'main':32,'probes':12,'max_items':6,'same_block_siblings_per_initial_context':1,'private_metadata_in_packets':False,'bool_transport_rule':'JSON booleans or exact case-insensitive true/false strings; UNKNOWN retained as UNKNOWN. No other coercion.'})
    write(R/'CONSTRUCTION_PROJECTION_RECEIPT.json',{'status':'STRUCTURAL_PASS_PENDING_INDEPENDENT_QA','created_at_utc':now(),'builder_sha256':sha(builder),'method_lock_sha256':sha(R/'METHOD_AND_SCOPE_LOCK.json'),'main':32,'probes':12,'classification':'template_related_exploratory','no_method_output_or_target_score_observed':True})
    print(json.dumps({'prepared':True,'semantic_contexts_required':16,'queries':44}))
def reduce_semantic():
    lock=read(R/'reviews'/'SEMANTIC_PACKET_LOCK.json')
    allresults={};rawlocks=[];issues=[]
    for p in lock['packets']:
        path=R/p['output'];result=read(path);items=result['items']
        assert len(items)==len(p['items']) and {x['id'] for x in items}==set(p['items'])
        rawlocks.append({'path':p['output'],'sha256':sha(path)})
        for item in items:
            assert len(item['candidate_satisfaction'])==2
            item['candidate_satisfaction']=[boolean(v) for v in item['candidate_satisfaction']]
            assert type(item['ambiguous']) is bool
            assert item['satisfying_indices']==[i for i,x in enumerate(item['candidate_satisfaction']) if x is True]
            allresults[(p['role'],item['id'])]=item
    projection=[json.loads(s) for s in (R/'private'/'REVIEW_MAP.jsonl').read_text(encoding='utf-8').splitlines()]
    data={x['query_id']:x for x in [json.loads(s) for s in (R/'new_eval.jsonl').read_text(encoding='utf-8').splitlines()]}
    sealed_rows=[]
    for m in projection:
        a=allresults[('A',m['neutral_id'])];b=allresults[('B',m['neutral_id'])]
        reasons=[]
        if a['candidate_satisfaction']!=b['candidate_satisfaction']:reasons.append('A_B_SATISFACTION_DISAGREEMENT')
        if a['candidate_satisfaction']!=m['expected_satisfaction']:reasons.append('REVIEWER_BUILDER_DIFFERENCE')
        if m['kind']=='main':
            expected=data[m['query_id']]['canonical']
            for role,item in (('A',a),('B',b)):
                c=item['constraint']
                if c is None or item['ambiguous']:reasons.append(role+'_INCOMPLETE_OR_AMBIGUOUS_MAIN')
                elif any(c.get(k)!=expected[k] for k in ('lower','upper','include_lower','include_upper')):reasons.append(role+'_BOUND_DIFFERENCE')
        if reasons:issues.append({'neutral_id':m['neutral_id'],'kind':m['kind'],'reasons':reasons,'A':a,'B':b,'builder_expected_satisfaction':m['expected_satisfaction']})
        sealed_rows.append({'neutral_id':m['neutral_id'],'kind':m['kind'],'A':a,'B':b,'issues':reasons})
    jsonl(R/'reviews'/'semantic_normalized.jsonl',sealed_rows)
    write(R/'reviews'/'INITIAL_SEMANTIC_OUTPUTS_SEALED.json',{'created_at_utc':now(),'reviewer_judgments':88,'contexts':16,'raw_outputs':rawlocks,'all_initial_outputs_complete':True,'issues':len(issues),'issues_path':'reviews/semantic_issues.json'})
    write(R/'reviews'/'semantic_issues.json',{'issues':issues,'no_majority_vote':True,'generator_not_authoritative':True})
    if not issues:
        write(R/'reviews'/'SEMANTIC_QA_SEAL.json',{'status':'PASS','created_at_utc':now(),'main_queries':32,'probes':12,'reviewer_judgments':88,'evidence_grade':'OPERATIONALLY_BLINDED_AUTOMATED_REVIEW','technical_isolation_or_human_certification':False,'C':'NOT_NEEDED','raw_output_sha_locks':rawlocks})
    # Full design packet only exists after every initial output has been sealed.
    builder=read(R/'private'/'builder_v1.json')
    blocks=[{'id':'g'+f'{i+1:02d}','queries':[q['text'] for q in sorted(x['queries'],key=lambda q:(q['condition'],q['wording']))],'candidates':x['candidates']} for i,x in enumerate(builder['blocks'])]
    for role in ('A','B'):
        folder=R/'reviews'/('design_'+role);folder.mkdir()
        write(folder/'input.json',{'blocks':blocks})
    print(json.dumps({'initial_sealed':True,'issues':len(issues),'design_packets_created':True}))
def reduce_design():
    assert (R/'reviews'/'INITIAL_SEMANTIC_OUTPUTS_SEALED.json').exists()
    rawlocks=[];issues=[];judgments=[]
    for role in ('A','B'):
        path=R/'reviews'/('design_'+role)/'raw.json';out=read(path)['blocks']
        assert len(out)==8 and {x['id'] for x in out}=={'g'+f'{i+1:02d}' for i in range(8)}
        rawlocks.append({'path':str(path.relative_to(R)),'sha256':sha(path)})
        for item in out:
            assert item['verdict'] in ('PASS_LIMITED','REJECT','UNKNOWN')
            if item['verdict']!='PASS_LIMITED':issues.append({'role':role,**item})
            judgments.append({'role':role,**item})
    jsonl(R/'reviews'/'design_normalized.jsonl',judgments)
    write(R/'reviews'/'DESIGN_OUTPUTS_SEALED.json',{'created_at_utc':now(),'judgments':16,'contexts':2,'raw_output_hashes':rawlocks,'issues':issues})
    if not issues:
        write(R/'reviews'/'DESIGN_QA_SEAL.json',{'status':'PASS_LIMITED','created_at_utc':now(),'blocks':8,'design_judgments':16,'template_holdout':'template_related_exploratory','C':'NOT_NEEDED','raw_output_hashes':rawlocks})
    print(json.dumps({'design_issues':len(issues),'design_status':'PASS_LIMITED' if not issues else 'PENDING_C'}))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','semantic','design'));mode=ap.parse_args().mode
    {'prepare':prepare,'semantic':reduce_semantic,'design':reduce_design}[mode]()
