import importlib.util
from pathlib import Path

SERVICE_ROOT = Path(__file__).parents[2]
SCRIPT_PATH = SERVICE_ROOT / "scripts" / "compare_shadow_results.py"
FIXTURE_ROOT = SERVICE_ROOT / "tests" / "fixtures" / "shadow"


def _load_script():
    spec = importlib.util.spec_from_file_location("compare_shadow_results", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_contract_golden_fixtures_have_no_semantic_drift() -> None:
    report = _load_script().compare(
        FIXTURE_ROOT / "v1_contract.jsonl",
        FIXTURE_ROOT / "v2_contract.jsonl",
    )

    assert report["status"] == "ready"
    assert report["case_count"] == 6
    assert report["difference_count"] == 0


def test_shadow_report_rejects_unapproved_difference() -> None:
    changed = FIXTURE_ROOT / "v2_unapproved_contract.jsonl"

    report = _load_script().compare(
        FIXTURE_ROOT / "v1_contract.jsonl",
        changed,
    )

    assert report["status"] == "approval_required"
    assert report["unapproved_difference_count"] == 1
    assert report["differences"][0]["path"] == "$.facts.decision"
