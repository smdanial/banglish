"""Compare speech models on Banglish audio.

    python -m eval.run --config eval/config.yaml
    python -m eval.run --config eval/config.yaml --data ~/dataset --splits ~/splits.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "eval" / "sample"


def load_dotenv():
    """Read KEY=VALUE lines from .env files (never printed; existing env vars win)."""
    for p in (ROOT / ".env", ROOT / "eval" / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().removeprefix("export ").strip()
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def cfg_path(p, base=ROOT):
    if p in (None, ""):
        return None
    p = Path(os.path.expanduser(str(p)))
    return p if p.is_absolute() else (base / p).resolve()


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "model"


def fingerprint(entry: dict, api: dict) -> str:
    keys = {k: v for k, v in entry.items() if k not in ("name", "enabled", "romanize", "note")}
    if entry.get("type") == "openai_compat":
        from .models.openai_compat import resolve
        keys["_model"] = resolve({**api, **entry})[2]
    return hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()[:12]


def read_records(out_dir: Path, fp: str):
    recs = {}
    t = out_dir / "transcripts.jsonl"
    if t.exists():
        for line in t.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("fingerprint") == fp:
                if "error" in r and r["path"] in recs and "error" not in recs[r["path"]]:
                    continue
                recs[r["path"]] = r
    return recs


def peak_ram(out_dir: Path, fp: str):
    best = None
    p = out_dir / "runs.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("fingerprint") == fp and r.get("transcribed"):
                best = max(best or 0, r.get("peak_ram_mb") or 0)
    return best


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="eval/config.yaml")
    ap.add_argument("--data", help="folder with manifest.csv + WAVs (overrides config)")
    ap.add_argument("--splits", help="splits.json from make_splits.py (overrides config)")
    ap.add_argument("--split", help="which split to evaluate (default from config, usually 'test')")
    ap.add_argument("--all", action="store_true", help="ignore splits.json and evaluate every clip")
    ap.add_argument("--models", help="comma-separated model names to run (default: all enabled in config)")
    ap.add_argument("--output", help="results folder (overrides config)")
    ap.add_argument("--limit", type=int, help="only the first N clips (quick try-out)")
    ap.add_argument("--quick", action="store_true", help="quick check: only the first 30 clips (same as --limit 30)")
    ap.add_argument("--no-isolate", action="store_true", help="run models in this process (RAM numbers less exact)")
    args = ap.parse_args(argv)
    if args.quick and not args.limit:
        args.limit = 30

    load_dotenv()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    dcfg = cfg.get("data") or {}
    cwd = Path.cwd()
    data_dir = cfg_path(args.data, cwd) if args.data else cfg_path(dcfg.get("dir", "eval/sample"))
    splits_file = None if args.all else (cfg_path(args.splits, cwd) if args.splits else cfg_path(dcfg.get("splits_file")))
    split_name = args.split or dcfg.get("split") or "test"
    out_root = cfg_path(args.output, cwd) if args.output else cfg_path(cfg.get("output_dir", "eval/results"))
    api = cfg.get("api") or {}
    worst_n = int(cfg.get("worst_n", 20))

    from .dataset import load_manifest, select_split
    from .report import group, machine_info, score_utt, write_summary, write_utts
    from .textnorm import Normalizer, has_non_latin, main_script
    from .worker import run_job

    if data_dir == SAMPLE_DIR.resolve():
        from .sample.make_sample import ensure_sample
        ensure_sample()

    clips, problems, n_rows = load_manifest(data_dir, dcfg.get("manifest", "manifest.csv"))
    if splits_file:
        if not splits_file.exists():
            raise SystemExit(f"splits file not found: {splits_file}")
        clips = select_split(clips, splits_file, split_name)
        split_note = f"Split: **{split_name}** from `{splits_file.name}`"
    else:
        split_note = ("**No splits.json given: evaluated ALL clips in the manifest** (may include clips "
                      "used for training; give --splits for a fair test-set number)")
    if args.limit:
        clips = clips[: args.limit]
        split_note += f"; limited to first {args.limit} clips ({'--quick' if args.quick else '--limit'})"
    if not clips:
        raise SystemExit("no clips to evaluate")
    print(f"{len(clips)} clips, {len({c.speaker_id for c in clips})} speakers. {split_note.replace('*', '')}")

    norm = Normalizer.from_file(cfg_path(cfg.get("normalization", "eval/normalization.yaml")))
    entries = [m for m in (cfg.get("models") or [])]
    wanted = set(args.models.split(",")) if args.models else None
    skipped, to_run = [], []
    for e in entries:
        name = e.get("name") or e.get("type")
        if wanted is not None:
            if name not in wanted:
                continue
        elif not e.get("enabled", True):
            skipped.append((name, e.get("note") or "disabled in config (enabled: false)"))
            continue
        from .models import check
        why = check(e, api)
        if why:
            skipped.append((name, why))
            print(f"SKIP {name}: {why}")
        else:
            to_run.append(e)

    romanizer = None
    if any(e.get("romanize") for e in to_run):
        from .romanizer import Romanizer
        romanizer = Romanizer(cfg.get("romanizer") or {}, api, cfg_path((cfg.get("romanizer") or {}).get("cache_dir", "eval/cache")))
        if not romanizer.available:
            for e in [e for e in to_run if e.get("romanize")]:
                skipped.append((e["name"], romanizer.note))
                to_run.remove(e)

    out_root.mkdir(parents=True, exist_ok=True)
    results = []
    for e in to_run:
        name = e["name"]
        out_dir = out_root / slug(name)
        fp = fingerprint(e, api)
        recs = read_records(out_dir, fp)
        todo = [[c.path, str(c.abs_path), c.duration] for c in clips
                if c.path not in recs or "error" in recs[c.path]]
        label = name + (f" + romanizer ({romanizer.label})" if e.get("romanize") else "")
        print(f"== {label}: {len(clips) - len(todo)} already done, {len(todo)} to transcribe")
        if todo:
            job = {"entry": e, "api": api, "todo": todo, "out_dir": str(out_dir), "fingerprint": fp, "label": name}
            code = run_job(job, isolate=not args.no_isolate and cfg.get("isolate_models", True))
            if code != 0:
                print(f"WARNING: {name} stopped with exit code {code}; results so far are kept", file=sys.stderr)
            recs = read_records(out_dir, fp)

        utts, failed, sec, aud, nonlatin_left = [], 0, 0.0, 0.0, 0
        scripts = Counter()
        for c in clips:
            r = recs.get(c.path)
            if r is None or "error" in r:
                failed += 1
                continue
            raw = r.get("raw", "")
            scripts[main_script(raw)] += 1
            hyp = romanizer(raw) if e.get("romanize") else raw
            if has_non_latin(hyp):
                nonlatin_left += 1
            rn, hn = norm.normalize(c.reference), norm.normalize(hyp)
            if not rn:
                continue
            w_err, w_n, c_err, c_n = score_utt(rn, hn)
            rk, hk = norm.key_fields(c.reference), norm.key_fields(hyp)
            utts.append({
                "path": c.path, "speaker_id": c.speaker_id, "category": c.category,
                "reference": c.reference, "hypothesis": hyp, "raw_model_output": raw,
                "reference_normalized": rn, "hypothesis_normalized": hn,
                "reference_key_fields": " ".join(sorted(rk.elements())),
                "hypothesis_key_fields": " ".join(sorted(hk.elements())),
                "w_err": w_err, "w_n": w_n, "c_err": c_err, "c_n": c_n,
                "wer": w_err / w_n if w_n else 0.0, "cer": c_err / c_n if c_n else 0.0,
                "kf_has": bool(rk), "kf_ok": rk == hk,
            })
            if r.get("seconds") is not None and c.duration:
                sec += r["seconds"]
                aud += c.duration
        if not utts:
            skipped.append((name, f"no successful transcriptions ({failed} failed; see {out_dir}/transcripts.jsonl)"))
            continue
        write_utts(out_dir / "worst.csv", utts, worst_n)
        write_utts(out_dir / "hypotheses.csv", utts)
        overall, by_cat = group(utts)
        notes = []
        if failed:
            notes.append(f"{name}: {failed} clips failed to transcribe (re-run to retry); excluded from its scores.")
        if set(scripts) - {"Latin", "Empty"}:
            notes.append(f"{name}: script of raw output: " + ", ".join(f"{s} {n}" for s, n in scripts.most_common()))
        if nonlatin_left:
            notes.append(f"{name}: {nonlatin_left} outputs still contain non-Latin letters after "
                         f"{'romanization' if e.get('romanize') else 'transcription (romanize: false)'}.")
        if e.get("romanize") and romanizer and romanizer.fallbacks:
            notes.append(f"{name}: LLM romanizer failed on {romanizer.fallbacks} clips; rules romanizer used for those.")
        results.append({"label": label, "overall": overall, "by_cat": by_cat, "failed": failed,
                        "speed": sec / aud if aud else None, "ram_mb": peak_ram(out_dir, fp), "notes": notes})

    ctx = {
        "time": time.strftime("%Y-%m-%d %H:%M"), "machine": machine_info(),
        "data_dir": str(data_dir), "manifest_rows": n_rows, "split_note": split_note,
        "n_clips": len(clips), "n_speakers": len({c.speaker_id for c in clips}),
        "audio_minutes": sum(c.duration for c in clips) / 60, "worst_n": worst_n,
        "problems": ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in problems.items() if v),
        "romanizer_note": romanizer.note if romanizer else "",
    }
    summary = out_root / "summary.md"
    write_summary(summary, ctx, results, skipped)
    print(f"\nWrote {summary}")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
