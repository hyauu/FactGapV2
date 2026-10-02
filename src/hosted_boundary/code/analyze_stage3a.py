"""Deterministic Stage3A raw replay and post-completion private truth join. No network calls."""
import collections,csv,datetime as dt,io,json,math,pathlib,sys
import provider_pilot as p
R=p.R
MODELS=p.MODELS

def rows(path): return [json.loads(s) for s in (R/path).read_text(encoding='utf-8-sig').splitlines()]
def csvbytes(values):
    assert values
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(values[0]))
    writer.writeheader();writer.writerows(values);return stream.getvalue().encode('utf-8')
def jsonbytes(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
def rate(n,d): return n/d if d else None

def compute():
    assert (R/'RESEARCH_EXECUTION_FINISHED.json').exists(), 'All provider calls must finish before truth join'
    closed=p.read('RESEARCH_EXECUTION_FINISHED.json');assert closed['all_active_requests_drained'] and closed['truth_join_now_allowed']
    p.verify_scientific_lock()
    qlist=rows('inputs/control_eval.jsonl');blocks={x['block_id']:x for x in rows('private/source_eval_blocks.jsonl')}
    mapping={x['request_id_neutral']:x for x in rows('private/REQUEST_MAP.jsonl')}
    qby={x['query_id']:x for x in qlist}
    requests={x['logical_id']:x for provider in MODELS for task in ('a','b') for x in rows('requests/'+provider+'_task_'+task+'.jsonl')}
    research=[x for path in sorted((R/'raw').glob('*.jsonl')) for x in rows(path.relative_to(R))]
    toys=[x for path in sorted((R/'toy'/'raw').glob('*.jsonl')) for x in rows(path.relative_to(R))]
    assert len(requests)==432
    attempts=collections.defaultdict(list);replay_errors=[]
    for x in research:
        logical=x['logical_id'];assert logical in requests
        req=requests[logical];assert x['provider']==req['provider'] and x['task']==req['task']
        assert x['requested_model']==MODELS[x['provider']]
        assert x['request_body_sha256']==req['request_body_sha256']==p.hashbytes(p.jsbytes(req['body']))
        rid=req['request_id_neutral'];m=mapping[rid];q=qby[m['query_id_private']]
        assert x['query_sha256']==p.hashbytes(q['text'].encode())
        if x['task']=='B': assert x['candidate_order_sha256']==m['candidate_order_sha256']
        if x.get('raw_response') and x['http_status']==200:
            text,*usage=p.extract(x['provider'],x['raw_response'])
            try: parsed=json.loads(text)
            except (ValueError,TypeError): parsed=None
            assert parsed==x['parsed_response'], 'Stored parsed output differs from returned text'
            assert p.parse(x['task'],parsed)==(x['status']=='OK') or x['status'] in ('MODEL_MISMATCH','USAGE_MISSING','MALFORMED')
            if x['status']=='OK': assert x['returned_model'].startswith(x['requested_model'])
        assert x['attempt'] in (0,1)
        attempts[logical].append(x)
    selected={}
    for logical,items in attempts.items():
        items=sorted(items,key=lambda x:x['attempt'])
        assert [x['attempt'] for x in items] in ([0],[0,1]), 'Missing/duplicate/excess attempt'
        if len(items)>1:
            assert items[0]['status']!='OK', 'Valid response retried'
            assert items[0]['status'] in ('MALFORMED','TRANSPORT_ERROR') or (items[0]['status']=='HTTP_ERROR' and (items[0]['http_status']==429 or 500<=items[0]['http_status']<600))
        selected[logical]=items[-1]
    aends=[x['http_end_utc'] for x in research if x['task']=='A']
    bstarts=[x['http_start_utc'] for x in research if x['task']=='B']
    assert not bstarts or max(aends)<=min(bstarts), 'Task barrier violated'
    all_cost_records=research+toys
    usage_cost=math.fsum(x['cost_usage_repriced_usd'] or 0 for x in all_cost_records)
    conservative_cost=math.fsum(x['cost_conservative_usd'] for x in all_cost_records)
    ledger=p.read('budget_ledger.json')
    assert not ledger['reservations'] and abs(conservative_cost-ledger['settled_conservative_usd'])<1e-9
    assert conservative_cost<=5
    peaks={};global_events=[]
    for provider in MODELS:
        events=[]
        for x in research:
            if x['provider']==provider:
                events.extend([(x['http_start_utc'],1),(x['http_end_utc'],-1)]);global_events.extend([(x['http_start_utc'],1),(x['http_end_utc'],-1)])
        active=peak=0
        for stamp,delta in sorted(events): active+=delta;peak=max(peak,active)
        assert peak<=2
        peaks[provider]=peak
    active=global_peak=0
    for stamp,delta in sorted(global_events): active+=delta;global_peak=max(global_peak,active)
    assert global_peak<=6
    task_a=[];task_b=[];order_rows=[];component=[];A={};B={};pairlookup={}
    for provider,model in MODELS.items():
        for i,q in enumerate(qlist):
            b=blocks[q['block_id']]
            true={'valid':True,'lower_bound':b['lower'],'lower_inclusive':b['include_lower'],'upper_bound':b['upper'],'upper_inclusive':b['include_upper']}
            aid=provider+'/a'+f'{i+1:03d}';a=selected.get(aid);valid=a is not None and a['status']=='OK';answer=a['parsed_response'] if valid else None
            exact=answer==true if valid else None
            common={'provider':provider,'requested_model':model,'query_id_private':q['query_id'],'block_id_private':q['block_id'],'template_id_private':q['template_id'],'condition_private':q['condition'],'wording_private':q['wording']}
            ar={**common,'logical_id':aid,'status':a['status'] if a else 'NOT_EVALUATED','returned_constraint_json':json.dumps(answer,sort_keys=True) if answer else '', 'exact_correct':int(exact) if valid else '', 'lower_bound_correct':int(answer['lower_bound']==true['lower_bound']) if valid else '', 'upper_bound_correct':int(answer['upper_bound']==true['upper_bound']) if valid else '', 'inclusivity_correct':int(answer['lower_inclusive']==true['lower_inclusive'] and answer['upper_inclusive']==true['upper_inclusive']) if valid else '', 'invalid_or_abstain':int(not answer['valid']) if valid else '', 'malformed':int(a is not None and a['status']=='MALFORMED'),'technical_or_missing':int(not valid and (a is None or a['status']!='MALFORMED'))}
            task_a.append(ar);A[(provider,q['query_id'])]=ar
            bytext={x['text']:x['candidate_id'] for x in b['documents']}
            gold=next(x['candidate_id'] for x in b['documents'] if x['private_role']=='gold')
            passage=[];correct=[];ordersok=[]
            for orientation in (0,1):
                bid=provider+'/b'+f'{i+1:03d}'+str(orientation);v=selected.get(bid);ok=v is not None and v['status']=='OK';choice=v['parsed_response']['choice'] if ok else ''
                texts=q['candidates'] if orientation==0 else list(reversed(q['candidates']))
                identity=bytext[texts[0 if choice=='A' else 1]] if choice in ('A','B') else choice
                success=ok and identity==gold
                passage.append(identity);correct.append(success);ordersok.append(ok)
                task_b.append({**common,'logical_id':bid,'orientation_private':orientation,'status':v['status'] if v else 'NOT_EVALUATED','display_choice':choice,'selected_passage_id':identity,'strict_correct':int(success) if ok else '', 'incorrect':int(choice in ('A','B') and not success) if ok else '', 'TIE':int(choice=='TIE') if ok else '', 'ABSTAIN':int(choice=='ABSTAIN') if ok else '', 'malformed':int(v is not None and v['status']=='MALFORMED'),'technical_or_missing':int(not ok and (v is None or v['status']!='MALFORMED'))})
            if not all(ordersok): disposition='RANK_TECHNICAL_OR_MISSING';ordercat='technical_or_missing'
            else:
                if all(correct): disposition='RANK_CORRECT'
                elif any(x and x not in ('TIE','ABSTAIN',gold) for x in passage): disposition='RANK_WRONG'
                else: disposition='RANK_TIE_OR_ABSTAIN'
                ordercat='order-stable' if passage[0]==passage[1] else 'order-flip' if all(x not in ('TIE','ABSTAIN') for x in passage) else 'tie/abstain interaction'
            orow={**common,'order0_passage_id':passage[0],'order1_passage_id':passage[1],'order_category':ordercat,'rank_status':disposition,'strict_both_orders_correct':int(all(correct)) if all(ordersok) else '', 'wrong_in_both_orders':int(all(x and x not in ('TIE','ABSTAIN',gold) for x in passage)) if all(ordersok) else '', 'one_correct_one_wrong':int(ordercat=='order-flip' and any(correct)) if all(ordersok) else ''}
            order_rows.append(orow);B[(provider,q['query_id'])]=orow
            extract='EXTRACT_CORRECT' if exact else 'EXTRACT_WRONG' if valid else 'EXTRACT_TECHNICAL_OR_MISSING'
            component.append({**common,'extract_status':extract,'rank_status':disposition,'component_cell':extract+' + '+disposition,'order_category':ordercat,'strict_both_orders_correct':orow['strict_both_orders_correct'],'wrong_in_both_orders':orow['wrong_in_both_orders'],'one_correct_one_wrong':orow['one_correct_one_wrong']})
            pairlookup[(provider,q['block_id'],q['wording'],q['condition'])]=q['query_id']
    condition=[]
    for provider in MODELS:
        for cond in ('LITERAL','RESOLVED'):
            a=[x for x in task_a if x['provider']==provider and x['condition_private']==cond]
            b=[x for x in task_b if x['provider']==provider and x['condition_private']==cond]
            o=[x for x in order_rows if x['provider']==provider and x['condition_private']==cond]
            c=[x for x in component if x['provider']==provider and x['condition_private']==cond]
            ac=sum(x['exact_correct']==1 for x in a);an=sum(x['status']=='OK' for x in a);qc=sum(x['strict_both_orders_correct']==1 for x in o);qn=sum(x['strict_both_orders_correct']!='' for x in o)
            condition.append({'provider':provider,'condition':cond,'TaskA_planned_queries':24,'TaskA_valid_schema_queries':an,'TaskA_exact_correct':ac,'TaskA_exact_accuracy':rate(ac,an),'TaskA_lower_correct':sum(x['lower_bound_correct']==1 for x in a),'TaskA_upper_correct':sum(x['upper_bound_correct']==1 for x in a),'TaskA_inclusivity_correct':sum(x['inclusivity_correct']==1 for x in a),'TaskA_invalid':sum(x['invalid_or_abstain']==1 for x in a),'TaskA_malformed':sum(x['malformed'] for x in a),'TaskA_technical_missing':sum(x['technical_or_missing'] for x in a),'TaskB_planned_order_responses':48,'TaskB_OK_order_responses':sum(x['status']=='OK' for x in b),'TaskB_correct_order_responses':sum(x['strict_correct']==1 for x in b),'TaskB_incorrect_order_responses':sum(x['incorrect']==1 for x in b),'TaskB_TIE':sum(x['TIE']==1 for x in b),'TaskB_ABSTAIN':sum(x['ABSTAIN']==1 for x in b),'TaskB_malformed':sum(x['malformed'] for x in b),'TaskB_technical_missing':sum(x['technical_or_missing'] for x in b),'TaskB_query_strict_both_orders_correct':qc,'TaskB_valid_query_pairs':qn,'TaskB_primary_query_accuracy':rate(qc,qn),'order_flips':sum(x['order_category']=='order-flip' for x in o),'tie_abstain_interactions':sum(x['order_category']=='tie/abstain interaction' for x in o),'components_json':json.dumps(dict(collections.Counter(x['component_cell'] for x in c)),sort_keys=True)})
    paired=[]
    for provider in MODELS:
        for block in blocks:
            for wording in (0,1):
                lid=pairlookup[(provider,block,wording,'LITERAL')];rid=pairlookup[(provider,block,wording,'RESOLVED')];l=B[(provider,lid)];r=B[(provider,rid)];la=A[(provider,lid)];ra=A[(provider,rid)]
                diff=r['strict_both_orders_correct']-l['strict_both_orders_correct'] if '' not in (l['strict_both_orders_correct'],r['strict_both_orders_correct']) else ''
                paired.append({'provider':provider,'block_id_private':block,'template_id_private':blocks[block]['template_id'],'wording_private':wording,'literal_query_id':lid,'resolved_query_id':rid,'literal_rank_status':l['rank_status'],'resolved_rank_status':r['rank_status'],'ranking_transition':l['rank_status']+' -> '+r['rank_status'],'literal_strict_success':l['strict_both_orders_correct'],'resolved_strict_success':r['strict_both_orders_correct'],'resolved_minus_literal':diff,'extraction_transition':str(la['exact_correct'])+' -> '+str(ra['exact_correct'])})
    templates=[];loto=[]
    for provider in MODELS:
        for tid in ('T0','T1','T2','T3'):
            record={'provider':provider,'template_id':tid,'paired_wordings_planned':6}
            for cond in ('LITERAL','RESOLVED'):
                a=[x for x in task_a if x['provider']==provider and x['template_id_private']==tid and x['condition_private']==cond]
                o=[x for x in order_rows if x['provider']==provider and x['template_id_private']==tid and x['condition_private']==cond]
                c=[x for x in component if x['provider']==provider and x['template_id_private']==tid and x['condition_private']==cond]
                record[cond+'_A_exact_correct']=sum(x['exact_correct']==1 for x in a);record[cond+'_B_strict_correct']=sum(x['strict_both_orders_correct']==1 for x in o);record[cond+'_order_flips']=sum(x['order_category']=='order-flip' for x in o);record[cond+'_components_json']=json.dumps(dict(collections.Counter(x['component_cell'] for x in c)),sort_keys=True)
            pairs=[x['resolved_minus_literal'] for x in paired if x['provider']==provider and x['template_id_private']==tid and x['resolved_minus_literal']!='']
            record['paired_valid_count']=len(pairs);record['delta_pp']=100*sum(pairs)/len(pairs) if pairs else '';templates.append(record)
        for omitted in ('T0','T1','T2','T3'):
            kept=[x['delta_pp'] for x in templates if x['provider']==provider and x['template_id']!=omitted and x['delta_pp']!='']
            loto.append({'provider':provider,'omitted_template':omitted,'kept_templates':len(kept),'delta_pp':sum(kept)/len(kept) if kept else ''})
    byprovider={}
    for provider in MODELS:
        pc=[x for x in paired if x['provider']==provider]
        td=[x['delta_pp'] for x in templates if x['provider']==provider and x['delta_pp']!='']
        byprovider[provider]={'model':MODELS[provider],'conditions':[x for x in condition if x['provider']==provider],'primary_delta_pp':sum(td)/len(td) if td else None,'transitions':dict(collections.Counter(x['ranking_transition'] for x in pc)),'templates':[x for x in templates if x['provider']==provider],'LOTO':[x for x in loto if x['provider']==provider]}
    cost_by={}
    for provider in MODELS:
        pr=[x for x in all_cost_records if x['provider']==provider]
        cost_by[provider]={'api_attempts':len(pr),'research_attempts':sum(x['phase']=='research' for x in pr),'toy_attempts':sum(x['phase']=='toy' for x in pr),'input_tokens_measured':sum(x.get('input_tokens') or 0 for x in pr),'output_tokens_including_thinking_measured':sum(x.get('output_tokens') or 0 for x in pr),'usage_repriced_usd':math.fsum(x['cost_usage_repriced_usd'] or 0 for x in pr),'unknown_usage_attempts':sum(x['cost_usage_repriced_usd'] is None for x in pr),'conservative_usd':math.fsum(x['cost_conservative_usd'] for x in pr),'returned_versions':dict(collections.Counter(x.get('returned_model') for x in pr if x.get('returned_model'))),'research_max_reported_output_tokens':max((x.get('output_tokens') or 0 for x in pr if x['phase']=='research'),default=0),'research_final_non_OK':sum(x['status']!='OK' for key,x in selected.items() if x['provider']==provider)}
    summary={'providers':byprovider,'research_logical_requests_observed':len(selected),'research_attempts':len(research),'technical_retries':len(research)-len(selected),'toy_attempts':len(toys),'last_attempt_status_counts':dict(collections.Counter(x['status'] for x in selected.values())),'usage_repriced_usd_total':usage_cost,'conservative_cost_usd_total':conservative_cost,'actual_invoice_cost':'UNKNOWN; no provider billing invoice/administrative usage endpoint queried','cost_by_provider':cost_by,'concurrency_peak_HTTP':{'global':global_peak,'per_provider':peaks},'research_start_utc':closed['started_at_utc'],'research_finished_utc':closed['finished_at_utc'],'statistical_inference':'NONE','data_scope':'12 convenience-constructed blocks,4 shared templates,2 wordings; not24 independent constructs','primary_ranking':'Both candidate orders must choose correct passage; per-order counts retained separately'}
    outputs={'TASK_A_RESULTS.csv':csvbytes(task_a),'TASK_B_RESULTS.csv':csvbytes(task_b),'COMPONENT_DECOMPOSITION.csv':csvbytes(component),'ORDER_SENSITIVITY.csv':csvbytes(order_rows),'TEMPLATE_RESULTS.csv':csvbytes(templates),'CONDITION_SUMMARY.csv':csvbytes(condition),'PAIRED_CONTRASTS.csv':csvbytes(paired),'LOTO_SUMMARY.csv':csvbytes(loto),'OVERALL_METRICS.json':jsonbytes(summary)}
    replay={'status':'PASS','research_request_bodies_verified':len(research),'unique_research_logical_requests':len(selected),'expected_three_provider_logical_requests':432,'research_attempts':len(research),'raw_answers_reparsed':sum(x['http_status']==200 for x in research),'source_query_candidate_order_hashes_verified':True,'raw_body_lock_hashes_verified':True,'phase_barrier_verified':True,'final_selection_rule':'Last permitted technical attempt; valid/wrong/TIE/ABSTAIN never retried','budget_ledger_reconstructed':True,'native_api_new_calls_during_replay':0,'source_scientific_lock_verified':True,'output_hashes':{name:p.hashbytes(data) for name,data in outputs.items()}}
    return outputs,replay,summary

if __name__=='__main__':
    outputs,replay,summary=compute()
    if sys.argv[1:]==['--replay-only']:
        errors=[name for name,data in outputs.items() if not (R/name).exists() or (R/name).read_bytes()!=data]
        assert not errors, errors
        stored=p.read('REPLAY_VERIFICATION.json');assert stored==replay
        print(json.dumps({'status':'PASS','tables_rebuilt_and_byte_compared':len(outputs),'raw_research_attempts':replay['research_attempts'],'new_API_calls':0}))
    else:
        assert not any((R/name).exists() for name in outputs), 'Existing analysis must not be silently overwritten'
        for name,data in outputs.items(): (R/name).write_bytes(data)
        p.write('REPLAY_VERIFICATION.json',replay)
        print(json.dumps(summary,ensure_ascii=False))
