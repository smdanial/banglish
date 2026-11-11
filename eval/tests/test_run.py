"""End-to-end run with a fake plugin model (no downloads, no network): resumability + outputs."""
import csv
import json
import wave

import yaml

from eval import run

PLUGIN = '''
import json, os
CALLS = os.environ["FAKE_CALLS"]
def transcribe(path):
    with open(CALLS, "a") as f: f.write(path + "\\n")
    return {"a.wav": "ami kal 4 tay jabo", "b.wav": "আমি ৫০ টাকা দিলাম", "c.wav": "bhul kotha"}[os.path.basename(path)]
'''


def test_end_to_end_and_resume(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "wavs").mkdir(parents=True)
    rows = [("a.wav", "s1", "Ami kal 4 tay jabo.", "food"), ("b.wav", "s2", "Ami 50 taka dilam.", "expenses"),
            ("c.wav", "s2", "Ami 10 tay ashbo.", "expenses")]
    with open(data / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "speaker_id", "prompt_text", "actual_text", "category", "duration"])
        for name, spk, text, cat in rows:
            with wave.open(str(data / "wavs" / name), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000); wf.writeframes(b"\0\0" * 8000)
            w.writerow([f"wavs/{name}", spk, text, text, cat, "0.5"])
    plugin = tmp_path / "fake.py"
    plugin.write_text(PLUGIN)
    calls = tmp_path / "calls.txt"
    monkeypatch.setenv("FAKE_CALLS", str(calls))
    out = tmp_path / "results"
    cfg = {"data": {"dir": str(data)}, "output_dir": str(out), "romanizer": {"method": "rules",
           "cache_dir": str(tmp_path / "cache")}, "isolate_models": False,
           "models": [{"name": "fake", "type": "plugin", "file": str(plugin), "romanize": True},
                      {"name": "off", "type": "plugin", "file": str(plugin), "enabled": False}]}
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg))

    assert run.main(["--config", str(cfg_file)]) == 0
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "fake + romanizer (rules)" in summary
    assert "No splits.json given" in summary and "3 clips from 2 speakers" in summary
    assert "off: disabled in config" in summary
    assert "66.7% (2/3)" in summary  # key fields: a ok, b ok (৫০ -> 50), c wrong
    worst = list(csv.DictReader(open(out / "fake" / "worst.csv", encoding="utf-8")))
    assert worst[0]["path"] == "wavs/c.wav" and worst[0]["key_fields_ok"] == "NO"
    assert worst[-1]["hypothesis"] in ("ami kal 4 tay jabo", "ami 50 taka dilam")
    assert len(calls.read_text().splitlines()) == 3

    assert run.main(["--config", str(cfg_file)]) == 0  # resume: nothing re-transcribed
    assert len(calls.read_text().splitlines()) == 3

    (data / "splits.json").write_text(json.dumps({"test": ["s2"]}))
    assert run.main(["--config", str(cfg_file), "--splits", str(data / "splits.json")]) == 0
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "Split: **test**" in summary and "2 clips from 1 speakers" in summary
    assert len(calls.read_text().splitlines()) == 3
