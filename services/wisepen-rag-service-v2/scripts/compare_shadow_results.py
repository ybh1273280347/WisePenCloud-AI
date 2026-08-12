"""比较 v1/v2 归一化 shadow 观测，并拒绝未批准的行为差异。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{path}:{line_number} has no case_id")
        if case_id in records:
            raise ValueError(f"{path}:{line_number} duplicates {case_id}")
        records[case_id] = record
    return records


def _differences(left: Any, right: Any, path: str = "$") -> Iterator[dict[str, Any]]:
    if type(left) is not type(right):
        yield {"path": path, "v1": left, "v2": right}
        return
    if isinstance(left, dict):
        for key in sorted(left.keys() | right.keys()):
            child_path = f"{path}.{key}"
            if key not in left:
                yield {"path": child_path, "v1": None, "v2": right[key]}
            elif key not in right:
                yield {"path": child_path, "v1": left[key], "v2": None}
            else:
                yield from _differences(left[key], right[key], child_path)
        return
    if isinstance(left, list):
        if len(left) != len(right):
            yield {"path": f"{path}.length", "v1": len(left), "v2": len(right)}
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
            yield from _differences(left_item, right_item, f"{path}[{index}]")
        return
    if left != right:
        yield {"path": path, "v1": left, "v2": right}


def compare(
    v1_path: Path,
    v2_path: Path,
    approvals_path: Path | None = None,
) -> dict[str, Any]:
    v1_records = _load_jsonl(v1_path)
    v2_records = _load_jsonl(v2_path)
    approvals = _load_approvals(approvals_path)
    differences: list[dict[str, Any]] = []

    for case_id in sorted(v1_records.keys() | v2_records.keys()):
        if case_id not in v1_records or case_id not in v2_records:
            differences.append(
                {
                    "case_id": case_id,
                    "path": "$record",
                    "v1": "present" if case_id in v1_records else "missing",
                    "v2": "present" if case_id in v2_records else "missing",
                }
            )
            continue
        v1_record = v1_records[case_id]
        v2_record = v2_records[case_id]
        # 延迟单独汇总；权限、revision、证据和正文仍属于严格行为对照。
        comparable_v1 = {key: value for key, value in v1_record.items() if key != "latency_ms"}
        comparable_v2 = {key: value for key, value in v2_record.items() if key != "latency_ms"}
        for difference in _differences(comparable_v1, comparable_v2):
            difference["case_id"] = case_id
            differences.append(difference)

    for difference in differences:
        approval = approvals.get((difference["case_id"], difference["path"]))
        difference["approval"] = approval

    unapproved = [item for item in differences if item["approval"] is None]
    return {
        "status": "ready" if not unapproved else "approval_required",
        "case_count": len(v1_records.keys() | v2_records.keys()),
        "difference_count": len(differences),
        "unapproved_difference_count": len(unapproved),
        "latency_ms": {
            "v1": _latencies(v1_records),
            "v2": _latencies(v2_records),
        },
        "differences": differences,
    }


def _load_approvals(path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    if path is None:
        return {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    approvals: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        if not all(entry.get(key) for key in ("case_id", "path", "reason", "approved_by")):
            raise ValueError("each approval requires case_id, path, reason and approved_by")
        approvals[(entry["case_id"], entry["path"])] = entry
    return approvals


def _latencies(records: dict[str, dict[str, Any]]) -> dict[str, float | None]:
    values = [record["latency_ms"] for record in records.values() if "latency_ms" in record]
    if not values:
        return {"average": None, "maximum": None}
    return {"average": sum(values) / len(values), "maximum": max(values)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("v1", type=Path)
    parser.add_argument("v2", type=Path)
    parser.add_argument("--approvals", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = compare(args.v1, args.v2, args.approvals)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
