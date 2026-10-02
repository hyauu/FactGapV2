"""ALIGN3 offline transport. Neural/BM25 math remains in the frozen adapter."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(r'<LOCAL_PROJECT>')
RUN = Path(__file__).resolve().parents[1]
OLD = ROOT / 'stage22b/runs/stage22b_20260930T083944Z_49e9c6b3'
OUT = RUN / 'scoring'
KEYS = ('bm25', 'bge_small', 'e5_small', 'minilm_ce')
EXPECTED_ADAPTER = 'b85d8ca6d114ca63f14f6b5bade7410c34aa907afe37b4cd6e865e5c141e7c39'
EXPECTED_MODEL_LOCK = '3451c18753970ba63cc6be15c020e9002f2aad9eb2cda81cba4ddd3614abb255'
EXPECTED_OLD_LOCK = '5848e1ba7792a0ad73f158139f3603f91dfadc313535db9563a486e1b56b1e5c'
START_DEADLINE = datetime(2026, 10, 1, 5, 46, tzinfo=timezone.utc)
END_DEADLINE = datetime(2026, 10, 1, 5, 46, tzinfo=timezone.utc)
os.environ.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1',
    TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
    TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='8', MKL_NUM_THREADS='8')

os.environ.update(HF_HOME=str(RUN/'cache/hf'), TORCH_HOME=str(RUN/'cache/torch'), HF_MODULES_CACHE=str(RUN/'cache/modules'), TEMP=str(RUN/'cache'), TMP=str(RUN/'cache'))

def now(): return datetime.now(timezone.utc).isoformat()
def digest(b): return hashlib.sha256(b).hexdigest()
def jb(x): return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def readj(p): return [json.loads(v) for v in p.read_text(encoding='utf-8-sig').splitlines() if v.strip()]
def exclusive(p, x, jsonl=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8', newline='\n') as f:
        if jsonl:
            for row in x: f.write(json.dumps(row, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
        else: f.write(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
def import_path(name, p):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m
def inside_run(p):
    p = p.resolve()
    if not p.is_relative_to(RUN): raise RuntimeError('Input must be in this ALIGN3 run')
    return p

def identity(key):
    prior_run = ROOT/'stage4a/runs/20260930T192807Z_a697a439'
    prior_identity = read(prior_run/'scoring'/f'neutral_precheck_{key}.json')['identity']
    paths = {'adapter': ROOT/'tools/local_score.py', 'model_lock': ROOT/'source_and_model_locks/model_local_lock.json',
        'old_score_lock': OLD/'CONTROL_SCORE_LOCK.json'}
    expected = {'adapter': EXPECTED_ADAPTER, 'model_lock': EXPECTED_MODEL_LOCK, 'old_score_lock': EXPECTED_OLD_LOCK}
    checks = []
    for label, p in paths.items():
        actual = sha(p)
        if actual != expected[label]: raise RuntimeError('Changed selected identity: ' + label)
        checks.append({'path': str(p), 'sha256': actual, 'matches': True})
    old = read(paths['old_score_lock'])
    binding_path = OLD/'BASELINE_BINDING.json'
    if sha(binding_path) != old['baseline_binding_sha256']: raise RuntimeError('Changed baseline binding')
    binding = read(binding_path)
    pre_path = ROOT/'source_and_model_locks/ADAPTER_PREFLIGHT_LOCK.json'
    pre = read(pre_path)
    if pre['status'] != 'PASS' or pre['code_sha256'] != EXPECTED_ADAPTER or old['inherited_adapter_sha256'] != EXPECTED_ADAPTER:
        raise RuntimeError('Inherited adapter preflight mismatch')
    model_lock = read(paths['model_lock'])
    contract = dict(old['target_models'][key])
    selected_files = []
    if key != 'bm25':
        entry = model_lock['models'][key]
        for field in ('repo_id', 'revision', 'snapshot_path'):
            if entry[field] != contract[field]: raise RuntimeError('Model identity differs: ' + field)
        if pre['models'][key]['revision'] != entry['revision']: raise RuntimeError('Preflight revision mismatch')
        snapshot = Path(entry['snapshot_path'])
        for row in binding['checks']:
            p = Path(row['path'])
            if row['scope'] == 'selected_model_tokenizer_config' and p.parent == snapshot:
                inherited = next(v for v in prior_identity['model_artifacts'] if Path(v['path']) == p)
                if inherited['sha256'] != row['expected_sha256'] or p.stat().st_size != inherited['bytes']: raise RuntimeError('Selected model identity differs: '+p.name)
                actual = inherited['sha256'] if p.name == 'model.safetensors' else sha(p)
                if actual != row['expected_sha256']: raise RuntimeError('Selected tokenizer/config changed: '+p.name)
                selected_files.append({'path': str(p), 'bytes': p.stat().st_size, 'sha256': actual, 'current_verification': 'inherited_weight_SHA_plus_current_path_size_mtime' if p.name == 'model.safetensors' else 'current_SHA256', 'mtime_ns': p.stat().st_mtime_ns})
        if len(selected_files) != 6: raise RuntimeError('Expected six selected model/config/tokenizer files')
    else:
        contract['corpus'] = 'ALIGN3 EVAL unique candidate full texts only, fixed across all three conditions'
        contract['corpus_size_is_inherited'] = False
    observer_path = OLD/'code/run_bounded_local.py'
    observer_expected = next(v['sha256'] for v in old['file_locks'] if v['path'] == 'code/run_bounded_local.py')
    if sha(observer_path) != observer_expected: raise RuntimeError('Inherited resource observer changed')
    m = import_path('frozen_stage4a_adapter', paths['adapter'])
    if m.MAX_TOK != 512 or m.PFX_BGE != old['target_models']['bge_small']['query_prefix']: raise RuntimeError('Adapter constants differ')
    observer = import_path('inherited_stage22b_memory', observer_path)
    result = {'status': 'PASS', 'created_at_utc': now(), 'selected_identity_checks': checks,
        'adapter_preflight_sha256': sha(pre_path), 'baseline_binding_sha256': sha(binding_path),
        'resource_observer_sha256': observer_expected, 'model_artifacts': selected_files,
        'model_contract': contract, 'wrapper_sha256': sha(Path(__file__))}
    return m, observer, result

class Guard:
    """Reuse the prior Windows memory sampler; one bounded local process only."""
    def __init__(self, observer, path):
        self.observer, self.path = observer, path
        self.stop = threading.Event(); self.lock = threading.RLock()
        self.state = {'status': 'RUNNING', 'created_at_utc': now(), 'pid': os.getpid(), 'samples': 0,
            'RAM_cap_fraction': .6, 'VRAM_cap_fraction': .8, 'CPU_threads_cap': 8, 'sample_period_seconds': .5,
            'start_deadline_utc': START_DEADLINE.isoformat(), 'end_deadline_utc': END_DEADLINE.isoformat(),
            'max_process_peak_working_set_bytes': 0, 'max_cuda_allocated_bytes': 0,
            'max_cuda_reserved_bytes': 0, 'max_total_cuda_used_bytes': 0}
    def sample(self):
        with self.lock:
            v = self.observer.memory(); self.state['samples'] += 1; self.state['last_memory'] = v
            self.state['max_process_peak_working_set_bytes'] = max(self.state['max_process_peak_working_set_bytes'], v['process_peak_working_set_bytes'])
            if v['process_peak_working_set_bytes'] > .6*v['total_physical_bytes']: raise RuntimeError('PROCESS_RAM_CAP_EXCEEDED')
            if datetime.now(timezone.utc) >= END_DEADLINE: raise RuntimeError('REPORT_ONLY_DEADLINE_REACHED')
            torch = sys.modules.get('torch')
            if torch is not None and hasattr(torch, 'get_num_threads'):
                if torch.get_num_threads() > 8: raise RuntimeError('CPU_THREAD_CAP_EXCEEDED')
                if hasattr(torch, 'cuda') and torch.cuda.is_initialized():
                    free, total = torch.cuda.mem_get_info(0)
                    allocated = int(torch.cuda.max_memory_allocated(0)); reserved = int(torch.cuda.max_memory_reserved(0))
                    self.state['max_cuda_allocated_bytes'] = max(self.state['max_cuda_allocated_bytes'], allocated)
                    self.state['max_cuda_reserved_bytes'] = max(self.state['max_cuda_reserved_bytes'], reserved)
                    self.state['max_total_cuda_used_bytes'] = max(self.state['max_total_cuda_used_bytes'], total-free)
                    self.state['total_cuda_bytes'] = total
                    if max(allocated, reserved, total-free) > .8*total: raise RuntimeError('VRAM_CAP_EXCEEDED')
            return v
    def monitor(self):
        while not self.stop.wait(.5):
            try: self.sample()
            except BaseException as e:
                self.state.update(status='RESOURCE_OR_TIME_FAILURE', error=repr(e), terminal_at_utc=now())
                try: exclusive(self.path, self.state)
                finally: os._exit(2)
    def __enter__(self):
        self.sample(); self.thread = threading.Thread(target=self.monitor, daemon=True); self.thread.start()
        return self
    def __exit__(self, kind, error, tb):
        self.stop.set(); self.thread.join(timeout=2)
        try: self.sample()
        finally:
            self.state.update(status='COMPLETE' if error is None else 'FAILED', error=repr(error) if error else None, terminal_at_utc=now())
            self.state['process_RAM_fraction'] = self.state['max_process_peak_working_set_bytes']/self.state['last_memory']['total_physical_bytes']
            torch = sys.modules.get('torch')
            self.state['configured_torch_intraop_threads'] = int(torch.get_num_threads()) if torch else None
            exclusive(self.path, self.state)

def runtime():
    x = {'python': sys.executable, 'python_executable_exists': Path(sys.executable).is_file(),
        'python_version': sys.version, 'local_only': True, 'paid_API_calls': 0, 'downloads': 0}
    torch = sys.modules.get('torch')
    if torch:
        import transformers
        x.update(torch=torch.__version__, transformers=transformers.__version__, cuda_available=torch.cuda.is_available(),
            torch_compute_threads=torch.get_num_threads(), CUDA=torch.version.cuda)
    return x

class ForwardAudit:
    def __init__(self, m, guard): self.m, self.guard, self.batches, self.by_token = m, guard, [], {}
    def hook(self, model, args, kwargs):
        self.guard.sample()
        arrays = {k: v.detach().cpu().tolist() for k, v in kwargs.items() if k in ('input_ids', 'attention_mask', 'token_type_ids')}
        batch_id = len(self.batches)
        self.batches.append({'batch_id': batch_id, 'sequences': len(arrays['input_ids']),
            'padded_width': len(arrays['input_ids'][0]), 'forward_tensors_sha256': digest(jb(arrays))})
        for i, ids in enumerate(arrays['input_ids']):
            mask = arrays['attention_mask'][i]; n = sum(mask)
            if n > 512: raise RuntimeError('Token context exceeded')
            unpadded = [t for t, keep in zip(ids, mask) if keep]
            record = {'batch_id': batch_id, 'batch_row': i, 'nonpadding_tokens': n,
                'padded_width': len(ids), 'input_ids_sha256': digest(jb(ids)),
                'attention_mask_sha256': digest(jb(mask)), 'unpadded_input_ids_sha256': digest(jb(unpadded)),
                'token_type_ids_sha256': digest(jb(arrays['token_type_ids'][i])) if 'token_type_ids' in arrays else None}
            self.by_token.setdefault(record['unpadded_input_ids_sha256'], []).append(record)

def load(key, m, guard):
    if key == 'bm25': return None, None, 'cpu', None, None
    import torch
    torch.set_num_threads(min(8, os.cpu_count() or 1)); torch.set_num_interop_threads(1)
    tok, model, device, entry = m.load_neural(key)
    guard.sample()
    if any(p.dtype != torch.float32 for p in model.parameters()): raise RuntimeError('Neural parameters must be FP32')
    audit = ForwardAudit(m, guard)
    model.register_forward_pre_hook(audit.hook, with_kwargs=True)
    return tok, model, device, entry, audit

def calculate(key, pairs, corpus, m, tok, model, device):
    scored = m.bm25_scores(pairs, corpus) if key == 'bm25' else m.neural_scores(key, pairs, tok, model, device)
    if set(scored) != set(pairs) or any(not math.isfinite(x[0]) for x in scored.values()): raise RuntimeError('Missing/nonfinite original score')
    return scored

def precheck(key, m, observer, ident):
    receipt_path = OUT/f'neutral_precheck_{key}.json'; resource_path = OUT/f'resources_precheck_{key}.json'
    if receipt_path.exists() or resource_path.exists(): raise FileExistsError('Neutral precheck is immutable')
    q = 'Find the passage about a silver lantern.'
    docs = ['A silver lantern is on the table.', 'A copper bucket is beside the door.']
    pairs = [(q, d) for d in docs]
    with Guard(observer, resource_path) as guard:
        tok, model, device, entry, audit = load(key, m, guard)
        a = calculate(key, pairs, docs, m, tok, model, device)
        b = calculate(key, list(reversed(pairs)), docs, m, tok, model, device)
        c = calculate(key, [pairs[0]], docs, m, tok, model, device)
        aa = calculate(key, pairs, docs, m, tok, model, device)
        differences = {'fresh_array_order_max_abs': max(abs(a[p][0]-b[p][0]) for p in pairs),
            'batch_vs_single_abs': abs(a[pairs[0]][0]-c[pairs[0]][0]),
            'fresh_AA_max_abs': max(abs(a[p][0]-aa[p][0]) for p in pairs)}
        if max(differences.values()) > 1e-4: raise RuntimeError('Neutral order/batch/A-A mismatch')
        if any(a[p][1:] != b[p][1:] or a[p][1:] != aa[p][1:] for p in pairs): raise RuntimeError('Neutral token mismatch')
        old_scores = read(ROOT/'source_and_model_locks/ADAPTER_PREFLIGHT_LOCK.json')['models'][key]['neutral_scores']
        prior_difference = max(abs(a[p][0]-old_scores[i]) for i,p in enumerate(pairs))
        if prior_difference > 1e-3: raise RuntimeError('Inherited neutral reference mismatch')
        receipt = {'status': 'PASS', 'created_at_utc': now(), 'model_key': key, 'identity': ident,
            'environment': runtime(), 'device': device, 'neutral_query': q, 'neutral_candidates': docs,
            'scores_forward_display': [a[p][0] for p in pairs], 'scores_reverse_display': [b[p][0] for p in reversed(pairs)],
            'scores_fresh_AA_display': [aa[p][0] for p in pairs], 'singleton_score': c[pairs[0]][0],
            'differences': differences, 'tolerance_abs': 1e-4, 'inherited_neutral_max_abs_difference': prior_difference,
            'token_records': [list(a[p][1:]) for p in pairs], 'logical_neutral_ranking_requests': 4,
            'neutral_candidate_score_occurrences': 7, 'fresh_adapter_calls': 4, 'pair_cache_used': False,
            'research_queries_read': 0, 'research_forward_calls': 0,
            'actual_model_forward_calls': len(audit.batches) if audit else 0,
            'actual_model_sequence_occurrences': sum(v['sequences'] for v in audit.batches) if audit else 0,
            'forward_batches': audit.batches if audit else [], 'resource_receipt': str(resource_path)}
        exclusive(receipt_path, receipt)
    print(json.dumps({'status': 'PASS', 'model_key': key, 'receipt': str(receipt_path), 'differences': differences}))

def tokens(key, q, d, m, tok, audit):
    if key == 'bm25':
        qt, dt = m.termlist(q), m.termlist(d)
        return {'query_token_sha256': digest(jb(qt)), 'document_token_sha256': digest(jb(dt)), 'pair_token_sha256': None,
            'query_forward_source': None, 'document_forward_source': None, 'pair_forward_source': None}
    if key == 'minilm_ce':
        enc = tok(q, d, truncation=False); th = digest(jb(enc['input_ids']))
        return {'query_token_sha256': None, 'document_token_sha256': None, 'pair_token_sha256': th,
            'query_forward_source': None, 'document_forward_source': None, 'pair_forward_source': audit.by_token[th][0]}
    qh = digest(jb(tok(m.prefix(key, q, True), truncation=False)['input_ids']))
    dh = digest(jb(tok(m.prefix(key, d, False), truncation=False)['input_ids']))
    return {'query_token_sha256': qh, 'document_token_sha256': dh, 'pair_token_sha256': None,
        'query_forward_source': audit.by_token[qh][0], 'document_forward_source': audit.by_token[dh][0], 'pair_forward_source': None}

def score(args, m, observer, ident):
    key = args.model
    inp, corp = inside_run(args.inputs), inside_run(args.corpus)
    if sha(inp) != args.input_sha256 or sha(corp) != args.corpus_sha256: raise RuntimeError('Prospective input/corpus hash mismatch')
    neutral_path = OUT/f'neutral_precheck_{key}.json'; neutral = read(neutral_path)
    stable = lambda x: {k: v for k, v in x.items() if k != 'created_at_utc'}
    if neutral['status'] != 'PASS' or stable(neutral['identity']) != stable(ident): raise RuntimeError('Current identities differ from neutral precheck')
    payloads, corpus_records = readj(inp), readj(corp)
    if len(payloads) != 144: raise RuntimeError('Expected exactly 144 planned logical requests per model')
    corpus = []
    for p in corpus_records:
        if set(p) != {'text'} or not isinstance(p['text'], str) or not p['text']: raise RuntimeError('Corpus allowlist is text only')
        corpus.append(p['text'])
    if not corpus or len(corpus) != len(set(corpus)): raise RuntimeError('Corpus must be nonempty unique rendered texts')
    request_ids = set()
    for p in payloads:
        if set(p) != {'request_id', 'query', 'candidates'} or not isinstance(p['request_id'], str) or not p['request_id']:
            raise RuntimeError('Request allowlist mismatch')
        if p['request_id'] in request_ids: raise RuntimeError('Duplicate neutral request ID')
        request_ids.add(p['request_id'])
        if not isinstance(p['query'], str) or not p['query'] or not isinstance(p['candidates'], list) or len(p['candidates']) != 2:
            raise RuntimeError('Malformed query/candidates')
        if any(not isinstance(d, str) or d not in corpus for d in p['candidates']): raise RuntimeError('Candidate missing from locked visible corpus')
    paths = [OUT/f'raw_{key}.jsonl', OUT/f'manifest_{key}.json', OUT/f'forward_audit_{key}.json', OUT/f'resources_score_{key}.json']
    if any(p.exists() for p in paths): raise FileExistsError('Per-model outputs are immutable')
    pairs = sorted({(p['query'], d) for p in payloads for d in p['candidates']})
    config = {'model_key': key, 'contract': ident['model_contract'], 'adapter_sha256': EXPECTED_ADAPTER,
        'model_artifacts': ident['model_artifacts'], 'model_lock_sha256': EXPECTED_MODEL_LOCK,
        'corpus_file_sha256': args.corpus_sha256, 'wrapper_sha256': ident['wrapper_sha256']}
    config_hash = digest(jb(config)); started = time.perf_counter()
    with Guard(observer, paths[3]) as guard:
        tok, model, device, entry, audit = load(key, m, guard)
        scored = calculate(key, pairs, corpus, m, tok, model, device)
        guard.sample(); elapsed_ms = (time.perf_counter()-started)*1000
        dtype = 'float64' if key == 'bm25' else 'float32'
        scale = 'bm25' if key == 'bm25' else 'raw_logit' if key == 'minilm_ce' else 'cosine_unscaled' if key == 'e5_small' else 'cosine'
        revision = ident['model_contract']['revision']; rows, seen = [], {}
        for ordinal, p in enumerate(payloads):
            for pos, d in enumerate(p['candidates']):
                q = p['query']; pair = (q, d); value, th, qlen, dlen = scored[pair]
                cache_key = digest(jb({'configuration_sha256': config_hash, 'query': q, 'document': d}))
                source = seen.get(cache_key); detail = tokens(key, q, d, m, tok, audit)
                calculated_th = digest(jb({'query_terms': m.termlist(q), 'document_terms': m.termlist(d)})) if key == 'bm25' else detail['pair_token_sha256'] if key == 'minilm_ce' else digest(jb([detail['query_token_sha256'], detail['document_token_sha256']]))
                if calculated_th != th: raise RuntimeError('Original tokenizer hash mismatch')
                execution = 'reused_from_exact_pair_cache' if source else 'computed_original_bm25' if key == 'bm25' else 'computed_from_fresh_deduplicated_embeddings' if key in ('bge_small', 'e5_small') else 'executed_batched'
                row = {'run_id': RUN.name, 'dataset_version': 'alignment3-eval72-template-shared-exploratory', 'model_key': key,
                    'model_revision': revision, 'request_id': p['request_id'], 'request_ordinal': ordinal,
                    'candidate_display_index': pos, 'query_text': q, 'candidate_text': d,
                    'payload_sha256': digest(jb({'query': q, 'candidates': p['candidates']})),
                    'query_text_sha256': digest(q.encode()), 'candidate_text_sha256': digest(d.encode()),
                    'encoder_input_sha256': digest(jb({'query': m.prefix(key, q, True), 'document': m.prefix(key, d, False)})),
                    'tokenizer_input_sha256': th, 'query_token_length': qlen, 'document_or_pair_token_length': dlen,
                    'token_length_semantics': 'joint_pair_length_in_both_original_adapter_fields' if key == 'minilm_ce' else 'separate_query_and_document',
                    'raw_score': value, 'score_scale': scale, 'dtype': dtype, 'configuration_sha256': config_hash,
                    'corpus_sha256': args.corpus_sha256, 'cache_key_sha256': cache_key, 'execution_mode': execution,
                    'cache_source_request_id': source['request_id'] if source else None,
                    'cache_source_candidate_display_index': source['candidate_display_index'] if source else None,
                    'elapsed_ms_amortized_per_unique_pair': elapsed_ms/len(pairs), 'status': 'OK', 'technical_error_code': None,
                    **detail}
                rows.append(row)
                if source is None: seen[cache_key] = {'request_id': p['request_id'], 'candidate_display_index': pos}
        if len(rows) != 288 or len(seen) != len(pairs): raise RuntimeError('Incomplete planned matrix')
        exclusive(paths[0], rows, jsonl=True)
        exclusive(paths[2], {'model_key': key, 'forward_batches': audit.batches if audit else [],
            'actual_model_forward_calls': len(audit.batches) if audit else 0,
            'actual_model_sequence_occurrences': sum(v['sequences'] for v in audit.batches) if audit else 0,
            'unique_query_embeddings': len({q for q,d in pairs}) if key in ('bge_small','e5_small') else 0,
            'unique_document_embeddings': len({d for q,d in pairs}) if key in ('bge_small','e5_small') else 0})
        manifest = {'status': 'COMPLETE', 'created_at_utc': now(), 'model_key': key, 'model_revision': revision,
            'identity': ident, 'environment': runtime(), 'device': device, 'dtype': dtype, 'score_scale': scale,
            'configuration': config, 'configuration_sha256': config_hash, 'logical_ranking_requests': 144,
            'score_rows': 288, 'unique_query_document_pairs_scored': len(pairs),
            'reused_candidate_score_occurrences': 288-len(pairs), 'actual_model_forward_calls': len(audit.batches) if audit else 0,
            'actual_model_sequence_occurrences': sum(v['sequences'] for v in audit.batches) if audit else 0,
            'elapsed_ms': elapsed_ms, 'input_sha256': args.input_sha256, 'corpus_sha256': args.corpus_sha256,
            'raw_sha256': sha(paths[0]), 'forward_audit_sha256': sha(paths[2]), 'neutral_receipt_sha256': sha(neutral_path),
            'query_document_pairs_are_not_forward_count': True,
            'research_metadata_read': False, 'old_result_caches_read': False, 'resource_receipt': str(paths[3])}
        exclusive(paths[1], manifest)
    print(json.dumps({'status': 'COMPLETE', 'model_key': key, 'logical_ranking_requests': 144,
        'score_rows': 288, 'unique_query_document_pairs': len(pairs), 'elapsed_ms': round(elapsed_ms)}))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model', required=True, choices=KEYS); ap.add_argument('--precheck', action='store_true')
    ap.add_argument('--inputs', type=Path, default=OUT/'scoring_inputs.jsonl')
    ap.add_argument('--corpus', type=Path, default=OUT/'scoring_corpus.jsonl')
    ap.add_argument('--input-sha256'); ap.add_argument('--corpus-sha256')
    args = ap.parse_args()
    if datetime.now(timezone.utc) >= START_DEADLINE: raise RuntimeError('New model batch deadline reached')
    if not args.precheck and (not args.input_sha256 or not args.corpus_sha256): ap.error('Target scoring requires prospective --input-sha256 and --corpus-sha256')
    m, observer, ident = identity(args.model)
    if args.precheck: precheck(args.model, m, observer, ident)
    else: score(args, m, observer, ident)

if __name__ == '__main__': main()
