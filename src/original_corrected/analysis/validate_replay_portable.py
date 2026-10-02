from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt", ".yaml", ".yml"}
DETERMINISTIC = ("primary_endpoints.csv", "confirmatory_report.md", "analysis/primary_endpoints.csv",
                 "analysis/family_contributions.csv", "analysis/leave_one_family_out.csv",
                 "analysis/secondary_model_metrics.csv", "analysis/bm25_diagnostics.csv",
                 "analysis/pipeline_diagnostics.csv", "analysis/status_mapping.json")


def normalized_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


def digest(path: Path) -> str:
    return hashlib.sha256(normalized_bytes(path)).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--reference", type=Path, required=True); p.add_argument("--candidate", type=Path, required=True); p.add_argument("--output", type=Path, required=True); args = p.parse_args()
    rows = []
    for rel in DETERMINISTIC:
        left, right = args.reference / rel, args.candidate / rel
        rows.append({"path": rel, "reference_sha256_normalized": digest(left), "candidate_sha256_normalized": digest(right), "match": digest(left) == digest(right)})
    ref = np.load(args.reference / "analysis/bootstrap_outputs.npz"); cand = np.load(args.candidate / "analysis/bootstrap_outputs.npz")
    arrays = {key: {"equal": bool(np.array_equal(ref[key], cand[key], equal_nan=True)), "max_absolute_difference": float(np.nanmax(np.abs(ref[key] - cand[key]))) if np.isfinite(ref[key] - cand[key]).any() else 0.0} for key in ref.files}
    status = "PASS" if all(row["match"] for row in rows) and all(v["equal"] for v in arrays.values()) else "FAIL"
    result = {"status": status, "newline_policy": "CRLF and CR are canonicalized to LF before text-file hashing", "files": rows, "bootstrap_arrays": arrays}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "files": len(rows), "bootstrap_arrays": len(arrays)}))
    if status != "PASS": raise SystemExit(1)


if __name__ == "__main__":
    main()
