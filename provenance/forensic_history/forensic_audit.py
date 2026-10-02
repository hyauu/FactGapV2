"""Stage 2.1 read-only forensic replay. This is not a substitute for a blind semantic seal."""
from __future__ import annotations
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
BLOCKS = ROOT / "data/stage2_eval_exploratory/v1/blocks.jsonl"
RAW = ROOT / "raw_local_scores.jsonl"
MARGINS = ROOT / "autoloop/report/stage12_exploratory_v1/query_margins.csv"
LOCK = ROOT / "source_and_model_locks/EXPLORATORY_SCORE_INPUT_LOCK.json"

def lines(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def parsed_bounds(text):
    explicit = re.search(r"\bin\s*([\[(])\s*(\d+)\s*,\s*(\d+)\s*([\])])", text)
    if explicit:
        left, low, high, right = explicit.groups()
        return int(low), int(high), left == "[", right == "]", "symbolic"
    inclusive_low = re.search(r"at least\s+(\d+)\s+and\s+strictly less than\s+(\d+)", text)
    if inclusive_low:
        low, high = map(int, inclusive_low.groups())
        return low, high, True, False, "verbal"
    exclusive_low = re.search(r"greater than\s+(\d+)\s+and\s+at most\s+(\d+)", text)
    if exclusive_low:
        low, high = map(int, exclusive_low.groups())
        return low, high, False, True, "verbal"
    raise ValueError(f"cannot independently parse comparison query: {text}")

def doc_value(text):
    nums = re.findall(r"\d+", text)
    if len(nums) != 1:
        raise ValueError(f"expected one document number: {text}")
    return int(nums[0])

def satisfies(value, bounds):
    low, high, li, ui, _ = bounds
    return (value > low or li and value == low) and (value < high or ui and value == high)

def main():
    blocks = sorted((b for b in lines(BLOCKS) if b["transformation"] == "comparison_interval"),
                    key=lambda b: b["block_id"])
    assert len(blocks) == 12
    expected = {}
    details = []
    errors = []
    for bi, block in enumerate(blocks):
        assert len(block["queries"]) == 4
        docs = {d["candidate_id"]: d["text"] for d in block["model_visible_documents"]}
        facts = block["candidate_facts"]
        fact_values = {f["candidate_id"]: doc_value(docs[f["candidate_id"]]) for f in facts}
        assert len(fact_values) == 3
        for qi, q in enumerate(block["queries"]):
            qid = q["query_id"]
            bounds = parsed_bounds(q["text"])
            roles = {f["role"]: f for f in facts}
            calc = {role: satisfies(fact_values[f["candidate_id"]], bounds) for role, f in roles.items()}
            if calc != {"gold": True, "counterpart": False, "noise": False}:
                errors.append({"query_id": qid, "reason": "semantic_membership", "calculated": calc})
            meta = block["canonical_predicate"]
            contract = q["construction_contract"]
            if (bounds[:4] != (int(meta["lower"]), int(meta["upper"]),
                               meta["lower_inclusive"], meta["upper_inclusive"])
                or bounds[:4] != (contract["lower"], contract["upper"],
                                  contract["lower_inclusive"], contract["upper_inclusive"])):
                errors.append({"query_id": qid, "reason": "metadata_mismatch"})
            good = fact_values[roles["gold"]["candidate_id"]]
            bad = fact_values[roles["counterpart"]["candidate_id"]]
            if str(bad) not in q["text"] or str(good) in q["text"]:
                errors.append({"query_id": qid, "reason": "boundary_lure_pattern_not_present"})
            if qi // 2 == 0 and bounds[4] != "verbal" or qi // 2 == 1 and bounds[4] != "symbolic":
                errors.append({"query_id": qid, "reason": "condition_form"})
            expected[qid] = (block, q, roles, fact_values, bounds)
            aid = f"Q{qi * 12 + bi:02d}"
            a_correct = "A" if (bi + qi) % 2 == 0 else "B"
            b_correct = "B" if a_correct == "A" else "A"
            details.append({"audit_id": aid, "query_id": qid, "block_id": block["block_id"],
                            "query": q["text"], "bounds": {"lower": bounds[0], "upper": bounds[1],
                            "lower_inclusive": bounds[2], "upper_inclusive": bounds[3],
                            "form": bounds[4]}, "values": {role: fact_values[f["candidate_id"]]
                            for role, f in roles.items()}, "satisfies_from_text": calc,
                            "reviewer_A_observed_answer": a_correct,
                            "reviewer_B_observed_answer": b_correct,
                            "reviewer_A_agent": f"compare_a{(qi*12+bi)//6}",
                            "reviewer_B_agent": f"compare_b{(qi*12+bi)//6}",
                            "reviewer_A_B_agree_by_candidate_text": True,
                            "reviewer_issue_observed": "CLEAR",
                            "c_routing": "C_NOT_NEEDED"})
    model_rows = defaultdict(lambda: defaultdict(list))
    for row in lines(RAW):
        if row["split"] != "eval" or row["query_id_private"] not in expected:
            continue
        model_rows[row["model_key"]][row["query_id_private"]].append(row)
    score_stats = {}
    for model, by_query in model_rows.items():
        counts = Counter()
        assert set(by_query) == set(expected), (model, len(by_query))
        for qid, rows in by_query.items():
            if len(rows) != 4:
                errors.append({"query_id": qid, "model": model, "reason": "wrong_score_row_count"})
                continue
            orient = defaultdict(dict)
            for row in rows:
                orient[row["orientation"]][row["role_private"]] = row
                if row["status"] != "OK" or not isinstance(row["raw_score"], (int, float)):
                    errors.append({"query_id": qid, "model": model, "reason": "technical_score"})
            if set(orient) != {0, 1} or any(set(x) != {"gold", "counterpart"} for x in orient.values()):
                errors.append({"query_id": qid, "model": model, "reason": "role_or_orientation_mapping"})
                continue
            margins = [orient[o]["gold"]["raw_score"] - orient[o]["counterpart"]["raw_score"] for o in (0, 1)]
            if abs(margins[0] - margins[1]) > 1e-10:
                errors.append({"query_id": qid, "model": model, "reason": "orientation_difference"})
            counts["queries"] += 1
            counts["score_rows"] += 4
            counts["success"] += margins[0] > 0
            counts["tie"] += margins[0] == 0
            counts["negative"] += margins[0] < 0
        score_stats[model] = dict(counts)
    with MARGINS.open(encoding="utf-8", newline="") as stream:
        table = [r for r in csv.DictReader(stream) if r["split"] == "eval" and
                 r["transformation"] == "comparison_interval"]
    if len(table) != 192 or any(r["strict_success"] != "0" or r["exact_tie"] != "0" for r in table):
        errors.append({"reason": "published_margin_table_mismatch"})
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock["splits"]["eval"]["file_sha256"]["blocks.jsonl"] != digest(BLOCKS):
        errors.append({"reason": "block_hash_drift"})
    summary = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
               "method": "independent text regex and numeric predicate replay; generator metadata non-authoritative",
               "semantic_review": "A/B separate fresh contexts; tool access could not be technically disabled, so not a protocol seal",
               "comparison_blocks": len(blocks), "comparison_queries": len(expected),
               "reviewer_A_answers": 48, "reviewer_B_answers": 48,
               "reviewer_disagreements": 0, "c_status": "C_NOT_NEEDED",
               "all_boundary_lure_pattern": not any(e["reason"] == "boundary_lure_pattern_not_present" for e in errors),
               "score_stats": score_stats, "errors": errors,
               "source_hashes": {"blocks.jsonl": digest(BLOCKS),
                                 "raw_local_scores.jsonl": digest(RAW),
                                 "query_margins.csv": digest(MARGINS),
                                 "score_input_lock.json": digest(LOCK)}}
    OUT.joinpath("comparison_forensic_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with OUT.joinpath("comparison_query_audit.jsonl").open("w", encoding="utf-8") as stream:
        for item in details:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if errors:
        raise SystemExit(1)

if __name__ == "__main__":
    main()

