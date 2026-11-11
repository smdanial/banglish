"""Create the tiny SYNTHETIC sample in eval/sample/ (text-to-speech, no real voices).

    python -m eval.sample.make_sample            # creates missing WAVs + manifest.csv
    python -m eval.sample.make_sample --force    # re-creates everything

The WAVs are not committed to git (no audio in the repo); eval.run calls this automatically.
Engines, tried in order: Google TTS (gTTS, needs internet), espeak-ng (if installed),
and finally plain tones (offline; tests the plumbing only, every model will score badly).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
WAVS = HERE / "wavs"
SR = 16000


def _write_wav(path: Path, samples):
    """samples: iterable of floats in [-1, 1] at 16 kHz mono."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples))


def _gtts(item, path):
    from gtts import gTTS  # noqa: WPS433
    from faster_whisper.audio import decode_audio
    buf = io.BytesIO()
    gTTS(item["tts_text"], lang="bn", slow=bool(item.get("slow"))).write_to_fp(buf)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(buf.getvalue())
        mp3 = f.name
    try:
        audio = decode_audio(mp3, sampling_rate=SR)  # PyAV, installed with faster-whisper
    finally:
        Path(mp3).unlink(missing_ok=True)
    _write_wav(path, [0.0] * int(0.3 * SR) + [float(x) for x in audio] + [0.0] * int(0.3 * SR))


def _espeak(item, path):
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("espeak-ng not installed")
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d) / "a.wav"
        speed = "120" if item.get("slow") else "160"
        subprocess.run([exe, "-v", "bn", "-s", speed, "-w", str(raw), item["tts_text"]], check=True,
                       capture_output=True)
        from faster_whisper.audio import decode_audio
        audio = decode_audio(str(raw), sampling_rate=SR)
    _write_wav(path, [float(x) for x in audio])


def _tones(item, path):
    n_words = len(item["prompt_text"].split())
    out = []
    for i in range(n_words):
        f = 180 + 40 * (i % 5)
        out += [0.3 * math.sin(2 * math.pi * f * t / SR) for t in range(int(0.25 * SR))]
        out += [0.0] * int(0.08 * SR)
    _write_wav(path, out)


ENGINES = [("gtts", _gtts), ("espeak-ng", _espeak), ("tones", _tones)]


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def generate(force: bool = False) -> str:
    items = json.loads((HERE / "sample_texts.json").read_text(encoding="utf-8"))
    used = set()
    for item in items:
        dst = WAVS / item["file"]
        if dst.exists() and not force:
            continue
        for name, fn in ENGINES:
            try:
                fn(item, dst)
                used.add(name)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  sample: {name} failed for {item['file']} ({type(e).__name__}: {str(e)[:80]})",
                      file=sys.stderr)
    if used:
        (WAVS / "ENGINE.txt").write_text(", ".join(sorted(used)) + "\n", encoding="utf-8")
        print(f"Synthetic sample created with: {', '.join(sorted(used))}")
        if "tones" in used:
            print("WARNING: some sample clips are plain tones (no TTS available); scores will be meaningless.",
                  file=sys.stderr)
    with open(HERE / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "speaker_id", "prompt_text", "actual_text", "category",
                                          "duration"], lineterminator="\n")
        w.writeheader()
        for item in items:
            p = WAVS / item["file"]
            w.writerow({"path": f"wavs/{item['file']}", "speaker_id": item["speaker_id"],
                        "prompt_text": item["prompt_text"], "actual_text": item["actual_text"],
                        "category": item["category"], "duration": f"{_duration(p):.3f}" if p.exists() else ""})
    return ", ".join(sorted(used))


def ensure_sample():
    items = json.loads((HERE / "sample_texts.json").read_text(encoding="utf-8"))
    if not all((WAVS / i["file"]).exists() for i in items) or not (HERE / "manifest.csv").exists():
        print("Creating the synthetic sample audio in eval/sample/wavs/ ...")
        generate()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    generate(ap.parse_args().force)
