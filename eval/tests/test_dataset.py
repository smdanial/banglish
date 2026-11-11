import csv
import json
import wave

import pytest

from eval.dataset import load_manifest, select_split


def make_data(tmp_path, rows):
    (tmp_path / "wavs").mkdir()
    for r in rows:
        with wave.open(str(tmp_path / r["path"]), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b"\0\0" * 16000)
    with open(tmp_path / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "speaker_id", "prompt_text", "actual_text", "category", "duration"])
        w.writeheader()
        w.writerows(rows)


ROWS = [{"path": f"wavs/{i}.wav", "speaker_id": f"spk{i % 3}", "prompt_text": "p", "actual_text": "ami",
         "category": "c", "duration": "9"} for i in range(6)]


def test_manifest_and_duration_from_wav(tmp_path):
    make_data(tmp_path, ROWS)
    clips, problems, n = load_manifest(tmp_path)
    assert n == 6 and len(clips) == 6 and clips[0].duration == pytest.approx(1.0)
    assert not any(problems.values())


@pytest.mark.parametrize("splits", [
    {"test": ["spk0"], "train": ["spk1", "spk2"]},
    {"splits": {"test": ["spk0"]}},
    {"test": {"speakers": ["spk0"]}},
    {"test": ["wavs/0.wav", "3.wav"]},
    {"wavs/0.wav": "test", "wavs/3.wav": "test", "wavs/1.wav": "train"},
])
def test_split_shapes(tmp_path, splits):
    make_data(tmp_path, ROWS)
    clips, _, _ = load_manifest(tmp_path)
    (tmp_path / "splits.json").write_text(json.dumps(splits))
    chosen = select_split(clips, tmp_path / "splits.json", "test")
    assert sorted(c.path for c in chosen) == ["wavs/0.wav", "wavs/3.wav"]


def test_unknown_split_fails(tmp_path):
    make_data(tmp_path, ROWS)
    clips, _, _ = load_manifest(tmp_path)
    (tmp_path / "splits.json").write_text(json.dumps({"train": ["spk0"]}))
    with pytest.raises(SystemExit):
        select_split(clips, tmp_path / "splits.json", "test")
