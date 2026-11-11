#!/usr/bin/env python3
"""Quality check for an exported dataset (manifest.csv + 16 kHz mono WAVs).

Usage (from the data-collector folder):
    python3 scripts/qc_dataset.py --dataset dataset            # folder made by export_dataset.py
    python3 scripts/qc_dataset.py --dataset tests/sample_data --out tests/sample_data/reports

Writes <out>/qc_report.md (plain-language report) and <out>/flagged.csv (one row per clip with a problem).
Needs Python 3.8+ and numpy (pip install numpy). Nothing is uploaded or changed in the dataset.
"""
import argparse
import csv
import hashlib
import re
import sys
import wave
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy is needed: run  pip install numpy  and try again.")

# ---- thresholds (change here if needed) ----
MIN_SEC, MAX_SEC = 1.0, 20.0
FRAME_SEC = 0.02                 # analysis frame
MOSTLY_SILENT = 0.70             # more than 70% of frames are silence
MIN_SPEECH_SEC = 0.25            # less speech than this = "no speech"
LEADING_SILENCE_SEC = 1.5
QUIET_DBFS = -35.0               # average loudness of the speech parts
CLIP_LEVEL = 0.999               # sample at (almost) maximum amplitude
CLIP_MIN_SAMPLES = 20
CUTOFF_TAIL_SEC = 0.06           # speech still going in the last 60 ms
BIG_CHANGE = 0.5                 # >50% of the prompt's words changed
EXPECTED_RATE, EXPECTED_CHANNELS = 16000, 1

BENGALI = re.compile(r"[\u0980-\u09FF]")
ALLOWED = re.compile(r"[A-Za-z0-9\s.,!?'\"\u2018\u2019\u201C\u201D\-:;()/&%+@#]")

# code -> (suggested action, plain-language sentence for the report, short description for flagged.csv)
ISSUES = {
    "missing_file": ("remove", "{n} clip(s) are listed in manifest.csv but the audio file is missing. Re-run the export, or remove them.", "audio file not found"),
    "unreadable": ("remove", "{n} clip(s) could not be opened as WAV files. Re-run the export, or remove them.", "not a readable WAV file"),
    "no_speech": ("remove", "{n} clip(s) contain no speech we could detect (silence, or the mic did not work). Remove them.", "no speech detected"),
    "empty_text": ("remove", "{n} clip(s) have an empty \"What you actually said\" box. Type what was said, or remove them.", "actual_text is empty"),
    "duplicate_audio": ("remove", "{n} audio file(s) are exact copies of another file. Remove the copies (one file of each group is kept and not flagged).", "identical to another audio file"),
    "duplicate_take": ("remove", "{n} extra recording(s) of a sentence the same speaker had already recorded. Keep one take per speaker and sentence; the flagged ones are the extras (a good take is kept in preference to a broken one).", "same speaker has another take of this prompt"),
    "bengali_script": ("fix text", "{n} clip(s) have Bengali letters in the text. The text must be Banglish in Latin letters: re-type it.", "Bengali script in actual_text"),
    "odd_characters": ("fix text", "{n} clip(s) have unusual characters in the text (emoji, symbols). Remove those characters.", "unusual characters in actual_text"),
    "too_short": ("listen", "{n} clip(s) are shorter than 1 second; the volunteer probably tapped Stop too early. Usually remove them.", "shorter than 1 s"),
    "too_long": ("listen", "{n} clip(s) are longer than 20 seconds; often Stop was tapped late. Listen and trim or remove.", "longer than 20 s"),
    "mostly_silence": ("listen", "{n} clip(s) are mostly silence (over 70% quiet). Listen: the mic may have been far away.", "mostly silence"),
    "clipping": ("listen", "{n} clip(s) are distorted because the sound was too loud (clipping). Listen and remove the ones that sound harsh.", "clipping (too loud)"),
    "low_volume": ("listen", "{n} clip(s) are very quiet. Listen and remove the ones that are hard to understand.", "very low volume"),
    "long_leading_silence": ("listen", "{n} clip(s) start with more than 1.5 seconds of silence. Usually fine; trim if you like.", "over 1.5 s silence at the start"),
    "cut_off": ("listen", "{n} clip(s) may be cut off at the end (speech still going when recording stopped). Listen to the last word; remove if it is cut.", "may be cut off at the end"),
    "big_text_change": ("listen", "{n} clip(s) where the typed text is very different from the prompt. Listen and make sure the typed text matches the audio.", "text very different from the prompt"),
    "wrong_format": ("listen", "{n} clip(s) are not 16 kHz mono 16-bit WAV. Re-run export_dataset.py to convert them.", "not 16 kHz mono 16-bit"),
}
ACTION_ORDER = {"remove": 0, "fix text": 1, "listen": 2}
FLAG_FIELDS = ["path", "speaker_id", "category", "duration", "suggested_action", "issues", "details",
               "prompt_text", "actual_text"]


def norm_words(text):
    return re.sub(r"[^\w\s]", " ", (text or "").lower()).split()


def word_change_ratio(prompt, actual):
    """Word-level edit distance divided by the prompt's word count."""
    a, b = norm_words(prompt), norm_words(actual)
    prev = list(range(len(b) + 1))
    for i, wa in enumerate(a, 1):
        cur = [i]
        for j, wb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (wa != wb)))
        prev = cur
    return prev[-1] / max(len(a), 1)


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-10))


def pcm_to_float(raw, width):
    """Decode little-endian PCM (8/16/24/32-bit) to floats in [-1, 1)."""
    if width == 1:
        return (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if width == 3:
        b = np.frombuffer(raw[: len(raw) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        return v.astype(np.float32) / float(1 << 23)
    return np.frombuffer(raw, dtype={2: "<i2", 4: "<i4"}[width]).astype(np.float32) / float(1 << (8 * width - 1))


def csv_cell(value):
    """Stop spreadsheets from running volunteer text as a formula."""
    value = str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def keeper(group):
    """The clip to keep from a group of duplicates: the first one with nothing that means 'remove'."""
    usable = [c for c in group if all(ISSUES[i][0] != "remove" for i in c["issues"])]
    return (usable or group)[0]


def analyse_audio(path):
    """Return (metrics dict, list of issue codes, details list, sha256 of the audio samples)."""
    issues, details = [], []
    with wave.open(str(path), "rb") as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    digest = hashlib.sha256(raw).hexdigest()
    if (rate, ch, width) != (EXPECTED_RATE, EXPECTED_CHANNELS, 2):
        issues.append("wrong_format")
        details.append(f"{rate} Hz, {ch} channel(s), {8 * width}-bit")
    if width not in (1, 2, 3, 4):
        raise wave.Error(f"{8 * width}-bit audio is not supported")
    x = pcm_to_float(raw, width)
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    dur = len(x) / float(rate)
    m = {"duration": dur}
    if dur < MIN_SEC:
        issues.append("too_short")
    if dur > MAX_SEC:
        issues.append("too_long")
    if len(x) == 0:
        issues.append("no_speech")
        return m, issues, details, digest

    peak = float(np.max(np.abs(x)))
    clipped = int(np.sum(np.abs(x) >= CLIP_LEVEL))
    if clipped >= CLIP_MIN_SAMPLES:
        issues.append("clipping")
        details.append(f"{clipped} samples at max level")

    hop = max(1, int(rate * FRAME_SEC))
    nf = max(1, len(x) // hop)
    xs = np.pad(x, (0, max(0, hop - len(x))))
    frames = xs[: nf * hop].reshape(nf, hop)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    fdb = db(rms)
    ref = float(np.percentile(fdb, 95))
    thr = min(max(ref - 30.0, -60.0), -40.0)   # adapts to quiet clips, never above -40 dBFS
    speech = fdb > thr
    m["silence_ratio"] = float(1 - speech.mean())
    speech_sec = float(speech.sum() * FRAME_SEC)
    if speech_sec < MIN_SPEECH_SEC:
        issues.append("no_speech")
        return m, issues, details, digest

    idx = np.flatnonzero(speech)
    lead = idx[0] * FRAME_SEC
    speech_db = float(10 * np.log10(np.mean(rms[speech] ** 2) + 1e-20))
    m.update(leading_silence=lead, speech_dbfs=speech_db, peak_dbfs=float(db(peak)))
    if m["silence_ratio"] > MOSTLY_SILENT:
        issues.append("mostly_silence")
        details.append(f"{m['silence_ratio']:.0%} silence")
    if speech_db < QUIET_DBFS:
        issues.append("low_volume")
        details.append(f"speech level {speech_db:.0f} dBFS")
    if lead > LEADING_SILENCE_SEC:
        issues.append("long_leading_silence")
        details.append(f"{lead:.1f} s silence at start")
    tail = max(1, int(round(CUTOFF_TAIL_SEC / FRAME_SEC)))
    if nf > tail and dur >= MIN_SEC and np.all(speech[-tail:]) and float(np.mean(fdb[-tail:])) > speech_db - 10:
        issues.append("cut_off")
    return m, issues, details, digest


def text_issues(prompt, actual):
    issues, details = [], []
    a = (actual or "").strip()
    if not a:
        return ["empty_text"], details
    if BENGALI.search(a):
        issues.append("bengali_script")
    odd = sorted({c for c in BENGALI.sub("", a) if not ALLOWED.match(c)})
    if odd:
        issues.append("odd_characters")
        details.append("characters: " + " ".join(f"U+{ord(c):04X}" for c in odd))
    ratio = word_change_ratio(prompt, a)
    if ratio > BIG_CHANGE:
        issues.append("big_text_change")
        details.append(f"{ratio:.0%} of words changed")
    return issues, details


def fmt_min(sec):
    return f"{sec / 60:.1f}"


def pct(a, b):
    return f"{100.0 * a / b:.0f}%" if b else "-"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def run(dataset, out_dir):
    dataset, out_dir = Path(dataset), Path(out_dir)
    manifest_path = dataset / "manifest.csv" if dataset.is_dir() else dataset
    if not manifest_path.exists():
        sys.exit(f"Cannot find {manifest_path}. Point --dataset at the folder made by export_dataset.py.")
    base = manifest_path.parent
    with open(manifest_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"{manifest_path} has no clips.")
    missing_cols = {"path", "speaker_id", "prompt_text", "actual_text"} - set(rows[0])
    if missing_cols:
        sys.exit(f"manifest.csv is missing columns: {', '.join(sorted(missing_cols))}")

    clips, by_hash, takes = [], defaultdict(list), defaultdict(list)
    for i, r in enumerate(rows, 1):
        c = {"row": r, "issues": [], "details": [], "duration": None}
        wav = base / r["path"]
        if not wav.exists():
            c["issues"].append("missing_file")
        else:
            try:
                m, iss, det, digest = analyse_audio(wav)
                c["duration"] = m["duration"]
                c["issues"] += iss
                c["details"] += det
                by_hash[digest].append(c)
            except (wave.Error, EOFError, ValueError) as e:
                c["issues"].append("unreadable")
                c["details"].append(str(e)[:80])
        if c["duration"] is None:
            try:
                c["duration"] = float(r.get("duration") or 0)
            except ValueError:
                c["duration"] = 0.0
        iss, det = text_issues(r["prompt_text"], r["actual_text"])
        c["issues"] += iss
        c["details"] += det
        c["unchanged"] = norm_words(r["prompt_text"]) == norm_words(r["actual_text"])
        takes[(r["speaker_id"], r.get("prompt_id") or r["prompt_text"].strip().lower())].append(c)
        clips.append(c)
        if i % 200 == 0:
            print(f"  checked {i}/{len(rows)} clips")

    # Pick keepers after the per-clip checks, so a good retake is kept instead of a broken first take.
    for group in by_hash.values():
        keep = keeper(group)
        for c in group:
            if c is not keep:
                c["issues"].append("duplicate_audio")
                c["details"].append("same audio as " + keep["row"]["path"])
    for group in takes.values():
        keep = keeper(group)
        for c in group:
            if c is not keep:
                c["issues"].append("duplicate_take")
                c["details"].append("kept take: " + keep["row"]["path"])

    flagged = [c for c in clips if c["issues"]]
    for c in flagged:
        c["issues"] = list(dict.fromkeys(c["issues"]))
        c["action"] = min((ISSUES[i][0] for i in c["issues"]), key=ACTION_ORDER.get)

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "flagged.csv", "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel shows Bengali correctly
        w = csv.DictWriter(f, fieldnames=FLAG_FIELDS)
        w.writeheader()
        for c in sorted(flagged, key=lambda c: (ACTION_ORDER[c["action"]], c["row"]["speaker_id"], c["row"]["path"])):
            r = c["row"]
            w.writerow({k: csv_cell(v) for k, v in {
                "path": r["path"], "speaker_id": r["speaker_id"], "category": r.get("category", ""),
                "duration": f"{c['duration']:.2f}", "suggested_action": c["action"],
                "issues": "; ".join(c["issues"]),
                "details": "; ".join([ISSUES[i][2] for i in c["issues"]] + c["details"]),
                "prompt_text": r["prompt_text"], "actual_text": r["actual_text"],
            }.items()})

    report = build_report(manifest_path, clips, flagged)
    (out_dir / "qc_report.md").write_text(report, encoding="utf-8")
    print(f"Checked {len(clips)} clips: {len(flagged)} flagged.")
    print(f"Report:  {out_dir / 'qc_report.md'}\nFlagged: {out_dir / 'flagged.csv'}")
    return clips, flagged


def build_report(manifest_path, clips, flagged):
    total_sec = sum(c["duration"] for c in clips)
    counts = Counter(i for c in flagged for i in c["issues"])
    actions = Counter(c["action"] for c in flagged)

    spk = defaultdict(list)
    cat = defaultdict(list)
    for c in clips:
        spk[c["row"]["speaker_id"]].append(c)
        cat[c["row"].get("category") or "(none)"].append(c)

    problems = []
    for code in sorted(counts, key=lambda k: (ACTION_ORDER[ISSUES[k][0]], -counts[k])):
        problems.append(f"**[{ISSUES[code][0]}]** " + ISSUES[code][1].format(n=counts[code]) + f" (`{code}`)")
    for s, cs in sorted(spk.items()):
        nflag = sum(1 for c in cs if c["issues"])
        if len(cs) >= 5 and nflag / len(cs) > 0.3:
            problems.append(f"Speaker `{s}` has {pct(nflag, len(cs))} of clips flagged. Listen to a few of them: "
                            "it may be a noisy room or a bad microphone.")
        if len(cs) >= 10 and all(c["unchanged"] for c in cs):
            problems.append(f"Speaker `{s}` never edited the text box ({len(cs)} clips, all identical to the prompt). "
                            "Fine if they read perfectly; spot-check two or three clips.")

    L = ["# Dataset quality report", "",
         f"Dataset: `{manifest_path}`  ",
         f"Checked: {datetime.now():%Y-%m-%d %H:%M}", "",
         "## Problems to fix", ""]
    if problems:
        L += [f"{i}. {p}" for i, p in enumerate(problems, 1)]
        L += ["", "Open **flagged.csv** (Excel or Google Sheets) to see each clip. Sort by `suggested_action`:",
              "**remove** = drop it from training, **fix text** = correct `actual_text`, **listen** = play it and decide."]
    else:
        L.append("No problems found.")
    L += ["", "## Overview", "",
          md_table(["", ""], [
              ["Clips", len(clips)],
              ["Speakers", len(spk)],
              ["Total audio", f"{total_sec / 3600:.2f} hours ({fmt_min(total_sec)} minutes)"],
              ["Average clip", f"{total_sec / len(clips):.1f} s"],
              ["Clips with any problem", f"{len(flagged)} ({pct(len(flagged), len(clips))})"],
              ["...suggested: remove", actions.get("remove", 0)],
              ["...suggested: fix text", actions.get("fix text", 0)],
              ["...suggested: listen", actions.get("listen", 0)],
              ["Text left exactly as the prompt", f"{sum(c['unchanged'] for c in clips)} ({pct(sum(c['unchanged'] for c in clips), len(clips))})"],
          ]), "",
          "## Per speaker", "",
          "\"Text unchanged\" = the volunteer did not edit the \"What you actually said\" box.", ""]
    srows = []
    for s, cs in sorted(spk.items(), key=lambda kv: -len(kv[1])):
        sec = sum(c["duration"] for c in cs)
        phones = Counter((c["row"].get("phone_model") or "").strip() for c in cs) - Counter({"": 10 ** 9})
        unchanged = sum(c["unchanged"] for c in cs)
        srows.append([f"`{s}`", len(cs), fmt_min(sec), f"{sec / len(cs):.1f}",
                      phones.most_common(1)[0][0] if phones else "-",
                      f"{unchanged} ({pct(unchanged, len(cs))})", pct(sum(1 for c in cs if c["issues"]), len(cs))])
    L.append(md_table(["Speaker", "Clips", "Minutes", "Avg sec", "Phone model", "Text unchanged", "% flagged"], srows))
    L += ["", "## Per category", ""]
    crows = []
    for k, cs in sorted(cat.items()):
        sec = sum(c["duration"] for c in cs)
        crows.append([k, len(cs), fmt_min(sec), f"{sec / len(cs):.1f}", len({c["row"]["speaker_id"] for c in cs}),
                      pct(sum(1 for c in cs if c["issues"]), len(cs))])
    L.append(md_table(["Category", "Clips", "Minutes", "Avg sec", "Speakers", "% flagged"], crows))
    L += ["", "## Problem counts", ""]
    L.append(md_table(["Check", "Clips", "Suggested action"],
                      [[f"`{k}`", counts.get(k, 0), ISSUES[k][0]] for k in ISSUES]))
    L += ["", "## What the checks mean", "",
          f"- **Duration**: flagged under {MIN_SEC:g} s or over {MAX_SEC:g} s.",
          f"- **Silence**: each {int(FRAME_SEC * 1000)} ms slice is \"speech\" or \"silence\" by loudness, relative to the loudest part of the clip. "
          f"Flagged when over {MOSTLY_SILENT:.0%} is silence, or less than {MIN_SPEECH_SEC} s is speech (`no_speech`).",
          f"- **Clipping**: {CLIP_MIN_SAMPLES}+ samples at the maximum level (sound was too loud for the mic).",
          f"- **Low volume**: the speech parts average below {QUIET_DBFS:g} dBFS.",
          f"- **Leading silence**: more than {LEADING_SILENCE_SEC:g} s before the first speech.",
          f"- **Cut off**: speech is still loud in the last {int(CUTOFF_TAIL_SEC * 1000)} ms (a guess; listen to confirm).",
          f"- **Big text change**: more than {BIG_CHANGE:.0%} of the prompt's words were changed, added or removed.",
          "- **Bengali script / unusual characters**: `actual_text` should only contain Latin letters, digits and normal punctuation.",
          "- **Duplicate take**: same speaker, same prompt recorded again. **Duplicate audio**: byte-identical audio.",
          "", "These are automatic checks. They can be wrong, so listen before deleting anything.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="dataset", help="folder with manifest.csv and wavs/ (default: dataset)")
    ap.add_argument("--out", default="reports", help="where to write qc_report.md and flagged.csv (default: reports)")
    args = ap.parse_args()
    run(args.dataset, args.out)


if __name__ == "__main__":
    main()
