#!/usr/bin/env python3
"""Split the dataset into train / dev / test BY SPEAKER (never by clip).

Usage (from the data-collector folder):
    python3 scripts/make_splits.py --dataset dataset --config docs/SPLITS.md
    python3 scripts/make_splits.py --dataset dataset --config docs/SPLITS.md --exclude reports/flagged.csv

The config (docs/SPLITS.md, or a .yaml file) lists speaker_ids under "test" and "dev";
every other speaker goes to "train". The script refuses to run if a speaker is listed in both.
--exclude drops clips that qc_dataset.py marked "remove" in flagged.csv.
Writes splits.json and prints clips, speakers and minutes per split and category.
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SPLITS = ("train", "dev", "test")
MIN_TEST_CLIPS_PER_CATEGORY = 15
ID = re.compile(r"[A-Za-z0-9_\-]+")


def parse_config(path):
    """Return {"test": [...], "dev": [...]} from a SPLITS.md or a simple YAML file.

    Markdown: a heading whose first word is "test" or "dev", then bullet lines ("- spk_abc  (any note)").
    YAML:     test: [spk_a, spk_b]   or   test:\\n  - spk_a
    """
    text = Path(path).read_text(encoding="utf-8")
    out = {"test": [], "dev": []}
    current = None
    yaml_mode = Path(path).suffix.lower() in (".yaml", ".yml")
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip() if yaml_mode else raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if yaml_mode:
            m = re.match(r"^(\w+)\s*:\s*(.*)$", line)
            if m and not line.startswith((" ", "\t", "-")):
                key = m.group(1).lower()
                current = key if key in out else None
                rest = m.group(2).strip()
                if current and rest.startswith("["):
                    out[current] += [t.strip(" '\"") for t in rest.strip("[]").split(",") if t.strip(" '\"")]
                continue
        else:
            if stripped.startswith("#"):
                first = (re.findall(r"[a-z]+", stripped.lower()) or [""])[0]
                current = first if first in out else None
                continue
        if current and stripped.startswith(("-", "*")):
            item = stripped[1:].strip().strip("`'\"")
            m = ID.match(item.strip("`"))
            if m:
                out[current].append(m.group(0))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="dataset", help="folder with manifest.csv (default: dataset)")
    ap.add_argument("--config", default="docs/SPLITS.md", help="speaker list (default: docs/SPLITS.md)")
    ap.add_argument("--out", default="splits.json", help="output file (default: splits.json)")
    ap.add_argument("--exclude", help="flagged.csv from qc_dataset.py: drop clips marked 'remove'")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    manifest = dataset / "manifest.csv" if dataset.is_dir() else dataset
    if not manifest.exists():
        sys.exit(f"Cannot find {manifest}.")
    if not Path(args.config).exists():
        sys.exit(f"Cannot find {args.config}. Copy docs/SPLITS.md and list your test/dev speakers in it.")
    with open(manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    cfg = parse_config(args.config)
    both = sorted(set(cfg["test"]) & set(cfg["dev"]))
    if both:
        sys.exit("REFUSING TO RUN: these speakers are listed in BOTH test and dev: " + ", ".join(both)
                 + f"\nEach speaker may be in only one set. Fix {args.config} and run again.")
    assign = {s: "test" for s in cfg["test"]}
    assign.update({s: "dev" for s in cfg["dev"]})

    known = {r["speaker_id"] for r in rows}
    for s in sorted(set(assign) - known):
        print(f"WARNING: speaker {s} is listed as {assign[s]} in {args.config} but has no clips in the manifest.")
    for name in ("test", "dev"):
        if not any(assign.get(s) == name for s in known):
            print(f"WARNING: the {name} split has no speakers.")

    excluded = set()
    if args.exclude:
        with open(args.exclude, newline="", encoding="utf-8-sig") as f:
            excluded = {r["path"] for r in csv.DictReader(f) if r.get("suggested_action") == "remove"}

    clips = {s: [] for s in SPLITS}
    spk = {s: set() for s in SPLITS}
    sec = defaultdict(float)
    cat_n, cat_sec = defaultdict(int), defaultdict(float)
    dropped = 0
    for r in rows:
        if r["path"] in excluded:
            dropped += 1
            continue
        split = assign.get(r["speaker_id"], "train")
        d = float(r.get("duration") or 0)
        c = r.get("category") or "(none)"
        clips[split].append(r["path"])
        spk[split].add(r["speaker_id"])
        sec[split] += d
        cat_n[(split, c)] += 1
        cat_sec[(split, c)] += d

    for a in SPLITS:
        for b in SPLITS:
            if a < b and spk[a] & spk[b]:
                sys.exit(f"INTERNAL ERROR: speakers in both {a} and {b}: {sorted(spk[a] & spk[b])}")

    cats = sorted({c for _, c in cat_n} | {r.get("category") or "(none)" for r in rows})
    summary = {s: {"clips": len(clips[s]), "speakers": len(spk[s]), "minutes": round(sec[s] / 60, 2),
                   "by_category": {c: {"clips": cat_n[(s, c)], "minutes": round(cat_sec[(s, c)] / 60, 2)}
                                   for c in cats}} for s in SPLITS}
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest": str(manifest), "config": str(args.config),
        "excluded_clips": dropped,
        "speakers": {s: sorted(spk[s]) for s in SPLITS},
        "summary": summary,
        "clips": clips,
    }
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n{'split':<6} {'clips':>6} {'speakers':>9} {'minutes':>8}")
    for s in SPLITS:
        print(f"{s:<6} {len(clips[s]):>6} {len(spk[s]):>9} {sec[s] / 60:>8.1f}")
    if dropped:
        print(f"({dropped} clips marked 'remove' in {args.exclude} were left out)")
    w = max(len(c) for c in cats)
    print(f"\n{'category':<{w}}  " + "  ".join(f"{s + ' clips/min':>16}" for s in SPLITS))
    for c in cats:
        print(f"{c:<{w}}  " + "  ".join(f"{cat_n[(s, c)]:>8} / {cat_sec[(s, c)] / 60:>5.1f}" for s in SPLITS))
    low = [c for c in cats if cat_n[("test", c)] < MIN_TEST_CLIPS_PER_CATEGORY]
    if low:
        print(f"\nWARNING: these categories have fewer than {MIN_TEST_CLIPS_PER_CATEGORY} clips in the test split:")
        for c in low:
            print(f"  - {c}: {cat_n[('test', c)]} clips")
        print("Add more test speakers (or record more) so every category is measured fairly.")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
