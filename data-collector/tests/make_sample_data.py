#!/usr/bin/env python3
"""Create a small SYNTHETIC dataset (beeps that look like speech, not real voices) for testing
qc_dataset.py and make_splits.py. Same layout as export_dataset.py output: manifest.csv + wavs/.

Usage (from the data-collector folder):
    python3 tests/make_sample_data.py                  # writes tests/sample_data/
It plants known problems (short, long, silent, clipped, quiet, cut-off, bad text, duplicates, ...)
so the QC report has something to find. Output is deterministic (fixed random seed).
"""
import argparse
import csv
import json
import random
import shutil
import uuid
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RATE = 16000
FIELDS = ["path", "speaker_id", "prompt_text", "actual_text", "category", "duration",
          "prompt_id", "phone_model", "age_range", "region", "recording_id", "created_at"]
SPEAKERS = [  # id, phone, age, region, f0 (Hz)
    ("spk_sample01", "Samsung Galaxy A12", "25-34", "Dhaka", 120),
    ("spk_sample02", "Xiaomi Redmi Note 10", "18-24", "Chattogram", 210),
    ("spk_sample03", "Walton Primo H9", "35-44", "Sylhet", 140),
    ("spk_sample04", "iPhone 11", "18-24", "Khulna", 190),
    ("spk_sample05", "", "", "", 110),
    ("spk_sample06", "Realme C11", "45-54", "Rajshahi", 230),
    ("spk_sample07", "Samsung Galaxy A12", "25-34", "Barishal", 160),
    ("spk_sample08", "Tecno Spark 8", "18-24", "Rangpur", 200),
]


def syllable(rng, f0, sec):
    t = np.arange(int(RATE * sec)) / RATE
    f = f0 * (1 + 0.08 * np.sin(2 * np.pi * rng.uniform(2, 5) * t))
    phase = 2 * np.pi * np.cumsum(f) / RATE
    tone = sum(np.sin(k * phase) / k for k in range(1, 6))
    return tone * np.hanning(len(t))


def speech(rng, f0, words, cut_off=False):
    parts = []
    for w in range(words):
        for _ in range(rng.randint(1, 3)):
            parts += [syllable(rng, f0, rng.uniform(0.12, 0.25)), np.zeros(int(RATE * rng.uniform(0.02, 0.06)))]
        parts.append(np.zeros(int(RATE * rng.uniform(0.08, 0.18))))
    if cut_off:  # end in the loud middle of a long syllable
        s = syllable(rng, f0, 0.6)
        parts.append(s[: len(s) // 2])
    x = np.concatenate(parts)
    return x / np.max(np.abs(x))


def clip_audio(rng, f0, words, kind):
    sil = lambda s: np.zeros(int(RATE * s))
    peak = 0.5  # about -6 dBFS
    if kind == "too_short":
        x = np.concatenate([sil(0.1), speech(rng, f0, 1)[: int(RATE * 0.4)], sil(0.1)])
    elif kind == "too_long":
        x = np.concatenate([sil(0.3)] + [np.concatenate([speech(rng, f0, 6), sil(0.8)]) for _ in range(5)])
        x = np.concatenate([x, sil(max(0.0, 22 - len(x) / RATE))])
    elif kind == "mostly_silence":
        x = np.concatenate([sil(0.5), speech(rng, f0, 2), sil(5.0)])
    elif kind == "no_speech":
        x = sil(3.0)
    elif kind == "leading_silence":
        x = np.concatenate([sil(2.5), speech(rng, f0, words), sil(0.4)])
    elif kind == "cut_off":
        x = np.concatenate([sil(0.3), speech(rng, f0, words, cut_off=True)])
    else:
        x = np.concatenate([sil(0.3), speech(rng, f0, words), sil(0.4)])
    if kind == "low_volume":
        peak = 0.01  # about -40 dBFS
    x = x * peak
    if kind == "clipping":
        x = np.clip(x * 6, -1, 1)
    x = x + np.random.default_rng(rng.randint(0, 2 ** 31)).normal(0, 10 ** (-66 / 20), len(x))
    return np.clip(np.round(x * 32767), -32768, 32767).astype("<i2")


def write_wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())


def small_edit(rng, text):
    words = text.split()
    i = rng.randrange(len(words))
    words[i] = {"ami": "ame", "tumi": "tume", "kal": "kalke"}.get(words[i].lower(), words[i] + "o")
    return " ".join(words)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "sample_data"))
    args = ap.parse_args()
    out = Path(args.out)
    wavs = out / "wavs"
    if wavs.exists():
        shutil.rmtree(wavs)
    wavs.mkdir(parents=True)

    rng = random.Random(1234)
    prompts = json.loads((ROOT / "data" / "prompts.json").read_text(encoding="utf-8"))
    by_cat = {}
    for p in prompts:
        by_cat.setdefault(p["category"], []).append(p)
    cats = sorted(by_cat)

    # (speaker index, category index) -> planted problem
    planted = {
        (2, 0): "too_short", (2, 1): "too_long", (2, 2): "mostly_silence", (2, 3): "clipping",
        (2, 4): "low_volume", (3, 5): "leading_silence", (3, 6): "cut_off", (4, 7): "no_speech",
        (0, 1): "empty_text", (1, 2): "bengali_script", (1, 3): "odd_characters", (6, 4): "big_text_change",
    }
    rows, n = [], 0
    for si, (spk, phone, age, region, f0) in enumerate(SPEAKERS):
        for ci, cat in enumerate(cats):
            p = by_cat[cat][(si * 3 + ci) % len(by_cat[cat])]
            kind = planted.get((si, ci), "ok")
            words = len(p["text"].split())
            samples = clip_audio(rng, f0, words, kind)
            actual = p["text"]
            if kind == "empty_text":
                actual = ""
            elif kind == "bengali_script":
                actual = "আমি " + p["text"]
            elif kind == "odd_characters":
                actual = p["text"] + " \U0001F600 \u2605"
            elif kind == "big_text_change":
                actual = "Ami ekhon bujhte parchi na ki bolbo, porer ta dao"
            elif spk != "spk_sample05" and rng.random() < 0.25:
                actual = small_edit(rng, p["text"])
            rid = str(uuid.UUID(int=rng.getrandbits(128), version=4))
            n += 1
            rows.append({"path": f"wavs/{rid}.wav", "speaker_id": spk, "prompt_text": p["text"],
                         "actual_text": actual, "category": cat, "duration": f"{len(samples) / RATE:.3f}",
                         "prompt_id": p["id"], "phone_model": phone, "age_range": age, "region": region,
                         "recording_id": rid, "created_at": f"2026-11-01T10:{n // 60:02d}:{n % 60:02d}+00:00"})
            write_wav(out / rows[-1]["path"], samples)

    def extra(base, **kw):
        rid = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        r = dict(base, path=f"wavs/{rid}.wav", recording_id=rid, created_at="2026-11-01T11:00:00+00:00", **kw)
        rows.append(r)
        return r

    # same speaker records the same prompt again (new audio)
    base = rows[5 * len(cats) + 2]
    r = extra(base)
    s = clip_audio(rng, SPEAKERS[5][4], len(base["prompt_text"].split()), "ok")
    write_wav(out / r["path"], s)
    r["duration"] = f"{len(s) / RATE:.3f}"
    # byte-identical copy of another speaker's file, filed under a different prompt
    src = rows[7 * len(cats) + 1]
    other = by_cat[cats[9]][20]
    r = extra(src, prompt_id=other["id"], prompt_text=other["text"], actual_text=other["text"], category=cats[9])
    shutil.copyfile(out / src["path"], out / r["path"])
    # row whose audio file is missing
    extra(rows[len(cats) + 6])

    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out / 'manifest.csv'} and {len(list(wavs.glob('*.wav')))} WAVs to {wavs}")


if __name__ == "__main__":
    main()
