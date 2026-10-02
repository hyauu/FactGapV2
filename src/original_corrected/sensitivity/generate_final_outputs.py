from __future__ import annotations

import argparse
import difflib
import json
import math
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import t

TYPES = ("relative_temporal", "unit_normalization_clean")
FORMS = ("D0", "D1", "P0", "P1")
EPSILONS = (1e-8, 1e-7, 1e-6, 1e-5)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def family_weighted(frame: pd.DataFrame, value: str) -> float:
    return float(frame.groupby("family_id")[value].mean().mean())


def pair_retriever(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path)
    return d[(d.corpus_condition == "hard") & (d.candidate_role_private == "gold")].copy()


def conversion_label(pair: dict) -> str:
    proof = pair["unit_proof"]
    mapping = {
        ("kilometer", "meter"): "km→m",
        ("kilogram", "gram"): "kg→g",
        ("liter", "milliliter"): "L→mL",
        ("hour", "minute"): "h→min",
    }
    return mapping[(proof["source_unit"], proof["target_unit"])]


def model_form_summary(retriever: pd.DataFrame, reranker: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model, g in retriever.groupby("model_id"):
        for (typ, form), x in g.groupby(["transformation_type", "query_form"]):
            rows.append({"component": "Retriever", "model": model, "type": typ, "form": form,
                         "accuracy": family_weighted(x, "strict_pair_correct")})
    for model, g in reranker.groupby("reranker_id"):
        for (typ, form), x in g.groupby(["transformation_type", "query_form"]):
            rows.append({"component": "Reranker", "model": model, "type": typ, "form": form,
                         "accuracy": family_weighted(x, "strict_pair_correct")})
    return pd.DataFrame(rows)


def family_form_summary(retriever: pd.DataFrame, reranker: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model, g in retriever.groupby("model_id"):
        for (typ, form, family), x in g.groupby(["transformation_type", "query_form", "family_id"]):
            rows.append({"component": "Retriever", "model": model, "type": typ, "form": form,
                         "family_id": family, "accuracy": float(x.strict_pair_correct.mean())})
    for model, g in reranker.groupby("reranker_id"):
        for (typ, form, family), x in g.groupby(["transformation_type", "query_form", "family_id"]):
            rows.append({"component": "Reranker", "model": model, "type": typ, "form": form,
                         "family_id": family, "accuracy": float(x.strict_pair_correct.mean())})
    return pd.DataFrame(rows)


def unit_breakdown(pairs: list[dict], retriever: pd.DataFrame, reranker: pd.DataFrame) -> pd.DataFrame:
    unit = [p for p in pairs if p["transformation_type"] == TYPES[1]]
    item_class = {p["pair_id"]: conversion_label(p) for p in unit}
    item_family = {p["pair_id"]: p["family_id"] for p in unit}
    rows = []
    for label in ["kg→g", "km→m", "L→mL", "h→min"]:
        ids = {item for item, cls in item_class.items() if cls == label}
        families = {item_family[item] for item in ids}
        row = {"conversion": label, "n": len(ids), "families": len(families)}
        for model, key in [("bge-base", "bge_retriever_accuracy"), ("e5-base", "e5_retriever_accuracy"),
                           ("qwen3-embedding", "qwen3_retriever_accuracy")]:
            x = retriever[(retriever.item_id.isin(ids)) & (retriever.query_form == "P0") & (retriever.model_id == model)]
            row[key] = family_weighted(x, "strict_pair_correct")
        for model, prefix in [("bge-reranker", "bge_reranker"), ("legacy-cross-encoder", "minilm_reranker")]:
            x = reranker[(reranker.item_id.isin(ids)) & (reranker.query_form == "P0") & (reranker.reranker_id == model)]
            acc = family_weighted(x, "strict_pair_correct")
            row[f"{prefix}_accuracy"] = acc
            row[f"{prefix}_failure"] = 1 - acc
        rows.append(row)
    return pd.DataFrame(rows)


def contamination_table(old_r: pd.DataFrame, old_x: pd.DataFrame, new_r: pd.DataFrame, new_x: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("E5 retriever, temporal D0", "retriever", "e5-base", TYPES[0], "D0"),
        ("MiniLM reranker, temporal D0", "reranker", "legacy-cross-encoder", TYPES[0], "D0"),
        ("BGE reranker, unit P0", "reranker", "bge-reranker", TYPES[1], "P0"),
    ]
    rows = []
    for label, component, model, typ, form in specs:
        if component == "retriever":
            old = old_r[(old_r.model_id == model) & (old_r.transformation_type == typ) & (old_r.query_form == form)]
            new = new_r[(new_r.model_id == model) & (new_r.transformation_type == typ) & (new_r.query_form == form)]
        else:
            old = old_x[(old_x.reranker_id == model) & (old_x.transformation_type == typ) & (old_x.query_form == form)]
            new = new_x[(new_x.reranker_id == model) & (new_x.transformation_type == typ) & (new_x.query_form == form)]
        rows.append({"model_condition": label, "original_accuracy": family_weighted(old, "strict_pair_correct"),
                     "corrected_accuracy": family_weighted(new, "strict_pair_correct")})
    return pd.DataFrame(rows)


def write_tex_tables(out: Path, units: pd.DataFrame, contamination: pd.DataFrame) -> None:
    lines = [r"\begin{tabular}{lrrrrrrr}", r"\toprule", "Conversion & $n$ & Fam. & BGE ret. & E5 ret. & Qwen ret. & BGE re. & MiniLM re. " + r"\\", r"\midrule"]
    tex_label = {"kg→g": r"kg$\rightarrow$g", "km→m": r"km$\rightarrow$m", "L→mL": r"L$\rightarrow$mL", "h→min": r"h$\rightarrow$min"}
    for _, r in units.iterrows():
        lines.append(f"{tex_label[r.conversion]} & {int(r.n)} & {int(r.families)} & {r.bge_retriever_accuracy:.3f} & {r.e5_retriever_accuracy:.3f} & {r.qwen3_retriever_accuracy:.3f} & {r.bge_reranker_accuracy:.3f} & {r.minilm_reranker_accuracy:.3f} " + r"\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (out / "table_unit_conversion.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    lines = [r"\begin{tabular}{lrr}", r"\toprule", "Model / condition & Original & Corrected " + r"\\", r"\midrule"]
    for _, r in contamination.iterrows():
        lines.append(f"{r.model_condition} & {r.original_accuracy:.3f} & {r.corrected_accuracy:.3f} " + r"\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (out / "table_contamination_effect.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_figure(out: Path, summary: pd.DataFrame, families: pd.DataFrame) -> None:
    selected = [("Retriever", "bge-base", "BGE retriever"), ("Retriever", "e5-base", "E5 retriever"),
                ("Reranker", "bge-reranker", "BGE reranker"), ("Reranker", "legacy-cross-encoder", "MiniLM reranker")]
    colors = ["#2f5f8f", "#3f8f6f", "#b25742", "#7a5195"]
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.65), sharey=True)
    positions = np.arange(len(FORMS), dtype=float)
    offsets = np.linspace(-.12, .12, len(selected))
    for ax, typ, title in zip(axes, TYPES, ["Temporal literal-lure", "Cross-unit mismatch"]):
        for ((component, model, label), color, offset) in zip(selected, colors, offsets):
            f = families[(families.component == component) & (families.model == model) & (families.type == typ)]
            for j, form in enumerate(FORMS):
                values = f[f.form == form].accuracy.to_numpy(float)
                ax.scatter(np.full(len(values), positions[j] + offset), values, s=8, color=color,
                           alpha=.18, linewidths=0, zorder=1)
            x = summary[(summary.component == component) & (summary.model == model) & (summary.type == typ)].set_index("form")
            ax.plot(positions, [x.loc[f, "accuracy"] for f in FORMS], marker="o", linewidth=1.7,
                    label=label, color=color, zorder=3)
        ax.set_xticks(positions, FORMS); ax.set_title(title, fontsize=9); ax.set_ylim(-.03, 1.03); ax.set_xlabel("Query form"); ax.grid(axis="y", alpha=.25)
    axes[0].set_ylabel("Family-weighted pair accuracy")
    handles, labels = axes[0].get_legend_handles_labels(); fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=7.5)
    fig.tight_layout(rect=(0, .12, 1, 1)); fig.savefig(out / "figure_query_forms.pdf", bbox_inches="tight"); fig.savefig(out / "figure_query_forms.png", dpi=220, bbox_inches="tight"); plt.close(fig)


def small_cluster(analysis: Path, out: Path) -> None:
    x = pd.read_csv(analysis / "family_contributions.csv"); x = x[x.endpoint == "R2-BGE-reranker"]; rows = []; qmatch = 1 - .05 / 14
    for typ, g in x.groupby("transformation_type"):
        v = g.contribution.dropna().to_numpy(float); n = len(v); mean = float(v.mean()); se = float(v.std(ddof=1) / math.sqrt(n)); ordinary = float(t.ppf(.975, n - 1)); matched = float(t.ppf(qmatch, n - 1))
        rows.append({"type": typ, "families": n, "mean": mean, "se": se, "ordinary_low": mean - ordinary * se, "ordinary_high": mean + ordinary * se, "matched_low": mean - matched * se, "matched_high": mean + matched * se})
    pd.DataFrame(rows).to_csv(out / "small_cluster_sensitivity.csv", index=False)


def cluster_variance(frame: pd.DataFrame, cols: list[str]) -> tuple[float, float, int]:
    w = frame.weight.to_numpy(float); y = frame.failure.to_numpy(float); mu = float((w * y).sum() / w.sum()); scores = pd.Series(w * (y - mu), index=frame.index)
    grouped = scores.groupby(frame[cols].astype(str).agg("|".join, axis=1)).sum().to_numpy(float); n = len(grouped); var = (n / (n - 1)) * float(np.square(grouped).sum()) / (w.sum() ** 2) if n > 1 else math.nan
    return mu, var, n


def value_sensitivity(dataset: Path, reranker_path: Path, out: Path) -> None:
    pairs = {x["pair_id"]: x for x in read_jsonl(dataset / "pairs.jsonl")}; d = pd.read_parquet(reranker_path); d = d[(d.reranker_id == "bge-reranker") & (d.query_form == "P0")].copy(); d["failure"] = d.margin <= 1e-8
    d["target_value"] = d.item_id.map(lambda item: str(pairs[item]["gold_fact"]["value"])); family_n = d.groupby(["transformation_type", "family_id"]).size().rename("family_n"); type_nf = d.groupby("transformation_type").family_id.nunique(); d = d.join(family_n, on=["transformation_type", "family_id"]); d["weight"] = 1 / d.transformation_type.map(type_nf) / d.family_n
    rows = []
    for typ, x in d.groupby("transformation_type"):
        mu, vv, nv = cluster_variance(x, ["target_value"]); _, vf, nf = cluster_variance(x, ["family_id"]); _, vi, ni = cluster_variance(x, ["family_id", "target_value"]); se = math.sqrt(max(vv, 0)); crit = float(t.ppf(.975, nv - 1)); crossed = math.sqrt(max(vf + vv - vi, 0)); df = min(nv, nf) - 1; ccrit = float(t.ppf(.975, df))
        rows.append({"type": typ, "unique_values": nv, "estimate": mu, "value_se": se, "value_low": mu - crit * se, "value_high": mu + crit * se, "family_value_intersections": ni, "crossed_se": crossed, "crossed_low": mu - ccrit * crossed, "crossed_high": mu + ccrit * crossed})
    pd.DataFrame(rows).to_csv(out / "value_and_crossed_cluster_sensitivity.csv", index=False)


def numerical_audits(reranker_path: Path, postfreeze_path: Path, out: Path) -> None:
    d = pd.read_parquet(reranker_path); rows = []
    for model, g in d.groupby("reranker_id"):
        for eps in EPSILONS: rows.append({"model": model, "epsilon": eps, "near_zero": int((g.margin.abs() <= eps).sum()), "total": len(g)})
    pd.DataFrame(rows).to_csv(out / "tie_threshold_audit.csv", index=False)
    q = d[d.reranker_id == "qwen3-reranker"]; sat = {"model": "qwen3-reranker", "decisions": len(q), "score_min": float(min(q.gold_score.min(), q.counterpart_score.min())), "score_max": float(max(q.gold_score.max(), q.counterpart_score.max())), "absolute_margin_quantiles": {str(p): float(q.margin.abs().quantile(p)) for p in (0, .25, .5, .75, 1)}}
    (out / "qwen_saturation_audit.json").write_text(json.dumps(sat, indent=2) + "\n", encoding="utf-8")
    power = pd.read_csv(postfreeze_path); power.to_csv(out / "postfreeze_sensitivity.csv", index=False); power[((power.true_effect == .15) & (power.family_icc == .3)) | ((power.true_effect == .2) & power.family_icc.isin([.1, .3, .5]))].to_csv(out / "postfreeze_sensitivity_summary.csv", index=False)


def distractor_audit(original_dataset: Path, corrected_dataset: Path, out: Path) -> None:
    report = {}
    for label, dataset in (("original", original_dataset), ("corrected", corrected_dataset)):
        docs = {x["doc_id"]: x for x in read_jsonl(dataset / "documents.jsonl")}; corpora = [x for x in read_jsonl(dataset / "corpora.jsonl") if x["condition"] == "hard"]; counts = Counter()
        for corpus in corpora:
            ids = corpus["ordered_doc_ids"]; texts = [docs[i]["text"] for i in ids]; freq = Counter(texts); gold = docs[ids[0]]["text"]; counterpart = docs[ids[1]]["text"]; topical = [docs[i]["text"] for i in ids if docs[i]["role"] == "topical_distractor"]; similarity = max(difflib.SequenceMatcher(None, gold, text).ratio() for text in topical); typ = docs[ids[0]]["fact"]["transformation_type"]
            counts["hard_corpora"] += 1; counts["any_exact_duplicate"] += any(n > 1 for n in freq.values()); counts["gold_exact_duplicate"] += freq[gold] > 1; counts["counterpart_exact_duplicate"] += freq[counterpart] > 1; counts[f"{typ}_gold_topical_similarity_ge_0_90"] += similarity >= .90; counts[f"{typ}_gold_topical_similarity_ge_0_95"] += similarity >= .95
        report[label] = dict(counts)
    (out / "distractor_redundancy_audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--corrected-dataset", type=Path, required=True); p.add_argument("--original-dataset", type=Path, required=True); p.add_argument("--corrected-raw", type=Path, required=True); p.add_argument("--original-raw", type=Path, required=True); p.add_argument("--corrected-analysis", type=Path, required=True); p.add_argument("--postfreeze", type=Path, required=True); p.add_argument("--output", type=Path, required=True); args = p.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    pairs = read_jsonl(args.corrected_dataset / "pairs.jsonl"); cr = pair_retriever(args.corrected_raw / "retriever_scores.parquet"); cx = pd.read_parquet(args.corrected_raw / "reranker_controlled.parquet"); oldr = pair_retriever(args.original_raw / "retriever_scores.parquet"); oldx = pd.read_parquet(args.original_raw / "reranker_controlled.parquet")
    summary = model_form_summary(cr, cx); families = family_form_summary(cr, cx); units = unit_breakdown(pairs, cr, cx); contamination = contamination_table(oldr, oldx, cr, cx); summary.to_csv(args.output / "query_form_accuracy.csv", index=False); families.to_csv(args.output / "family_query_form_accuracy.csv", index=False); units.to_csv(args.output / "unit_conversion_breakdown.csv", index=False); contamination.to_csv(args.output / "contamination_effect.csv", index=False); write_tex_tables(args.output, units, contamination); make_figure(args.output, summary, families); small_cluster(args.corrected_analysis, args.output); value_sensitivity(args.corrected_dataset, args.corrected_raw / "reranker_controlled.parquet", args.output); numerical_audits(args.corrected_raw / "reranker_controlled.parquet", args.postfreeze, args.output); distractor_audit(args.original_dataset, args.corrected_dataset, args.output); print(json.dumps({"status": "PASS", "output": str(args.output), "unit_rows": len(units)}, indent=2))


if __name__ == "__main__":
    main()
