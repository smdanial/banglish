#!/usr/bin/env python3
"""Download every recording from Supabase, convert to 16 kHz mono WAV and write manifest.csv.

Usage (from the repo folder):
    python3 scripts/export_dataset.py              # writes ./dataset/
    python3 scripts/export_dataset.py --out mydata

Needs: Python 3.8+, ffmpeg on PATH, and these environment variables (or a .env file):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   (admin key - keep it on your own computer only)
Re-running is safe: files that were already converted are skipped.
"""
import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import wave
from pathlib import Path

from sbhttp import ROOT, Client, env, load_dotenv

PAGE = 1000
MANIFEST_FIELDS = ["path", "speaker_id", "prompt_text", "actual_text", "category", "duration",
                   "prompt_id", "phone_model", "age_range", "region", "recording_id", "created_at"]


def fetch_rows(client):
    rows, offset = [], 0
    while True:
        q = f"/rest/v1/recordings?select=*&order=created_at.asc,id.asc&limit={PAGE}&offset={offset}"
        status, body = client.request("GET", q)
        if status != 200:
            raise SystemExit(f"Could not read the recordings table (HTTP {status}): {body[:300]!r}\n"
                             "Check SUPABASE_URL and that SUPABASE_SERVICE_ROLE_KEY is the admin key.")
        batch = json.loads(body)
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        offset += PAGE


def wav_duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def convert(src, dst):
    tmp = dst.with_suffix(".tmp.wav")
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
           "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", "-c:a", "pcm_s16le", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(r.stderr.strip()[-300:])
    tmp.replace(dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="dataset", help="output folder (default: dataset)")
    ap.add_argument("--keep-original", action="store_true", help="also keep the original webm/m4a files")
    args = ap.parse_args()

    load_dotenv()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not installed or not on PATH. Install it from https://ffmpeg.org/download.html")
    client = Client(env("SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"))
    bucket = env("SUPABASE_BUCKET", required=False) or "recordings"

    prompts_file = ROOT / "data" / "prompts.json"
    categories = {p["id"]: p["category"] for p in json.loads(prompts_file.read_text(encoding="utf-8"))}

    out = Path(args.out).resolve()
    wav_dir = out / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)
    orig_dir = out / "original"
    if args.keep_original:
        orig_dir.mkdir(exist_ok=True)

    rows = fetch_rows(client)
    print(f"{len(rows)} rows in the recordings table")
    manifest, failed, new = [], 0, 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, row in enumerate(rows, 1):
            dst = wav_dir / f"{row['id']}.wav"
            if not dst.exists():
                status, data = client.request(
                    "GET", f"/storage/v1/object/{bucket}/{urllib.parse.quote(row['audio_path'])}")
                if status != 200 or not data:
                    print(f"  [{i}] download failed for {row['audio_path']} (HTTP {status})", file=sys.stderr)
                    failed += 1
                    continue
                ext = Path(row["audio_path"]).suffix or ".bin"
                src = Path(tmpdir) / f"{row['id']}{ext}"
                src.write_bytes(data)
                try:
                    convert(src, dst)
                except RuntimeError as e:
                    print(f"  [{i}] ffmpeg failed for {row['audio_path']}: {e}", file=sys.stderr)
                    failed += 1
                    continue
                if args.keep_original:
                    shutil.copyfile(src, orig_dir / src.name)
                new += 1
            manifest.append({
                "path": dst.relative_to(out).as_posix(),
                "speaker_id": row["speaker_id"],
                "prompt_text": row["prompt_text"],
                "actual_text": row["actual_text"],
                "category": row.get("category") or categories.get(row["prompt_id"], ""),
                "duration": f"{wav_duration(dst):.3f}",
                "prompt_id": row["prompt_id"],
                "phone_model": row.get("phone_model") or "",
                "age_range": row.get("age_range") or "",
                "region": row.get("region") or "",
                "recording_id": row["id"],
                "created_at": row["created_at"],
            })
            if i % 50 == 0:
                print(f"  {i}/{len(rows)}")

    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(manifest)
    print(f"Done: {len(manifest)} clips in manifest ({new} newly converted, {failed} failed) -> {out / 'manifest.csv'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
