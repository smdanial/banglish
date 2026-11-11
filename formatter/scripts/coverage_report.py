#!/usr/bin/env python3
"""Prints the pass rate per note type for tests/cases.yaml.

Usage (from the formatter/ folder):  python3 scripts/coverage_report.py [--show-failures] [cases.yaml]
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from banglish_formatter import format_note


def passes(case, out):
    ok = (out["type"] == case["type"] and out["result"] == case["expected"]
          and out["matched"] is (case["type"] != "other"))
    return ok and case.get("notes_contains", "") in out["notes"]


def main(argv):
    show = "--show-failures" in argv
    paths = [a for a in argv if not a.startswith("--")]
    path = Path(paths[0]) if paths else ROOT / "tests" / "cases.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))
    stats, failures = {}, []
    for case in cases:
        out = format_note(case["input"])
        total, passed = stats.get(case["type"], (0, 0))
        ok = passes(case, out)
        stats[case["type"]] = (total + 1, passed + ok)
        if not ok:
            failures.append((case, out))

    print(f"{'type':<10} {'cases':>5} {'passed':>6} {'rate':>7}")
    print("-" * 31)
    for t in ("schedule", "expenses", "other"):
        total, passed = stats.pop(t, (0, 0))
        print(f"{t:<10} {total:>5} {passed:>6} {(passed / total if total else 0):>7.1%}")
    for t, (total, passed) in stats.items():
        print(f"{t:<10} {total:>5} {passed:>6} {passed / total:>7.1%}")
    all_total, all_passed = len(cases), len(cases) - len(failures)
    print("-" * 31)
    print(f"{'ALL':<10} {all_total:>5} {all_passed:>6} {all_passed / all_total:>7.1%}")

    if failures:
        if show:
            for case, out in failures:
                print(f"\n[{case['id']}] {case['input']!r}\n  expected ({case['type']}): {case['expected']!r}"
                      f"\n  got      ({out['type']}): {out['result']!r}  notes: {out['notes']!r}")
        else:
            print(f"\n{len(failures)} failing; run with --show-failures for details")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
