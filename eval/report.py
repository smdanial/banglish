"""Scoring (WER/CER/key-field accuracy) and writing summary.md / worst.csv."""
from __future__ import annotations

import csv
import platform
from collections import defaultdict
from pathlib import Path

import jiwer


def score_utt(ref_norm: str, hyp_norm: str):
    w = jiwer.process_words(ref_norm, hyp_norm)
    c = jiwer.process_characters(ref_norm, hyp_norm)
    w_err = w.substitutions + w.deletions + w.insertions
    c_err = c.substitutions + c.deletions + c.insertions
    w_n = w.substitutions + w.deletions + w.hits
    c_n = c.substitutions + c.deletions + c.hits
    return w_err, w_n, c_err, c_n


class Agg:
    def __init__(self):
        self.w_err = self.w_n = self.c_err = self.c_n = 0
        self.kf_n = self.kf_ok = self.clips = 0
        self.speakers = set()

    def add(self, u):
        self.clips += 1
        self.w_err += u["w_err"]; self.w_n += u["w_n"]
        self.c_err += u["c_err"]; self.c_n += u["c_n"]
        self.speakers.add(u["speaker_id"])
        if u["kf_has"]:
            self.kf_n += 1
            self.kf_ok += int(u["kf_ok"])

    @property
    def wer(self):
        return self.w_err / self.w_n if self.w_n else None

    @property
    def cer(self):
        return self.c_err / self.c_n if self.c_n else None

    @property
    def kf(self):
        return self.kf_ok / self.kf_n if self.kf_n else None


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def counts(c) -> str:
    return ", ".join(f"{k} {n}" for k, n in c.most_common()) or "n/a"


def script_cell(r) -> str:
    if not r.get("script_n"):
        return "n/a"
    return f"{pct(r['script_ok'] / r['script_n'])} ({r['script_ok']}/{r['script_n']} {r['expected']})"


def kf_cell(a: Agg):
    return "n/a (no numbers)" if a.kf is None else f"{pct(a.kf)} ({a.kf_ok}/{a.kf_n})"


def write_utts(path: Path, utts, n=None):
    fields = ["path", "speaker_id", "category", "wer", "cer", "key_fields_ok", "reference", "hypothesis",
              "reference_normalized", "hypothesis_normalized", "reference_key_fields", "hypothesis_key_fields",
              "raw_model_output", "raw_script", "language_requested", "language_used", "language_detected"]
    rows = sorted(utts, key=lambda u: (-u["wer"], -u["cer"]))[: n or len(utts)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for u in rows:
            w.writerow({**u, "wer": f"{u['wer']:.3f}", "cer": f"{u['cer']:.3f}",
                        "key_fields_ok": "" if not u["kf_has"] else ("yes" if u["kf_ok"] else "NO")})


def machine_info():
    try:
        import psutil
        ram = f"{psutil.virtual_memory().total / 2**30:.1f} GB RAM"
        cores = f"{psutil.cpu_count(logical=False) or '?'} cores / {psutil.cpu_count()} threads"
    except Exception:  # noqa: BLE001
        ram, cores = "? RAM", "? cores"
    cpu = platform.processor() or platform.machine()
    return f"{platform.system()} {platform.release()}, {cpu}, {cores}, {ram}, Python {platform.python_version()}"


def write_summary(path: Path, ctx: dict, results: list, skipped: list):
    L = []
    L.append("# Banglish speech model comparison\n")
    L.append(f"Generated {ctx['time']} on: {ctx['machine']}\n")
    L.append(f"- Data: `{ctx['data_dir']}` ({ctx['manifest_rows']} rows in manifest)")
    L.append(f"- {ctx['split_note']}")
    L.append(f"- **Evaluated: {ctx['n_clips']} clips from {ctx['n_speakers']} speakers, "
             f"{ctx['audio_minutes']:.1f} minutes of audio**")
    if ctx.get("problems"):
        L.append(f"- Data problems: {ctx['problems']}")
    L.append("")
    L.append("## Overall\n")
    L.append("| Model | Run variant | WER | CER | Key-field acc | % outputs in expected script | Speed (s per audio s) "
             "| Peak RAM | Clips |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    order = sorted(results, key=lambda r: (-(r["overall"].kf if r["overall"].kf is not None else -1),
                                          r["overall"].wer if r["overall"].wer is not None else 9))
    for r in order:
        a = r["overall"]
        speed = "n/a" if r["speed"] is None else f"{r['speed']:.2f}"
        ram = "n/a" if r["ram_mb"] is None else f"{r['ram_mb']:.0f} MB"
        clips = f"{a.clips}" + (f" ({r['failed']} failed)" if r["failed"] else "")
        L.append(f"| {r['label']} | {r.get('variant') or '-'} | {pct(a.wer)} | {pct(a.cer)} | {kf_cell(a)} "
                 f"| {script_cell(r)} | {speed} | {ram} | {clips} |")
    L.append("")
    L.append("Sorted by key-field accuracy, then WER. Lower WER/CER/speed/RAM is better; higher key-field acc is better.\n")
    if skipped:
        L.append("**Not run:**\n")
        for name, why in skipped:
            L.append(f"- {name}: {why}")
        L.append("")
    notes = [n for r in results for n in r["notes"]]
    if notes or ctx.get("romanizer_note"):
        L.append("**Notes:**\n")
        if ctx.get("romanizer_note"):
            L.append(f"- {ctx['romanizer_note']}")
        for n in notes:
            L.append(f"- {n}")
        L.append("")
    L.append("## Language and script check\n")
    L.append("Per run, in config order. Counts are clips. \"Whisper detects\" is the language Whisper itself hears "
             "in the audio (checked even when the language is forced).\n")
    L.append("| Run | Run variant | % outputs in expected script | Raw output script | Language passed "
             "| Language used for decoding | Whisper detects |")
    L.append("|---|---|---|---|---|---|---|")
    for r in results:
        lg = r.get("lang") or {}
        if r.get("type") == "faster_whisper":
            cells = [counts(lg.get(k) or {}) if lg.get(k) else "not recorded" for k in ("requested", "used", "detected")]
        else:
            cells = ["n/a (not Whisper)"] * 3
        L.append(f"| {r.get('name', r['label'])} | {r.get('variant') or '-'} | {script_cell(r)} "
                 f"| {counts(r.get('scripts') or {})} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("## Per category\n")
    cats = sorted({c for r in results for c in r["by_cat"]})
    for c in cats:
        L.append(f"### {c}\n")
        L.append("| Model | WER | CER | Key-field acc | Clips |")
        L.append("|---|---|---|---|---|")
        for r in order:
            a = r["by_cat"].get(c)
            if a:
                L.append(f"| {r['label']} | {pct(a.wer)} | {pct(a.cer)} | {kf_cell(a)} | {a.clips} |")
        L.append("")
    L.append("## How to read this\n")
    L.append("- **WER / CER**: word / character error rate after normalization (lowercase, no punctuation, "
             "spelling variants from `eval/normalization.yaml`).")
    L.append("- **Key-field acc**: share of clips whose reference contains at least one number or time where the "
             "model got ALL numbers and times exactly right (no missing, wrong or extra ones). "
             "Counted only over clips that contain numbers/times (the count is shown).")
    L.append("- **\"+ romanizer (...)\"**: the model wrote Bengali script, which was converted to Banglish before "
             "scoring. Errors in those rows are model errors PLUS romanizer errors. `rules` = rough offline "
             "converter (more error); `llm:<model>` = LLM converter. Raw model output is in "
             "`<model>/hypotheses.csv`.")
    L.append("- **Run variant**: the same model run with different language settings (`run_variants:` in the "
             "config): (a) `language=bn` forced, (b) auto-detect, (c) `language=en` forced with a romanized-Banglish "
             "`initial_prompt`. Results per variant are in `<model>_<variant>/`.")
    L.append("- **% outputs in expected script**: share of clips whose RAW model output (before any romanizer) is "
             "mainly in the script that run should write: Bengali for `bn` and auto-detect, Latin for `en` and "
             "Gemini. Devanagari/Arabic here means Whisper wrote Hindi/Urdu letters.")
    L.append("- **Speed**: processing seconds per second of audio on this machine (below 1.0 = faster than "
             "real time); model loading not included. For API models it includes network time.")
    L.append("- **Peak RAM**: highest memory use of the process that ran the model (includes Python itself, "
             "~100 MB). For API models this is only the local client.")
    L.append(f"- Worst {ctx['worst_n']} clips per model: `<model>/worst.csv` next to this file.")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def group(utts):
    overall, by_cat = Agg(), defaultdict(Agg)
    for u in utts:
        overall.add(u)
        by_cat[u["category"]].add(u)
    return overall, dict(by_cat)
