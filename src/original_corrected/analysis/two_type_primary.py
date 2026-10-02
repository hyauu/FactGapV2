from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import t

TYPES = ("relative_temporal", "unit_normalization_clean")
TYPE_SHORT = {TYPES[0]: "temporal", TYPES[1]: "unit"}
EPSILONS = (1e-8, 1e-7, 1e-6, 1e-5)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(value), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def family_weighted(frame: pd.DataFrame, value: str) -> float:
    values = frame.groupby(["transformation_type", "family_id"], sort=True)[value].mean()
    return float(values.groupby(level=0).mean().mean())


def family_series(frame: pd.DataFrame, value: str, all_families: dict[str, list[str]]) -> dict[str, pd.Series]:
    grouped = frame.groupby(["transformation_type", "family_id"], sort=True)[value].mean()
    return {typ: grouped.get(typ, pd.Series(dtype=float)).reindex(all_families[typ]) for typ in TYPES}


def collapse_inputs(scores: Path):
    retrieval_raw = pd.read_parquet(scores / "retriever_scores.parquet")
    controlled = pd.read_parquet(scores / "reranker_controlled.parquet")
    pipeline_raw = pd.read_parquet(scores / "pipeline_reranking.parquet")
    bm25_raw = pd.read_parquet(scores / "bm25_scores.parquet")
    retrieval = retrieval_raw.drop_duplicates(["item_id", "query_form", "corpus_condition", "model_id"]).copy()
    pipeline = pipeline_raw.drop_duplicates(["item_id", "query_form", "corpus_condition", "retriever_id", "reranker_id"]).copy()
    bm25 = bm25_raw.copy()
    docs = {"retrieval_raw": retrieval_raw, "controlled": controlled, "pipeline_raw": pipeline_raw, "bm25_raw": bm25_raw}
    return retrieval, controlled, pipeline, bm25, docs


def make_contributions(endpoint: dict, retrieval: pd.DataFrame, controlled: pd.DataFrame, pipeline: pd.DataFrame, all_families: dict[str, list[str]]):
    claim, model = endpoint["claim"], endpoint["model_or_pipeline"]
    counts = {}
    if claim == "R1":
        block = retrieval[(retrieval.model_id == model) & (retrieval.corpus_condition == "hard") & retrieval.query_form.isin(["D0", "P0"])].copy()
        pivot = block.pivot(index=["item_id", "family_id", "transformation_type"], columns="query_form", values="strict_pair_correct").reset_index()
        pivot["value"] = pivot["D0"].astype(float) - pivot["P0"].astype(float)
        contrib = family_series(pivot, "value", all_families)
        d0 = block[block.query_form == "D0"].copy(); d0["v"] = d0.strict_pair_correct.astype(float)
        d0acc = family_series(d0, "v", all_families)
        d0acc = {k: float(v.mean()) for k, v in d0acc.items()}
        affected = pivot.groupby(["transformation_type", "family_id"]).value.apply(lambda x: bool((x > 0).any()))
        affected = {typ: int(affected.get(typ, pd.Series(dtype=bool)).sum()) for typ in TYPES}
        validity = all(d0acc[x] >= 0.90 for x in TYPES)
        breadth = all(affected[x] >= 3 for x in TYPES) and sum(affected.values()) >= 6
        counts = {"d0_accuracy": d0acc, "affected_families": affected, "affected_families_total": sum(affected.values()), "n": len(pivot)}
        gates = {"validity": validity, "breadth": breadth}
    elif claim == "R2":
        block = controlled[(controlled.reranker_id == model) & controlled.query_form.isin(["D0", "P0"])].copy()
        d0 = block[block.query_form == "D0"].copy(); d0["v"] = (d0.margin > endpoint["epsilon"]).astype(float)
        p0 = block[block.query_form == "P0"].copy(); p0["value"] = (p0.margin <= endpoint["epsilon"]).astype(float)
        contrib = family_series(p0, "value", all_families)
        d0acc = {k: float(v.mean()) for k, v in family_series(d0, "v", all_families).items()}
        failures = p0.groupby(["transformation_type", "family_id"]).value.apply(lambda x: bool((x > 0).any()))
        failures = {typ: int(failures.get(typ, pd.Series(dtype=bool)).sum()) for typ in TYPES}
        validity = all(d0acc[x] >= 0.90 for x in TYPES)
        breadth = all(failures[x] >= 3 for x in TYPES) and sum(failures.values()) >= 6
        counts = {"d0_accuracy": d0acc, "failure_families": failures, "failure_families_total": sum(failures.values()), "n": len(p0)}
        gates = {"validity": validity, "breadth": breadth}
    else:
        retriever_id, reranker_id = model.split("->")
        block = pipeline[(pipeline.retriever_id == retriever_id) & (pipeline.reranker_id == reranker_id) & (pipeline.query_form == "P0") & (pipeline.corpus_condition == "hard")].copy()
        eligible = block[block.eligible & block.before_correct].copy()
        numer = eligible.groupby(["transformation_type", "family_id"]).corrupted.sum()
        denom = eligible.groupby(["transformation_type", "family_id"]).size()
        contrib = {}
        for typ in TYPES:
            idx = pd.MultiIndex.from_product([[typ], all_families[typ]], names=["transformation_type", "family_id"])
            n = numer.reindex(idx, fill_value=0).astype(float)
            d = denom.reindex(idx, fill_value=0).astype(float)
            ratio = n / d.replace(0, np.nan)
            ratio.index = ratio.index.droplevel(0)
            contrib[typ] = ratio
        eligible_families = int(denom.size)
        corrupt_families_raw = eligible[eligible.corrupted].groupby("transformation_type").family_id.nunique()
        corrupt_families = {typ: int(corrupt_families_raw.get(typ, 0)) for typ in TYPES}
        eligibility = len(eligible) >= 50 and eligible_families >= 20
        breadth = all(corrupt_families[x] >= 3 for x in TYPES) and sum(corrupt_families.values()) >= 6
        counts = {"eligible_denominator": len(eligible), "eligible_families": eligible_families, "corruptions": int(eligible.corrupted.sum()), "corruption_families": corrupt_families, "corruption_families_total": sum(corrupt_families.values())}
        gates = {"eligibility": eligibility, "breadth": breadth}
    return contrib, gates, counts


def quantile(values: np.ndarray, q: tuple[float, float]) -> list[float]:
    finite = values[np.isfinite(values)]
    return [math.nan, math.nan] if not len(finite) else list(map(float, np.quantile(finite, q)))


def boundary_degenerate_types(
    contributions: dict[str, pd.Series], type_intervals: dict[str, list[float]]
) -> list[str]:
    """Return retained types with constant family outcomes and a boundary-collapsed CI."""
    flagged = []
    for typ in TYPES:
        values = contributions[typ].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        interval = type_intervals[typ]
        constant = len(values) > 0 and bool(np.all(values == values[0]))
        collapsed = all(math.isfinite(float(x)) for x in interval) and interval[0] == interval[1]
        at_boundary = collapsed and interval[0] in {0.0, 1.0}
        if constant and at_boundary:
            flagged.append(typ)
    return flagged


def r3_bootstrap_is_defined(undefined_fraction: float, max_fraction: float) -> bool:
    """Return whether an R3 bootstrap satisfies the locked undefined-ratio gate."""
    return math.isfinite(float(undefined_fraction)) and float(undefined_fraction) <= float(max_fraction)


def map_global_status(endpoints: list[dict]) -> str:
    """Implement Sections 12.1--12.3 of the sealed two-type amendment."""
    by_id = {endpoint["endpoint"]: endpoint for endpoint in endpoints}
    r1 = ("R1-BGE", "R1-E5")
    r2 = ("R2-BGE-reranker", "R2-legacy-cross-encoder")
    r3 = (
        "R3-BGE_to_BGE-reranker",
        "R3-BGE_to_legacy-cross-encoder",
        "R3-E5_to_BGE-reranker",
    )

    def all_supported(ids: tuple[str, ...]) -> bool:
        return all(by_id[name]["status"] == "SUPPORTED" for name in ids)

    if all_supported(r1) and (all_supported(r2) or all_supported(r3)):
        return "SUPPORTED"

    disqualifying = {"BOUNDARY_DEGENERATE", "INSUFFICIENT_ELIGIBILITY", "INCOMPLETE", "INTEGRITY_BLOCKED"}
    precise_null = True
    for endpoint in endpoints:
        if endpoint["status"] in disqualifying:
            precise_null = False
            break
        tau = float(endpoint["tau"])
        for typ in TYPES:
            upper = endpoint["type_simultaneous"][typ][1]
            if not math.isfinite(float(upper)) or float(upper) > tau:
                precise_null = False
                break
        if not precise_null:
            break
    return "NOT_SUPPORTED" if precise_null else "INCONCLUSIVE"


def analyze(scores: Path, config_path: Path, output: Path, dataset: Path) -> dict:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    analysis_dir = output / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    retrieval, controlled, pipeline, bm25, raw = collapse_inputs(scores)
    pairs = read_jsonl(dataset / "pairs.jsonl")
    all_families = {typ: sorted({p["family_id"] for p in pairs if p["transformation_type"] == typ}) for typ in TYPES}
    if [len(all_families[x]) for x in TYPES] != [12, 10]:
        raise RuntimeError("unexpected family structure")
    rng = np.random.default_rng(cfg["bootstrap"]["seed"])
    b = cfg["bootstrap"]["replicates"]
    indices = {typ: rng.integers(0, len(all_families[typ]), size=(b, len(all_families[typ]))) for typ in TYPES}
    ordinary_q = tuple(cfg["bootstrap"]["ordinary_quantiles"])
    simultaneous_q = tuple(cfg["bootstrap"]["simultaneous_quantiles"])
    endpoints, contribution_rows, bootstrap_arrays = [], [], {}
    for spec in cfg["endpoints"]:
        spec = {**spec, "epsilon": cfg["tie_epsilon"]}
        contrib, gates, counts = make_contributions(spec, retrieval, controlled, pipeline, all_families)
        estimates, boots = {}, {}
        for typ in TYPES:
            values = contrib[typ].to_numpy(dtype=float)
            estimates[typ] = float(np.nanmean(values)) if np.isfinite(values).any() else math.nan
            sampled = values[indices[typ]]
            defined = np.isfinite(sampled).sum(axis=1)
            boot = np.nansum(sampled, axis=1) / np.where(defined, defined, np.nan)
            boots[typ] = boot
            for family, value in contrib[typ].items():
                contribution_rows.append({"endpoint": spec["endpoint"], "claim": spec["claim"], "model_or_pipeline": spec["model_or_pipeline"], "transformation_type": typ, "family_id": family, "contribution": value})
        tau = float(spec["tau"])
        joint = np.minimum(boots[TYPES[0]] - tau, boots[TYPES[1]] - tau)
        joint_point = min(estimates[x] - tau for x in TYPES) if all(math.isfinite(estimates[x]) for x in TYPES) else math.nan
        invalid = float((~np.isfinite(joint)).mean())
        type_ci = {x: quantile(boots[x], ordinary_q) for x in TYPES}
        type_sim = {x: quantile(boots[x], simultaneous_q) for x in TYPES}
        joint_ci = quantile(joint, ordinary_q)
        joint_sim = quantile(joint, simultaneous_q)
        boundary_types = boundary_degenerate_types(contrib, type_ci)
        if spec["claim"] == "R3":
            max_invalid = float(cfg["gates"]["r3_max_undefined_bootstrap_fraction"])
            counts["undefined_bootstrap_fraction"] = invalid
            gates["bootstrap_defined"] = r3_bootstrap_is_defined(invalid, max_invalid)
            gates["eligibility"] = gates["eligibility"] and gates["bootstrap_defined"]
        if spec["claim"] == "R3" and not gates["eligibility"]:
            status = "INSUFFICIENT_ELIGIBILITY"
        elif boundary_types:
            status = "BOUNDARY_DEGENERATE"
        elif spec["claim"] in {"R1", "R2"} and not gates["validity"]:
            status = "VALIDITY_FAIL"
        elif not gates["breadth"]:
            status = "INSUFFICIENT_BREADTH"
        elif math.isfinite(joint_sim[0]) and joint_sim[0] > 0:
            status = "SUPPORTED"
        else:
            status = "INCONCLUSIVE"
        endpoint = {
            "endpoint": spec["endpoint"], "claim": spec["claim"], "model_or_pipeline": spec["model_or_pipeline"], "tau": tau, "status": status,
            "gates": gates, "counts": counts, "type_estimates": estimates, "type_ci95": type_ci, "type_simultaneous": type_sim,
            "joint_estimate": joint_point, "joint_ci95": joint_ci, "joint_simultaneous": joint_sim,
            "invalid_bootstrap_fraction": invalid, "boundary_degenerate": bool(boundary_types),
            "boundary_degenerate_types": boundary_types,
        }
        endpoints.append(endpoint)
        bootstrap_arrays[f"{spec['endpoint']}__temporal"] = boots[TYPES[0]]
        bootstrap_arrays[f"{spec['endpoint']}__unit"] = boots[TYPES[1]]
        bootstrap_arrays[f"{spec['endpoint']}__joint_J"] = joint
    np.savez_compressed(analysis_dir / "bootstrap_outputs.npz", **bootstrap_arrays)
    pd.DataFrame(contribution_rows).to_csv(analysis_dir / "family_contributions.csv", index=False)

    csv_rows = []
    for e in endpoints:
        csv_rows.append({
            "endpoint": e["endpoint"], "claim": e["claim"], "model_or_pipeline": e["model_or_pipeline"], "tau": e["tau"], "status": e["status"],
            "joint_estimate": e["joint_estimate"], "joint_ci95_low": e["joint_ci95"][0], "joint_ci95_high": e["joint_ci95"][1],
            "joint_simultaneous_low": e["joint_simultaneous"][0], "joint_simultaneous_high": e["joint_simultaneous"][1],
            "invalid_bootstrap_fraction": e["invalid_bootstrap_fraction"], "boundary_degenerate": e["boundary_degenerate"],
            "temporal_estimate": e["type_estimates"][TYPES[0]], "temporal_ci95_low": e["type_ci95"][TYPES[0]][0], "temporal_ci95_high": e["type_ci95"][TYPES[0]][1],
            "temporal_simultaneous_low": e["type_simultaneous"][TYPES[0]][0], "temporal_simultaneous_high": e["type_simultaneous"][TYPES[0]][1],
            "unit_estimate": e["type_estimates"][TYPES[1]], "unit_ci95_low": e["type_ci95"][TYPES[1]][0], "unit_ci95_high": e["type_ci95"][TYPES[1]][1],
            "unit_simultaneous_low": e["type_simultaneous"][TYPES[1]][0], "unit_simultaneous_high": e["type_simultaneous"][TYPES[1]][1],
            "gates_json": json.dumps(e["gates"], sort_keys=True), "counts_json": json.dumps(e["counts"], sort_keys=True),
        })
    primary = pd.DataFrame(csv_rows)
    primary.to_csv(analysis_dir / "primary_endpoints.csv", index=False)
    primary.to_csv(output / "primary_endpoints.csv", index=False)

    # Leave-one-family-out point-estimate stability.
    loo = []
    cframe = pd.DataFrame(contribution_rows)
    for e in endpoints:
        for typ in TYPES:
            for family in all_families[typ]:
                estimates = {}
                for tname in TYPES:
                    block = cframe[(cframe.endpoint == e["endpoint"]) & (cframe.transformation_type == tname)]
                    if tname == typ:
                        block = block[block.family_id != family]
                    values = block.contribution.to_numpy(dtype=float)
                    estimates[tname] = float(np.nanmean(values)) if np.isfinite(values).any() else math.nan
                joint = min(estimates[x] - e["tau"] for x in TYPES) if all(math.isfinite(estimates[x]) for x in TYPES) else math.nan
                loo.append({"endpoint": e["endpoint"], "omitted_family": family, "omitted_type": typ, "temporal_estimate": estimates[TYPES[0]], "unit_estimate": estimates[TYPES[1]], "joint_J": joint, "threshold_relation": "above" if math.isfinite(joint) and joint > 0 else "at_or_below" if math.isfinite(joint) else "undefined"})
    pd.DataFrame(loo).to_csv(analysis_dir / "leave_one_family_out.csv", index=False)

    # Secondary per-form metrics.
    sec = []
    for model, block in retrieval.groupby("model_id", sort=True):
        for (typ, form), x in block[block.corpus_condition == "hard"].groupby(["transformation_type", "query_form"], sort=True):
            sec.append({"analysis": "retriever", "model": model, "transformation_type": typ, "query_form": form, "strict_accuracy": family_weighted(x.assign(v=x.strict_pair_correct.astype(float)), "v"), "mean_margin": float(x.pair_margin.mean()), "gold_at_1": float(x.gold_at_1.mean()), "gold_at_5": float(x.gold_at_5.mean()), "gold_at_10": float(x.gold_at_10.mean()), "pair_at_10": float(x.pair_at_10.mean()), "n": len(x)})
    for model, block in controlled.groupby("reranker_id", sort=True):
        for (typ, form), x in block.groupby(["transformation_type", "query_form"], sort=True):
            sec.append({"analysis": "controlled_reranker", "model": model, "transformation_type": typ, "query_form": form, "strict_accuracy": family_weighted(x.assign(v=(x.margin > cfg['tie_epsilon']).astype(float)), "v"), "mean_margin": float(x.margin.mean()), "gold_at_1": math.nan, "gold_at_5": math.nan, "gold_at_10": math.nan, "pair_at_10": math.nan, "n": len(x)})
    secondary = pd.DataFrame(sec)
    secondary.to_csv(analysis_dir / "secondary_model_metrics.csv", index=False)

    # BM25 pair diagnostics.
    bm25_pair = []
    for keys, x in bm25.groupby(["item_id", "family_id", "transformation_type", "source_mode", "query_form", "corpus_condition"], sort=False):
        row = dict(zip(["item_id", "family_id", "transformation_type", "source_mode", "query_form", "corpus_condition"], keys))
        gold = x[x.candidate_role_private == "gold"].iloc[0]
        neg = x[x.candidate_role_private == "critical_negative"].iloc[0]
        row.update({"margin": float(gold.raw_score - neg.raw_score), "strict_correct": bool(gold.raw_score - neg.raw_score > cfg["tie_epsilon"])})
        bm25_pair.append(row)
    bm25_pair = pd.DataFrame(bm25_pair)
    bm25_diag = bm25_pair[bm25_pair.corpus_condition == "hard"].groupby(["transformation_type", "query_form"], sort=True).agg(strict_accuracy=("strict_correct", "mean"), mean_margin=("margin", "mean"), n=("item_id", "size")).reset_index()
    bm25_diag.to_csv(analysis_dir / "bm25_diagnostics.csv", index=False)

    # Pipeline counts, descriptive.
    pipe_diag = pipeline.groupby(["retriever_id", "reranker_id", "transformation_type", "query_form", "corpus_condition"], sort=True).agg(n=("item_id", "size"), eligible=("eligible", "sum"), initial_w=("before_correct", "sum"), after_w=("after_correct", "sum"), corrupted=("corrupted", "sum"), recovered=("recovered", "sum")).reset_index()
    pipe_diag.to_csv(analysis_dir / "pipeline_diagnostics.csv", index=False)

    supported = {e["endpoint"] for e in endpoints if e["status"] == "SUPPORTED"}
    global_status = map_global_status(endpoints)
    summary = {
        "schema_version": "phase1_scoring.corrective_result_summary.v1", "created_at": now(), "status": global_status,
        "bootstrap": {"method": "family-clustered within retained transformation type", "replicates": b, "seed": cfg["bootstrap"]["seed"], "primary_quantiles": list(simultaneous_q)},
        "accepted_item_count": len(pairs), "family_count": sum(map(len, all_families.values())), "c0_equals_d0": True, "c0_score_source": "D0",
        "endpoints": endpoints, "supported_endpoints": sorted(supported), "generator_run": False, "answer_generator_run": False,
    }
    write_json(output / "result_summary.json", summary)
    write_json(analysis_dir / "status_mapping.json", {"global_status": global_status, "supported_endpoints": sorted(supported), "rule": cfg["global_decision_mapping"]})

    report = ["# FactGap corrective role-neutral confirmatory analysis", "", f"Status: **{global_status}**", "", "The exact locked two-type analysis was rerun on the corrective role-neutral scores. The original role-coded run remains preserved separately.", "", "## Primary endpoints", "", "| Endpoint | Temporal estimate | Unit estimate | Joint J | Simultaneous CI | Status |", "|---|---:|---:|---:|---:|---|"]
    for e in endpoints:
        fmt = lambda x: "NA" if x is None or not math.isfinite(float(x)) else f"{float(x):.3f}"
        report.append(f"| {e['endpoint']} | {fmt(e['type_estimates'][TYPES[0]])} | {fmt(e['type_estimates'][TYPES[1]])} | {fmt(e['joint_estimate'])} | [{fmt(e['joint_simultaneous'][0])}, {fmt(e['joint_simultaneous'][1])}] | {e['status']} |")
    report += ["", "R2 is the family-weighted P0 strict failure fraction with D0 as a validity gate; it is not a paired D0−P0 effect estimator. R3 is conditional on initially correct eligible P0 cases and remains descriptive when eligibility gates fail.", "", "The two-type intersection statistic is determined by the weaker component. When temporal performance is at ceiling, the unit component determines J."]
    (output / "confirmatory_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    manifest_files = [analysis_dir / "primary_endpoints.csv", analysis_dir / "bootstrap_outputs.npz", analysis_dir / "family_contributions.csv", analysis_dir / "leave_one_family_out.csv", analysis_dir / "secondary_model_metrics.csv", analysis_dir / "bm25_diagnostics.csv", analysis_dir / "pipeline_diagnostics.csv", output / "primary_endpoints.csv", output / "result_summary.json", output / "confirmatory_report.md"]
    write_json(output / "analysis_manifest.json", {"schema_version": "factgap.corrective.analysis_manifest.v1", "created_at": now(), "status": "COMPLETE", "config_sha256": sha(config_path), "files": [{"path": p.relative_to(output).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in manifest_files]})
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Regenerate the locked FactGap two-type primary analysis from raw score tables.")
    ap.add_argument("--scores", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--dataset", type=Path, required=True)
    args = ap.parse_args()
    result = analyze(args.scores.resolve(), args.config.resolve(), args.output.resolve(), args.dataset.resolve())
    print(json.dumps({"status": result["status"], "supported_endpoints": result["supported_endpoints"]}, indent=2))


if __name__ == "__main__":
    main()
