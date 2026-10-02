"""Prepare prospective Stage4A inputs and replay all results without model calls."""
from __future__ import annotations
import argparse, csv, dataclasses, hashlib, importlib.util, io, json, math, statistics, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
RUN = Path(__file__).resolve().parents[1]
SCORING = RUN/'scoring'
REVIEWS = RUN/'reviews'
KEYS = ('bm25', 'bge_small', 'e5_small', 'minilm_ce')
METHODS = ('M0', 'M1', 'M2')
STATUSES = {'SATISFIES', 'VIOLATES', 'UNKNOWN'}
ANALYSIS_FILES = ('condition_summary.csv', 'coverage_harm_and_probe_results.csv',
    'block_template_transitions.csv', 'OVERALL_METRICS.json', 'M2_DECISIONS.jsonl')

def jb(x): return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
def digest(b): return hashlib.sha256(b).hexdigest()
def sha(p): return digest(p.read_bytes())
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def readj(p): return [json.loads(v) for v in p.read_text(encoding='utf-8-sig').splitlines() if v.strip()]
def jfile(x): return (json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')
def jlfile(xs): return b''.join((json.dumps(x, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8') for x in xs)
def exclusive(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f: f.write(data)
def now(): return datetime.now(timezone.utc).isoformat()
def inside(p):
    p = p.resolve()
    if not p.is_relative_to(RUN): raise RuntimeError('All Stage4A inputs must be inside this run')
    return p
def rel(p): return str(inside(p).relative_to(RUN)).replace('\\', '/')
def load_method():
    lock = read(RUN/'METHOD_AND_SCOPE_LOCK.json')
    if lock['status'] != 'LOCKED_BEFORE_NEW_MATERIAL_CONSTRUCTION': raise RuntimeError('Prospective method lock missing')
    for row in lock['method_files']:
        if sha(inside(RUN/row['path'])) != row['sha256']: raise RuntimeError('Method file changed: '+row['path'])
    p = RUN/'method/constraint_check.py'
    spec = importlib.util.spec_from_file_location('stage4a_locked_method', p)
    m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
    return m, lock
def seal_digest(seal, p):
    """Accept an explicit file-lock list or a named data hash dictionary."""
    matches = []
    for field in ('data_sha256', 'file_sha256', 'data_file_sha256'):
        for name, value in seal.get(field, {}).items():
            q = Path(name)
            if q == p or str(name).replace('\\', '/') in (rel(p), p.name): matches.append(value)
    for row in seal.get('file_locks', []):
        if str(row['path']).replace('\\', '/') in (rel(p), p.name) or Path(row['path']) == p: matches.append(row['sha256'])
    if p.name == 'final_semantic_truths.jsonl':
        for field in ('final_semantic_truths_sha256', 'semantic_truths_sha256', 'truths_sha256'):
            if seal.get(field): matches.append(seal[field])
        value = seal.get('semantic_truths')
        if isinstance(value, dict) and value.get('sha256'): matches.append(value['sha256'])
    if not matches or any(value != sha(p) for value in matches): raise RuntimeError('QA seal does not bind current file: '+rel(p))
    return matches[0]
def qa(main_path, probe_path):
    sp, dp = REVIEWS/'SEMANTIC_QA_SEAL.json', REVIEWS/'DESIGN_QA_SEAL.json'
    semantic, design = read(sp), read(dp)
    if semantic['status'] != 'PASS' or design['status'] != 'PASS_LIMITED': raise RuntimeError('Required semantic/design QA seals incomplete')
    if semantic.get('main_queries') != 32 or semantic.get('probes') != 12 or design.get('blocks') != 8:
        raise RuntimeError('Sealed planned denominator differs')
    for seal in (semantic, design):
        for p in (main_path, probe_path): seal_digest(seal, p)
    truths_path = REVIEWS/'final_semantic_truths.jsonl'; seal_digest(semantic, truths_path)
    return sp, dp, truths_path
def data(main_path, probe_path):
    main, probes = readj(main_path), readj(probe_path)
    if len(main) != 32 or len(probes) != 12: raise RuntimeError('Fixed32 main and12 probes required')
    required_main = {'query_id','block_id','template_id','condition','wording','query','candidates','gold_candidate_index','canonical','data_designation'}
    required_probe = {'query_id','probe_id','probe_type','query','candidates','expected_satisfaction','semantic_note'}
    ids = set()
    for kind, rows, required in (('main', main, required_main), ('probe', probes, required_probe)):
        for row in rows:
            if not required.issubset(row): raise RuntimeError('Missing data contract field')
            if not isinstance(row['query_id'], str) or row['query_id'] in ids: raise RuntimeError('Invalid or duplicate query ID')
            ids.add(row['query_id'])
            if not isinstance(row['query'], str) or not row['query'] or len(row['candidates']) != 2 or any(not isinstance(s,str) or not s for s in row['candidates']):
                raise RuntimeError('Malformed visible query/candidate pair')
            if kind == 'main' and (type(row['gold_candidate_index']) is not int or row['gold_candidate_index'] not in (0,1)):
                raise RuntimeError('Invalid main gold index')
    conditions = Counter(p['condition'] for p in main)
    blocks = Counter(p['block_id'] for p in main); templates = Counter(p['template_id'] for p in main)
    if sorted(conditions.values()) != [16,16] or len(blocks) != 8 or set(blocks.values()) != {4} or len(templates) != 4 or set(templates.values()) != {8}:
        raise RuntimeError('Main32 four-template eight-block design differs')
    return main, probes

def prepare(args):
    if datetime.now(timezone.utc) >= datetime(2026,9,30,22,39,tzinfo=timezone.utc): raise RuntimeError('New scoring batch deadline reached')
    main_path, probe_path = inside(args.main), inside(args.probes)
    sp, dp, truths_path = qa(main_path, probe_path)
    m, method_lock = load_method(); main, probes = data(main_path, probe_path)
    paths = [SCORING/'scoring_inputs.jsonl', SCORING/'scoring_corpus.jsonl', RUN/'private/SCORE_MAP.jsonl',
        RUN/'M1_REWRITE_RECORDS.jsonl', RUN/'INPUT_MODEL_SCORE_LOCK.json']
    if any(p.exists() for p in paths): raise FileExistsError('Prepared inputs/lock are immutable')
    inputs, maps, rewrites = [], [], []
    for kind, records in (('main',main), ('probe',probes)):
        for p in records:
            # The sole rewrite input is the original visible query string.
            rewritten = m.rewrite(p['query'])
            before, after = m.parse_query(p['query']), m.parse_query(rewritten['query'])
            preserved = m.semantic_key(before) == m.semantic_key(after)
            if isinstance(before,m.Abstention): preserved = rewritten['query'] == p['query']
            if not preserved: raise RuntimeError('M1 prospective text constraint preservation failed')
            rewrites.append({'query_id':p['query_id'], 'kind':kind, 'original_query':p['query'],
                'rewritten_query':rewritten['query'], 'original_query_sha256':digest(p['query'].encode()),
                'rewritten_query_sha256':digest(rewritten['query'].encode()), 'text_constraint_preserved':preserved,
                'action':rewritten['action'], 'reason':rewritten['reason'], 'constraint':rewritten['constraint'],
                'latency_ns':rewritten['latency_ns']})
            for method in ('M0','M1'):
                query = p['query'] if method == 'M0' else rewritten['query']
                for orientation in (0,1):
                    rid = f'n{len(inputs):06d}'
                    inputs.append({'request_id':rid, 'query':query, 'candidates':list(p['candidates']) if orientation == 0 else list(reversed(p['candidates']))})
                    maps.append({'request_id':rid,'query_id':p['query_id'],'kind':kind,'method':method,'orientation':orientation})
    corpus = [{'text':s} for s in sorted({d for p in main+probes for d in p['candidates']})]
    if len(inputs) != 176 or len(rewrites) != 44: raise RuntimeError('Preparation matrix incomplete')
    neutral_paths = []
    for key in KEYS:
        p = SCORING/f'neutral_precheck_{key}.json'; r = read(p)
        if r['status'] != 'PASS' or r['research_queries_read'] != 0: raise RuntimeError('Neutral precheck missing or exposed')
        if r['identity']['wrapper_sha256'] != sha(RUN/'code/score_new.py'): raise RuntimeError('Scorer differs from neutral precheck')
        rp = SCORING/f'resources_precheck_{key}.json'
        if read(rp)['status'] != 'COMPLETE': raise RuntimeError('Neutral resource precheck incomplete')
        neutral_paths.extend((p,rp))
    for p, content in zip(paths[:4], (inputs,corpus,maps,rewrites)): exclusive(p,jlfile(content))
    locked_paths = [main_path,probe_path,sp,dp,truths_path,RUN/'METHOD_AND_SCOPE_LOCK.json',
        RUN/'code/score_new.py',Path(__file__),*paths[:4],*neutral_paths,
        *[RUN/v['path'] for v in method_lock['method_files']]]
    lock = {'status':'LOCKED_BEFORE_TARGET_SCORING','created_at_utc':now(),
        'research_name':'local_constraint_check_feasibility','main_queries':32,'probes':12,
        'logical_requests_per_model':176,'candidate_rows_per_model':352,'target_logical_requests':704,
        'unique_M2_logical_requests':352,'neutral_logical_requests':16,'total_unique_logical_requests':1072,
        'logical_request_cap':1200,'rewrite_calls':44,'input_sha256':sha(paths[0]),'corpus_sha256':sha(paths[1]),
        'score_map_sha256':sha(paths[2]),'models':method_lock['models'],
        'BM25_corpus_contract':'All unique actual44-query candidate texts in scoring_corpus.jsonl; M0/M1 share one fixed index',
        'main_path':rel(main_path),'probe_path':rel(probe_path),'semantic_truths_path':rel(truths_path),
        'inputs_path':rel(paths[0]),'corpus_path':rel(paths[1]),'score_map_path':rel(paths[2]),'rewrite_records_path':rel(paths[3]),
        'analysis_contract':method_lock['analysis'],'replay_is_same_input_deterministic_verification':True,
        'no_extra_archived_diagnostic':True,'no_model_calls_before_this_lock':True,
        'file_locks':[{'path':rel(p),'sha256':sha(p)} for p in locked_paths]}
    exclusive(paths[4],jfile(lock))
    print(json.dumps({'status':lock['status'],'input_sha256':lock['input_sha256'],'corpus_sha256':lock['corpus_sha256'],
        'logical_requests':704,'score_rows':1408,'unique_M2_logical_requests':352}))

def verify_lock():
    lock = read(RUN/'INPUT_MODEL_SCORE_LOCK.json')
    if lock['status'] != 'LOCKED_BEFORE_TARGET_SCORING': raise RuntimeError('Prospective input/model score lock absent')
    for row in lock['file_locks']:
        if sha(inside(RUN/row['path'])) != row['sha256']: raise RuntimeError('Changed score-locked file: '+row['path'])
    return lock
def finite(x): return type(x) in (int,float) and math.isfinite(x)
def check_digest(x):
    if not isinstance(x,str) or len(x) != 64 or any(c not in '0123456789abcdef' for c in x): raise RuntimeError('Invalid hash evidence')
def merge_raw(lock, inputs, maps):
    by_input = {p['request_id']:p for p in inputs}; by_map = {p['request_id']:p for p in maps}
    if len(inputs) != 176 or set(by_input) != set(by_map) or len(by_map) != 176: raise RuntimeError('Incomplete input/map matrix')
    merged, manifests, indexed = [], {}, {}
    for key in KEYS:
        rp, mp, ap = SCORING/f'raw_{key}.jsonl', SCORING/f'manifest_{key}.json', SCORING/f'forward_audit_{key}.json'
        manifest, audit = read(mp), read(ap); rows = readj(rp)
        if manifest['status'] != 'COMPLETE' or manifest['model_key'] != key or manifest['logical_ranking_requests'] != 176 or manifest['score_rows'] != 352 or len(rows) != 352:
            raise RuntimeError('Required full model manifest incomplete: '+key)
        if manifest['input_sha256'] != lock['input_sha256'] or manifest['corpus_sha256'] != lock['corpus_sha256'] or manifest['raw_sha256'] != sha(rp) or manifest['forward_audit_sha256'] != sha(ap):
            raise RuntimeError('Raw model input/output hash mismatch: '+key)
        resource = read(SCORING/f'resources_score_{key}.json')
        if resource['status'] != 'COMPLETE' or resource['process_RAM_fraction'] > .6 or (resource.get('configured_torch_intraop_threads') or 0) > 8:
            raise RuntimeError('Target resource gate failed')
        if resource.get('total_cuda_bytes') and max(resource['max_cuda_allocated_bytes'],resource['max_cuda_reserved_bytes'],resource['max_total_cuda_used_bytes']) > .8*resource['total_cuda_bytes']:
            raise RuntimeError('Target VRAM gate failed')
        config = manifest['configuration']; config_hash = digest(jb(config))
        if manifest['configuration_sha256'] != config_hash or config['wrapper_sha256'] != sha(RUN/'code/score_new.py') or config['corpus_file_sha256'] != lock['corpus_sha256']:
            raise RuntimeError('Full model/config/corpus cache identity mismatch')
        expected_contract = lock['models'][key]
        for field, value in expected_contract.items():
            if key == 'bm25' and field == 'corpus': continue
            if config['contract'].get(field) != value: raise RuntimeError('Frozen target configuration differs: '+key+'/'+field)
        if audit['actual_model_forward_calls'] != manifest['actual_model_forward_calls'] or audit['actual_model_sequence_occurrences'] != manifest['actual_model_sequence_occurrences']:
            raise RuntimeError('Model forward count evidence mismatch')
        batches = {v['batch_id']:v for v in audit['forward_batches']}; seen, slots = {}, set()
        for ordinal,p in enumerate(inputs):
            for pos in (0,1):
                row = rows[ordinal*2+pos]; slot = (row['request_id'],row['candidate_display_index'])
                if slot != (p['request_id'],pos) or slot in slots or row['model_key'] != key or row['request_ordinal'] != ordinal:
                    raise RuntimeError('Request/orientation/candidate matrix mismatch')
                slots.add(slot)
                q,d = p['query'],p['candidates'][pos]
                if row['query_text'] != q or row['candidate_text'] != d or row['query_text_sha256'] != digest(q.encode()) or row['candidate_text_sha256'] != digest(d.encode()):
                    raise RuntimeError('Visible text hash mismatch')
                if row['payload_sha256'] != digest(jb({'query':q,'candidates':p['candidates']})): raise RuntimeError('Payload hash mismatch')
                if row['status'] != 'OK' or row['technical_error_code'] is not None or not finite(row['raw_score']): raise RuntimeError('Missing/nonfinite technical score')
                if row['model_revision'] != expected_contract['revision'] or row['configuration_sha256'] != config_hash or row['corpus_sha256'] != lock['corpus_sha256']:
                    raise RuntimeError('Row config identity mismatch')
                dtype = 'float64' if key == 'bm25' else 'float32'
                scale = 'bm25' if key == 'bm25' else 'raw_logit' if key == 'minilm_ce' else 'cosine_unscaled' if key == 'e5_small' else 'cosine'
                if row['dtype'] != dtype or row['score_scale'] != scale: raise RuntimeError('Raw scale/dtype differs')
                check_digest(row['encoder_input_sha256']); check_digest(row['tokenizer_input_sha256'])
                qprefix = expected_contract.get('query_prefix',''); dprefix = expected_contract.get('document_prefix','')
                if row['encoder_input_sha256'] != digest(jb({'query':qprefix+q,'document':dprefix+d})): raise RuntimeError('Encoder prefix/input hash mismatch')
                for field in ('query_token_length','document_or_pair_token_length'):
                    if type(row[field]) is not int or row[field] < 1 or (key != 'bm25' and row[field] > 512): raise RuntimeError('Invalid/truncated token length')
                if key in ('bge_small','e5_small'):
                    if row['tokenizer_input_sha256'] != digest(jb([row['query_token_sha256'],row['document_token_sha256']])): raise RuntimeError('Dense token hashes differ')
                    sources = [(row['query_forward_source'],row['query_token_sha256'],row['query_token_length']), (row['document_forward_source'],row['document_token_sha256'],row['document_or_pair_token_length'])]
                elif key == 'minilm_ce':
                    if row['pair_token_sha256'] != row['tokenizer_input_sha256']: raise RuntimeError('CE joint token hash differs')
                    sources = [(row['pair_forward_source'],row['pair_token_sha256'],row['document_or_pair_token_length'])]
                else: sources = []
                for source, th, n in sources:
                    if source['batch_id'] not in batches or not 0 <= source['batch_row'] < batches[source['batch_id']]['sequences'] or source['unpadded_input_ids_sha256'] != th or source['nonpadding_tokens'] != n:
                        raise RuntimeError('Actual forward token/mask cache source mismatch')
                    for field in ('input_ids_sha256','attention_mask_sha256','unpadded_input_ids_sha256'): check_digest(source[field])
                ck = digest(jb({'configuration_sha256':config_hash,'query':q,'document':d}))
                if ck != row['cache_key_sha256']: raise RuntimeError('Incomplete exact cache key')
                cached = seen.get(ck)
                if cached:
                    if row['execution_mode'] != 'reused_from_exact_pair_cache' or row['cache_source_request_id'] != cached['request_id'] or row['cache_source_candidate_display_index'] != cached['candidate_display_index'] or row['raw_score'] != cached['raw_score'] or row['tokenizer_input_sha256'] != cached['tokenizer_input_sha256']:
                        raise RuntimeError('Exact pair reuse provenance differs')
                else:
                    if row['cache_source_request_id'] is not None or row['cache_source_candidate_display_index'] is not None or row['execution_mode'] == 'reused_from_exact_pair_cache': raise RuntimeError('Unexecuted cache source')
                    seen[ck] = row
                indexed[(key,p['request_id'],pos)] = row
        if manifest['unique_query_document_pairs_scored'] != len(seen) or manifest['reused_candidate_score_occurrences'] != 352-len(seen): raise RuntimeError('Cache occurrence count mismatch')
        manifests[key] = manifest; merged.extend(rows)
    if len(merged) != 1408 or len(indexed) != 1408: raise RuntimeError('Full four-model matrix incomplete')
    return merged, indexed, manifests

def relation(scores): return 0 if scores[0] > scores[1] else 1 if scores[1] > scores[0] else 'TIE'
def original_index(choice, orientation): return choice if choice == 'TIE' else choice if orientation == 0 else 1-choice
def constraint_tuple(c, independent=False):
    if c is None: return None
    return (' '.join(c['subject'].lower().split()),' '.join(c['property'].lower().split()),c.get('dimension'),c.get('unit'),
        c['lower'],c['upper'],c['include_lower'] if independent else c['lower_inclusive'],c['include_upper'] if independent else c['upper_inclusive'])
def spans_valid(query, documents, decision):
    c = decision['constraint']
    if c:
        for field in ('subject','property'):
            b,e = c[field+'_span']
            if not 0 <= b <= e <= len(query) or query[b:e] != c[field]: return False
    for document, parsed in zip(documents,decision['documents']):
        if isinstance(parsed,dict): continue
        for fact in parsed:
            for field in ('subject','property','value'):
                b,e = fact[field+'_span']
                if not 0 <= b <= e <= len(document): return False
                if field == 'value':
                    if not document[b:e].isdigit() or int(document[b:e]) != fact['value']: return False
                elif document[b:e] != fact[field]: return False
    return True
def outcome(relations, gold):
    if any(v == 'TECHNICAL' for v in relations): return 'TECHNICAL'
    if relations[0] != relations[1]: return 'TECHNICAL'
    if relations[0] == 'TIE': return 'TIE'
    return 'WIN' if relations[0] == gold else 'LOSE'
def transition(before, after):
    if before == after: return 'unchanged'
    names = {'WIN':'correct','LOSE':'wrong','TIE':'tie','TECHNICAL':'technical'}
    return names[before]+'_to_'+names[after]
def is_harm(before, after): return before == 'WIN' and after != 'WIN'
def mean(xs): return statistics.mean(xs) if xs else 'NA'
def median(xs): return statistics.median(xs) if xs else 'NA'
def csvfile(rows):
    columns = list(dict.fromkeys(k for row in rows for k in row))
    buf = io.StringIO(newline=''); writer = csv.DictWriter(buf,fieldnames=columns,lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(list,dict,tuple)) else v for k,v in row.items()})
    return buf.getvalue().encode('utf-8')

def derive(lock, main, probes, truths, inputs, maps, rewrites, indexed, manifests, m, captured=None):
    records = {p['query_id']:p for p in main+probes}; truthmap = {p['query_id']:p for p in truths}
    if len(truthmap) != 44 or set(truthmap) != set(records): raise RuntimeError('Independent semantic truth matrix incomplete')
    for p in truths:
        if len(p['candidate_statuses']) != 2 or not set(p['candidate_statuses']).issubset(STATUSES): raise RuntimeError('Invalid independent satisfaction statuses')
    for p in main:
        status = truthmap[p['query_id']]['candidate_statuses']
        if status != ['SATISFIES' if i == p['gold_candidate_index'] else 'VIOLATES' for i in (0,1)]: raise RuntimeError('Private main gold conflicts with sealed independent truth')
    inputmap = {p['request_id']:p for p in inputs}; requestmap = {(p['query_id'],p['method'],p['orientation']):p['request_id'] for p in maps}
    rewritemap = {p['query_id']:p for p in rewrites}
    if len(requestmap) != 176 or len(rewritemap) != 44: raise RuntimeError('Private map/rewrite matrix incomplete')
    capturedmap = {(p['model_key'],p['query_id'],p['orientation']):p for p in captured} if captured is not None else None
    decisions, states = [], {}; rerank_calls = 0
    for key in KEYS:
        for kind, ps in (('main',main),('probe',probes)):
            for p in ps:
                qid = p['query_id']; r = rewritemap[qid]; truth = truthmap[qid]
                if r['original_query'] != p['query'] or r['original_query_sha256'] != digest(p['query'].encode()) or r['rewritten_query_sha256'] != digest(r['rewritten_query'].encode()): raise RuntimeError('Rewrite text/cache identity mismatch')
                state = {'model_key':key,'query_id':qid,'kind':kind,'relations':{},'scores':{},'margins':{},'decisions':[],'latencies':[],
                    'independent_statuses':truth['candidate_statuses'],'rewrite_action':r['action'],'rewrite_changed':r['rewritten_query'] != p['query']}
                for method in ('M0','M1'):
                    relations, margins, score_arrays = [], [], []
                    for orient in (0,1):
                        rid = requestmap[(qid,method,orient)]; payload = inputmap[rid]
                        expected_query = p['query'] if method == 'M0' else r['rewritten_query']
                        expected_docs = list(p['candidates']) if orient == 0 else list(reversed(p['candidates']))
                        if payload['query'] != expected_query or payload['candidates'] != expected_docs: raise RuntimeError('Prepared orientation/method map mismatch')
                        scores = [indexed[(key,rid,i)]['raw_score'] for i in (0,1)]
                        relations.append(original_index(relation(scores),orient)); score_arrays.append(scores)
                        if kind == 'main':
                            gi = p['gold_candidate_index'] if orient == 0 else 1-p['gold_candidate_index']
                            margins.append(scores[gi]-scores[1-gi])
                    state['relations'][method] = relations; state['scores'][method] = score_arrays; state['margins'][method] = margins
                relations = []
                for orient in (0,1):
                    rid = requestmap[(qid,'M0',orient)]; payload = inputmap[rid]; base = state['scores']['M0'][orient]
                    # M2 receives no private IDs, condition, truth, canonical tuple, or probe type.
                    decision = m.rerank(payload['query'],payload['candidates'],base); rerank_calls += 1
                    row = {'model_key':key,'query_id':qid,'kind':kind,'method':'M2','orientation':orient,'M0_source_request_id':rid,
                        'query_sha256':digest(payload['query'].encode()),'candidate_sha256':[digest(d.encode()) for d in payload['candidates']],
                        'decision':decision}
                    if capturedmap is not None:
                        prior = capturedmap[(key,qid,orient)]
                        decision['latency_ns'] = prior['decision']['latency_ns']
                        if jb(row) != jb(prior): raise RuntimeError('Deterministic M2 replay mismatch: '+key+'/'+qid)
                    decisions.append(row); state['decisions'].append(decision); state['latencies'].append(decision['latency_ns'])
                    choice = 0 if decision['choice'] == 'A' else 1 if decision['choice'] == 'B' else 'TIE'
                    relations.append(original_index(choice,orient))
                state['relations']['M2'] = relations
                d0 = state['decisions'][0]
                state['query_complete'] = d0['constraint'] is not None
                state['document_parse_complete'] = all(isinstance(v,list) and bool(v) for v in d0['documents'])
                statuses = [v['status'] for v in d0['constraint_status']]
                state['candidate_attribute_value_complete'] = all(v != 'UNKNOWN' for v in statuses)
                state['UNKNOWN_count'] = statuses.count('UNKNOWN')
                state['safe_override'] = any(v['override_rule_applied'] for v in state['decisions'])
                state['actual_rank_changed'] = state['relations']['M2'] != state['relations']['M0']
                state['spans_grounded_in_text'] = all(spans_valid(inputmap[requestmap[(qid,'M0',o)]]['query'],inputmap[requestmap[(qid,'M0',o)]]['candidates'],state['decisions'][o]) for o in (0,1))
                tc = truth['query_constraint']
                state['query_constraint_independent_match'] = constraint_tuple(d0['constraint']) == constraint_tuple(tc,True) if d0['constraint'] is not None and tc is not None else 'NA_UNPARSED_OR_INDEPENDENT_UNKNOWN'
                state['known_status_errors'] = sum(a != b for a,b in zip(statuses,truth['candidate_statuses']) if a != 'UNKNOWN' and b != 'UNKNOWN')
                state['unverified_known_statuses'] = sum(a != 'UNKNOWN' and b == 'UNKNOWN' for a,b in zip(statuses,truth['candidate_statuses']))
                independent_safe = sorted(truth['candidate_statuses']) == ['SATISFIES','VIOLATES']
                state['wrong_override'] = state['safe_override'] and (not independent_safe or state['known_status_errors'] > 0 or state['query_constraint_independent_match'] is False or not state['spans_grounded_in_text'])
                before, after = m.parse_query(p['query']),m.parse_query(r['rewritten_query'])
                preserved = m.semantic_key(before) == m.semantic_key(after)
                if isinstance(before,m.Abstention): preserved = r['rewritten_query'] == p['query']
                after_statuses = [m.check(after,m.parse_document(d))['status'] for d in p['candidates']]
                state['M1_constraints_preserved'] = preserved and statuses == after_statuses
                state['M1_independent_constraint_match'] = constraint_tuple(dataclasses.asdict(after)) == constraint_tuple(tc,True) if isinstance(after,m.Constraint) and tc is not None else 'NA_UNPARSED_OR_INDEPENDENT_UNKNOWN'
                state['M1_known_status_errors'] = sum(a != b for a,b in zip(after_statuses,truth['candidate_statuses']) if a != 'UNKNOWN' and b != 'UNKNOWN')
                state['M2_reasons'] = [v['reason'] for v in state['decisions']]
                state['original_M0_margin'] = mean(state['margins']['M0'])
                if kind == 'main':
                    state['outcomes'] = {method:outcome(state['relations'][method],p['gold_candidate_index']) for method in METHODS}
                    state['M1_transition'] = transition(state['outcomes']['M0'],state['outcomes']['M1'])
                    state['M2_transition'] = transition(state['outcomes']['M0'],state['outcomes']['M2'])
                states[(key,qid)] = state
    if len(decisions) != 352 or rerank_calls != 352: raise RuntimeError('M2 planned matrix incomplete')
    conditions = []; coverage = []; breakdown = []; overall = {}
    condition_names = sorted({p['condition'] for p in main})
    for key in KEYS:
        ms = [states[(key,p['query_id'])] for p in main]
        original_correct = sum(s['outcomes']['M0'] == 'WIN' for s in ms)
        overall[key] = {'main_planned_queries':32,'probes_planned':12,'methods':{},
            'model_elapsed_ms':manifests[key]['elapsed_ms'],'unique_query_document_pairs_scored':manifests[key]['unique_query_document_pairs_scored'],
            'reused_candidate_score_occurrences':manifests[key]['reused_candidate_score_occurrences'],
            'actual_model_forward_calls':manifests[key]['actual_model_forward_calls'],'actual_model_sequence_occurrences':manifests[key]['actual_model_sequence_occurrences'],
            'M0_original_correct_harm_denominator':original_correct if original_correct else 'NA',
            'query_complete':sum(s['query_complete'] for s in ms),'document_parse_complete':sum(s['document_parse_complete'] for s in ms),
            'candidate_attribute_value_complete':sum(s['candidate_attribute_value_complete'] for s in ms),'UNKNOWN_candidate_occurrences':sum(s['UNKNOWN_count'] for s in ms),
            'safe_override_queries':sum(s['safe_override'] for s in ms),'actual_rank_changed_queries':sum(s['actual_rank_changed'] for s in ms),
            'known_candidate_status_error_queries':sum(s['known_status_errors'] > 0 for s in ms),
            'wrong_override_queries':sum(s['wrong_override'] for s in ms),
            'M1_constraint_preservation_errors':sum(not s['M1_constraints_preserved'] or s['M1_independent_constraint_match'] is False for s in ms),
            'numeric_value_independent_ground_truth_available':False,
            'M2_CPU_latency_ns_mean':mean([n for s in ms for n in s['latencies']]),'M2_CPU_latency_ns_median':median([n for s in ms for n in s['latencies']]),
            'leave_one_template_out_descriptive':{}}
        for method in METHODS:
            counts = Counter(s['outcomes'][method] for s in ms)
            harms = sum(is_harm(s['outcomes']['M0'],s['outcomes'][method]) for s in ms)
            overall[key]['methods'][method] = {'win':counts['WIN'],'lose':counts['LOSE'],'exact_tie':counts['TIE'],'technical':counts['TECHNICAL'],
                'strict_success_full_denominator':counts['WIN']/32,'harm_numerator':harms,'harm_denominator':original_correct if original_correct else 'NA',
                'harm_rate':harms/original_correct if original_correct else 'NA','transitions':dict(Counter(transition(s['outcomes']['M0'],s['outcomes'][method]) for s in ms)),
                'raw_margin_mean':mean([mean(s['margins'][method]) for s in ms]) if method != 'M2' else 'NA_NO_SAME_SCALE_M2_MARGIN',
                'raw_margin_median':median([mean(s['margins'][method]) for s in ms]) if method != 'M2' else 'NA_NO_SAME_SCALE_M2_MARGIN'}
            for condition in condition_names:
                subset = [states[(key,p['query_id'])] for p in main if p['condition'] == condition]
                counts = Counter(s['outcomes'][method] for s in subset)
                valid_subset = [s for s in subset if s['query_complete'] and s['candidate_attribute_value_complete']]
                margins = [mean(s['margins'][method]) for s in subset] if method != 'M2' else []
                conditions.append({'model_key':key,'condition':condition,'method':method,'planned_denominator':16,
                    'win':counts['WIN'],'lose':counts['LOSE'],'exact_tie':counts['TIE'],'technical':counts['TECHNICAL'],
                    'valid_count':16-counts['TECHNICAL'],'strict_success_full_denominator':counts['WIN']/16,
                    'near_tie_1e6':sum(any(abs(v) <= 1e-6 for v in s['margins'][method]) for s in subset) if method != 'M2' else 'NA',
                    'near_tie_1e5':sum(any(abs(v) <= 1e-5 for v in s['margins'][method]) for s in subset) if method != 'M2' else 'NA',
                    'raw_margin_mean':mean(margins) if method != 'M2' else 'NA_NO_SAME_SCALE_M2_MARGIN',
                    'raw_margin_median':median(margins) if method != 'M2' else 'NA_NO_SAME_SCALE_M2_MARGIN',
                    'original_M0_margin_mean':mean([s['original_M0_margin'] for s in subset]),
                    'query_complete':sum(s['query_complete'] for s in subset),'candidate_attribute_value_complete':sum(s['candidate_attribute_value_complete'] for s in subset),
                    'UNKNOWN_queries':sum(s['UNKNOWN_count'] > 0 for s in subset),'safe_override_queries':sum(s['safe_override'] for s in subset),
                    'actual_rank_changed_queries':sum(s['actual_rank_changed'] for s in subset),
                    'parsed_subset_denominator':len(valid_subset),'parsed_subset_win':sum(s['outcomes'][method] == 'WIN' for s in valid_subset),
                    'parsed_subset_success':sum(s['outcomes'][method] == 'WIN' for s in valid_subset)/len(valid_subset) if valid_subset else 'NA',
                    'order_effect_queries':sum(s['relations'][method][0] != s['relations'][method][1] for s in subset)})
        for p in main:
            s = states[(key,p['query_id'])]
            coverage.append({'record_kind':'main','model_key':key,'query_id':p['query_id'],'block_id':p['block_id'],'template_id':p['template_id'],
                'condition':p['condition'],'wording':p['wording'],'planned_group_denominator':32,
                'M0_outcome':s['outcomes']['M0'],'M1_outcome':s['outcomes']['M1'],'M2_outcome':s['outcomes']['M2'],
                'M0_orientation_choices':s['relations']['M0'],'M1_orientation_choices':s['relations']['M1'],'M2_orientation_choices':s['relations']['M2'],
                'M1_transition':s['M1_transition'],'M2_transition':s['M2_transition'],'M1_harm':is_harm(s['outcomes']['M0'],s['outcomes']['M1']),
                'M2_harm':is_harm(s['outcomes']['M0'],s['outcomes']['M2']),'M0_original_correct_harm_denominator':original_correct if original_correct else 'NA',
                'query_complete':s['query_complete'],'document_parse_complete':s['document_parse_complete'],'candidate_attribute_value_complete':s['candidate_attribute_value_complete'],
                'UNKNOWN_count':s['UNKNOWN_count'],'safe_override':s['safe_override'],'actual_rank_changed':s['actual_rank_changed'],
                'original_M0_raw_margin':s['original_M0_margin'],'M2_raw_margin':'NA_NO_SAME_SCALE_M2_MARGIN',
                'M1_action':s['rewrite_action'],'M1_constraints_preserved':s['M1_constraints_preserved'],'M1_independent_constraint_match':s['M1_independent_constraint_match'],
                'query_constraint_independent_match':s['query_constraint_independent_match'],'known_candidate_status_errors':s['known_status_errors'],
                'unverified_known_statuses':s['unverified_known_statuses'],'wrong_override':s['wrong_override'],'spans_grounded_in_visible_text':s['spans_grounded_in_text'],
                'independent_candidate_statuses':s['independent_statuses'],'M2_reasons':s['M2_reasons'],'numeric_value_independent_ground_truth_available':False})
        probe_results = {method:[] for method in METHODS}
        for p in probes:
            s = states[(key,p['query_id'])]; truth = truthmap[p['query_id']]
            clear_nonunique = truth['query_constraint'] is not None and truth['candidate_statuses'] in (['SATISFIES','SATISFIES'],['VIOLATES','VIOLATES'])
            for method in METHODS:
                preserve = s['relations'][method] == s['relations']['M0']
                expected = 'BASELINE_NO_INTERVENTION' if method == 'M0' else 'NO_SAFE_OVERRIDE' if method == 'M2' else 'UNCHANGED_OR_CONSTRAINT_PRESERVING_NORMALIZATION' if clear_nonunique else 'UNCHANGED'
                actual = 'BASELINE_NO_INTERVENTION' if method == 'M0' else '|'.join(s['M2_reasons']) if method == 'M2' else s['rewrite_action']
                mistaken = False if method == 'M0' else (s['safe_override'] or not preserve) if method == 'M2' else (s['rewrite_changed'] and not clear_nonunique) or not s['M1_constraints_preserved'] or s['M1_independent_constraint_match'] is False
                row = {'record_kind':'probe','model_key':key,'query_id':p['query_id'],'probe_id':p['probe_id'],'probe_type':p['probe_type'],'method':method,
                    'planned_group_denominator':12,'expected_action':expected,'actual_action':actual,'preserve_base_order_and_tie':preserve,
                    'mistaken_activation':mistaken,'constraints_preserved':s['M1_constraints_preserved'] if method == 'M1' else 'NA',
                    'independent_candidate_statuses':truth['candidate_statuses'],'expected_satisfaction_metadata':p['expected_satisfaction'],
                    'actual_orientation_choices':s['relations'][method],'reason':s['M2_reasons'] if method == 'M2' else rewritemap[p['query_id']]['reason'] if method == 'M1' else 'ORIGINAL_MODEL_SCORING',
                    'query_complete':s['query_complete'],'document_parse_complete':s['document_parse_complete'],'UNKNOWN_count':s['UNKNOWN_count'],
                    'safe_override':s['safe_override'] if method == 'M2' else False,'wrong_override':s['wrong_override'] if method == 'M2' else False,
                    'gold_accuracy':'NA_NONUNIQUE_OR_APPLICABILITY_PROBE'}
                coverage.append(row); probe_results[method].append(row)
        overall[key]['probes'] = {method:{'planned':12,'mistaken_activation':sum(r['mistaken_activation'] for r in rs),
            'preserved_base_order_and_tie':sum(r['preserve_base_order_and_tie'] for r in rs),'gold_accuracy':'NA'} for method,rs in probe_results.items()}
        for group_kind, group_field in (('block','block_id'),('template','template_id'),('leave_one_template_out','template_id')):
            for group in sorted({p[group_field] for p in main}):
                ps = [p for p in main if (p[group_field] != group if group_kind == 'leave_one_template_out' else p[group_field] == group)]
                ss = [states[(key,p['query_id'])] for p in ps]
                for method in METHODS:
                    counts = Counter(s['outcomes'][method] for s in ss); transitions = Counter(transition(s['outcomes']['M0'],s['outcomes'][method]) for s in ss)
                    row = {'group_kind':group_kind,'group_id':group,'model_key':key,'method':method,'planned_denominator':len(ps),
                        'win':counts['WIN'],'lose':counts['LOSE'],'exact_tie':counts['TIE'],'technical':counts['TECHNICAL'],
                        'strict_success_full_denominator':counts['WIN']/len(ps),'query_complete':sum(s['query_complete'] for s in ss),
                        'safe_override_queries':sum(s['safe_override'] for s in ss),'actual_rank_changed_queries':sum(s['actual_rank_changed'] for s in ss),
                        **{name:transitions[name] for name in ('wrong_to_correct','correct_to_wrong','tie_to_correct','correct_to_tie','wrong_to_tie','tie_to_wrong','unchanged')},
                        'analysis_status':'DESCRIPTIVE_ONLY_NO_INFERENTIAL_STATISTICS'}
                    breakdown.append(row)
                    if group_kind == 'leave_one_template_out': overall[key]['leave_one_template_out_descriptive'].setdefault(method,{})[group] = row['strict_success_full_denominator']
    summary = {'status':'COMPLETE_DERIVED_FROM_FOUR_LOCKED_MODELS','main_queries':32,'safety_probes':12,
        'primary_requires_both_orientations':True,'private_gold_never_method_input':True,'full_planned_denominators_retained':True,
        'no_same_scale_M2_margin':True,'models':overall,'research_logical_requests':704,'neutral_logical_requests':16,
        'unique_M2_logical_requests':352,'total_unique_logical_requests':1072,'logical_request_cap':1200,
        'rerank_computations_per_derivation':rerank_calls,'model_forward_calls':sum(manifests[k]['actual_model_forward_calls'] for k in KEYS),
        'model_sequence_occurrences':sum(manifests[k]['actual_model_sequence_occurrences'] for k in KEYS),
        'candidate_score_rows':1408,'M2_decision_rows':352,'M1_rewrite_calls':44,
        'M1_CPU_latency_ns_mean':mean([r['latency_ns'] for r in rewrites]),'M1_CPU_latency_ns_median':median([r['latency_ns'] for r in rewrites]),
        'latency_scope':'Captured local CPU method timings and per-model elapsed time reported separately; replay retains captured method timings',
        'independent_truth_limitation':'Sealed candidate satisfaction and query constraints; no independently structured candidate numeric-value ground truth. Fact values/spans checked against visible text.',
        'data_designation':sorted({p['data_designation'] for p in main}),'evaluation_scope':'Fixed supplied candidate pairs with a satisfying document already present; exploratory artificial quantity grammar',
        'statistical_inference':'NONE','old_reference_excluded':True,'archived_diagnostic_executed':False,
        'input_model_score_lock_sha256':sha(RUN/'INPUT_MODEL_SCORE_LOCK.json')}
    return {'condition_summary.csv':csvfile(conditions),'coverage_harm_and_probe_results.csv':csvfile(coverage),
        'block_template_transitions.csv':csvfile(breakdown),'OVERALL_METRICS.json':jfile(summary),'M2_DECISIONS.jsonl':jlfile(decisions)}

def analyze(replay_only):
    lock = verify_lock(); m, method_lock = load_method()
    main, probes = data(RUN/lock['main_path'],RUN/lock['probe_path'])
    truths = readj(RUN/lock['semantic_truths_path']); inputs = readj(RUN/lock['inputs_path'])
    maps = readj(RUN/lock['score_map_path']); rewrites = readj(RUN/lock['rewrite_records_path'])
    merged, indexed, manifests = merge_raw(lock,inputs,maps); merged_bytes = jlfile(merged)
    if replay_only:
        captured = readj(RUN/'M2_DECISIONS.jsonl')
        if (RUN/'raw_scores.jsonl').read_bytes() != merged_bytes: raise RuntimeError('Merged raw replay mismatch')
        generated = derive(lock,main,probes,truths,inputs,maps,rewrites,indexed,manifests,m,captured)
        failures = [name for name,b in generated.items() if (RUN/name).read_bytes() != b]
        if failures: raise RuntimeError('Derived replay byte mismatch: '+','.join(failures))
        verification = {'status':'PASS','verified_at_utc':now(),'scope':'Full1408 raw rows and352 deterministic M2 decisions; all derived tables/metrics reproduced byte-for-byte',
            'model_calls':0,'API_calls':0,'new_research_logical_requests':0,'unique_M2_logical_requests':352,
            'actual_rerank_computations_this_replay':352,'actual_rerank_computations_initial_plus_this_replay':704,
            'captured_latency_ns_preserved':True,'all_deterministic_decision_fields_compared':True,
            'output_hashes':{name:digest(b) for name,b in generated.items()},'raw_scores_sha256':digest(merged_bytes),
            'input_model_score_lock_sha256':sha(RUN/'INPUT_MODEL_SCORE_LOCK.json'),'analyzer_sha256':sha(Path(__file__))}
        exclusive(RUN/'REPLAY_VERIFICATION.json',jfile(verification))
        print(json.dumps({'status':'PASS','replay_model_calls':0,'deterministic_decisions_verified':352,'tables_byte_identical':True}))
    else:
        if any((RUN/p).exists() for p in ('raw_scores.jsonl',*ANALYSIS_FILES)): raise FileExistsError('Analysis outputs are immutable')
        generated = derive(lock,main,probes,truths,inputs,maps,rewrites,indexed,manifests,m)
        exclusive(RUN/'raw_scores.jsonl',merged_bytes)
        for name,b in generated.items(): exclusive(RUN/name,b)
        print(json.dumps({'status':'COMPLETE','raw_score_rows':1408,'M2_decision_rows':352,'model_calls':0,'actual_rerank_computations':352}))

def selfcheck():
    # Synthetic arithmetic arrays only; no research files or model/method calls.
    assert original_index(relation([2.0,1.0]),0) == original_index(relation([1.0,2.0]),1) == 0
    assert outcome([0,0],0) == 'WIN' and outcome([1,1],0) == 'LOSE'
    assert outcome(['TIE','TIE'],0) == 'TIE' and outcome([0,1],0) == 'TECHNICAL'
    assert transition('LOSE','WIN') == 'wrong_to_correct' and is_harm('WIN','TIE')
    assert not is_harm('LOSE','WIN')
    xs = [{'a':1,'b':'汉字'},{'a':2,'b':'x'}]
    assert jlfile(xs) == jlfile(json.loads(s) for s in jlfile(xs).decode().splitlines())
    assert csvfile(xs) == csvfile(xs)
    print(json.dumps({'status':'PASS','scope':'Synthetic orientation/tie/harm/serialization contracts only','research_files_read':0,'model_calls':0,'method_calls':0}))

def main():
    ap = argparse.ArgumentParser(description=__doc__); modes = ap.add_mutually_exclusive_group()
    modes.add_argument('--prepare',action='store_true'); modes.add_argument('--replay-only',action='store_true'); modes.add_argument('--selfcheck',action='store_true')
    ap.add_argument('--main',type=Path,default=RUN/'new_eval.jsonl'); ap.add_argument('--probes',type=Path,default=RUN/'safety_probes.jsonl')
    args = ap.parse_args()
    if args.selfcheck: selfcheck()
    elif args.prepare: prepare(args)
    else: analyze(args.replay_only)

if __name__ == '__main__': main()
