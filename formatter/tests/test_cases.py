from pathlib import Path

import pytest
import yaml

from banglish_formatter import format_note

CASES = yaml.safe_load((Path(__file__).parent / "cases.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case):
    out = format_note(case["input"])
    assert out["type"] == case["type"]
    assert out["result"] == case["expected"]
    assert out["matched"] is (case["type"] != "other")
    if "notes_contains" in case:
        assert case["notes_contains"] in out["notes"]


def test_case_file_has_enough_cases():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    assert len(CASES) >= 60
    assert sum(c["type"] == "other" for c in CASES) >= 10
    for t in ("schedule", "expenses"):
        assert sum(c["type"] == t for c in CASES) >= 20
