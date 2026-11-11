"""Load manifest.csv and (optionally) choose one split from splits.json."""
from __future__ import annotations

import csv
import json
import wave
from dataclasses import dataclass
from pathlib import Path

REQUIRED = ["path", "speaker_id", "prompt_text", "actual_text", "category", "duration"]


@dataclass
class Clip:
    path: str          # as written in the manifest (used as the clip id)
    abs_path: Path
    speaker_id: str
    prompt_text: str
    reference: str     # actual_text (falls back to prompt_text if empty)
    category: str
    duration: float    # seconds, measured from the WAV when possible


def wav_info(path: Path):
    """(duration_s, sample_rate, channels) or None if not a readable PCM WAV."""
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate()), w.getframerate(), w.getnchannels()
    except (wave.Error, EOFError, OSError):
        return None


def load_manifest(data_dir: Path, manifest_name: str = "manifest.csv"):
    data_dir = Path(data_dir)
    mpath = data_dir / manifest_name
    if not mpath.exists():
        raise SystemExit(f"manifest not found: {mpath}")
    with open(mpath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{mpath} is missing columns: {', '.join(missing)}")
        rows = list(reader)
    clips, problems = [], {"missing_file": 0, "not_16k_mono": 0, "empty_reference": 0}
    for r in rows:
        p = Path(r["path"])
        ap = p if p.is_absolute() else data_dir / p
        ref = (r.get("actual_text") or "").strip() or (r.get("prompt_text") or "").strip()
        if not ref:
            problems["empty_reference"] += 1
            continue
        if not ap.exists():
            problems["missing_file"] += 1
            continue
        info = wav_info(ap)
        if info is None or info[1] != 16000 or info[2] != 1:
            problems["not_16k_mono"] += 1
        try:
            dur = info[0] if info else float(r.get("duration") or 0)
        except ValueError:
            dur = 0.0
        clips.append(Clip(r["path"], ap, r.get("speaker_id", ""), r.get("prompt_text", ""), ref,
                          (r.get("category") or "").strip() or "uncategorized", dur))
    return clips, problems, len(rows)


def _as_list(v):
    if isinstance(v, dict):  # {"speakers": [...], "clips": [...]} or similar
        out = []
        for x in v.values():
            out.extend(_as_list(x))
        return out
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def select_split(clips, splits_file, split_name: str):
    """Keep only clips in `split_name`. Accepts these splits.json shapes:
       {"test": [ids...], "train": [...]}, {"splits": {...}}, {"test": {"speakers": [...]}}, {"<clip path>": "test"}
    where ids may be speaker_ids, clip paths (as in the manifest) or file names."""
    data = json.loads(Path(splits_file).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("splits"), dict):
        data = data["splits"]
    if not isinstance(data, dict):
        raise SystemExit(f"{splits_file}: expected a JSON object")
    if split_name in data:
        ids = set(_as_list(data[split_name]))
    elif data and all(isinstance(v, str) for v in data.values()):  # {"clip": "split"}
        ids = {k for k, v in data.items() if v == split_name}
    else:
        raise SystemExit(f"{splits_file}: no split named '{split_name}' (found: {', '.join(map(str, data))})")
    chosen = [c for c in clips
              if c.speaker_id in ids or c.path in ids or Path(c.path).name in ids or Path(c.path).stem in ids]
    if not chosen:
        raise SystemExit(f"split '{split_name}' in {splits_file} matched none of the {len(clips)} clips "
                         "(ids must be speaker_ids, clip paths or file names)")
    return chosen
