from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

ROLE_ID = re.compile(r"\s+ttc-r1-(?:relative_temporal|unit_normalization_clean)-\d+-p\d+-(?:G|N|T\d+)\b")
ARCHIVE_ID = re.compile(r"^(Archive note)\s+[0-9A-F]{8}:")
FORBIDDEN = (re.compile(r"ttc-r1", re.I), re.compile(r"relative_temporal", re.I),
             re.compile(r"unit_normalization_clean", re.I), re.compile(r"(?:^|[-_])(?:G|N|T\d+)(?:\b|$)"))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def neutralize(text: str, transformation_type: str, role: str) -> tuple[str, list[str]]:
    out = text; actions = []
    replaced = ROLE_ID.sub("", out)
    if replaced != out:
        out = replaced; actions.append("remove_role_bearing_internal_identifier")
    replaced = ARCHIVE_ID.sub(r"\1:", out)
    if replaced != out:
        out = replaced; actions.append("remove_unrelated_archive_identifier")
    if role == "topical_distractor":
        if transformation_type == "relative_temporal" and out.startswith("Topical entry "):
            out = "Register entry " + out[len("Topical entry "):]; actions.append("neutralize_role_bearing_entry_label")
        elif transformation_type == "unit_normalization_clean" and ", topical entry " in out:
            out = out.replace(", topical entry ", ", measurement entry ", 1); actions.append("neutralize_role_bearing_entry_label")
    return re.sub(r"\s+", " ", out).strip(), actions


def transform(source: Path, output: Path, lock_path: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    pairs = read_jsonl(source / "pairs.jsonl"); original_docs = read_jsonl(source / "documents.jsonl")
    pair_type = {p["pair_id"]: p["transformation_type"] for p in pairs}; docs = []; actions = Counter()
    for row in original_docs:
        item = json.loads(json.dumps(row)); typ = row["fact"]["transformation_type"] if row.get("fact") else pair_type[row["pair_id"]]
        item["text"], used = neutralize(row["text"], typ, row["role"]); item["text_sha256"] = hashlib.sha256(item["text"].encode("utf-8")).hexdigest(); actions.update(used); docs.append(item)
    by_doc = {d["doc_id"]: d for d in docs}; corrected_pairs = []
    for row in pairs:
        item = json.loads(json.dumps(row)); item["gold_text"] = by_doc[item["gold_doc_id"]]["text"]; item["negative_text"] = by_doc[item["critical_negative_doc_id"]]["text"]; corrected_pairs.append(item)
    write_jsonl(output / "documents.jsonl", docs); write_jsonl(output / "pairs.jsonl", corrected_pairs)
    for name in ("families.jsonl", "corpora.jsonl", "sources.jsonl", "audit_decisions.jsonl", "selection_weights.jsonl"):
        shutil.copy2(source / name, output / name)
    shutil.copy2(source / "freeze_manifest.json", output / "source_freeze_manifest.json"); shutil.copy2(source / "verification.json", output / "source_freeze_verification.json")
    lock = json.loads(lock_path.read_text(encoding="utf-8")); expected = lock["hashes"]
    actual = {"pairs_jsonl_sha256": sha(output / "pairs.jsonl"), "documents_jsonl_sha256": sha(output / "documents.jsonl"), "corpora_jsonl_sha256": sha(output / "corpora.jsonl")}
    source_by_id = {d["doc_id"]: d for d in original_docs}; marker_hits = [d["doc_id"] for d in docs for pattern in FORBIDDEN if pattern.search(d["text"])]
    checks = {
        "queries_unchanged": all(a["queries"] == b["queries"] for a, b in zip(pairs, corrected_pairs)),
        "semantic_values_unchanged": all(source_by_id[d["doc_id"]].get("fact") == d.get("fact") for d in docs),
        "role_type_internal_markers_removed": not marker_hits,
        "output_file_hashes_match_lock": all(actual[k] == expected[k] for k in actual),
        "action_counts_match_audit": dict(actions) == {"remove_role_bearing_internal_identifier": 1029, "neutralize_role_bearing_entry_label": 735, "remove_unrelated_archive_identifier": 3675},
    }
    report = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "authorized_transform_counts": dict(actions), "hashes": actual, "marker_hits": marker_hits}
    (output / "neutralization_replay_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report["status"] != "PASS":
        raise RuntimeError(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--source", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--lock", type=Path, required=True); args = parser.parse_args()
    print(json.dumps(transform(args.source, args.output, args.lock), indent=2))


if __name__ == "__main__":
    main()
