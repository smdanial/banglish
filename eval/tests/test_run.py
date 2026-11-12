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


def test_quick_limits_to_30_clips(tmp_path):
    data = tmp_path / "data"
    (data / "wavs").mkdir(parents=True)
    plugin = tmp_path / "echo.py"
    plugin.write_text("def transcribe(path):\n    return 'ami jabo'\n")
    with open(data / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "speaker_id", "prompt_text", "actual_text", "category", "duration"])
        for i in range(40):
            with wave.open(str(data / "wavs" / f"{i}.wav"), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000); wf.writeframes(b"\0\0" * 8000)
            w.writerow([f"wavs/{i}.wav", f"s{i % 4}", "ami jabo", "ami jabo", "food", "0.5"])
    out = tmp_path / "results"
    cfg = {"data": {"dir": str(data)}, "output_dir": str(out), "isolate_models": False,
           "models": [{"name": "echo", "type": "plugin", "file": str(plugin)}]}
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg))
    assert run.main(["--config", str(cfg_file), "--quick"]) == 0
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "limited to first 30 clips" in summary and "30 clips from 4 speakers" in summary


def test_run_variants_expected_script_and_language_log(tmp_path):
    """Variants expand to <name>:<id>, --models <base> selects all of them, the script column is filled, and
    per-clip language info returned by the model (last_info) is stored and summarized."""
    data = tmp_path / "data"
    (data / "wavs").mkdir(parents=True)
    with open(data / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "speaker_id", "prompt_text", "actual_text", "category", "duration"])
        for i in range(4):
            with wave.open(str(data / "wavs" / f"{i}.wav"), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000); wf.writeframes(b"\0\0" * 8000)
            w.writerow([f"wavs/{i}.wav", "s1", "ami jabo", "ami jabo", "food", "0.5"])
    plugin = tmp_path / "fakewhisper.py"
    plugin.write_text(
        "import os\n"
        "LANG = None\n"
        "def setup(options):\n"
        "    global LANG\n"
        "    LANG = options['language']\n"
        "def transcribe(path):\n"
        "    n = int(os.path.basename(path)[0])\n"
        "    if LANG == 'en':\n"
        "        return 'ami jabo'\n"
        "    return 'आमि जाबो' if n < 3 else 'আমি যাবো'\n")
    out = tmp_path / "results"
    cfg = {"data": {"dir": str(data)}, "output_dir": str(out), "isolate_models": False,
           "romanizer": {"method": "rules", "cache_dir": str(tmp_path / "cache")},
           "run_variants": [{"id": "bn", "label": "(a) language=bn forced", "options": {"language": "bn"},
                             "expected_script": "Bengali"},
                            {"id": "en-prompt", "label": "(c) en + prompt", "options": {"language": "en"},
                             "expected_script": "Latin"}],
           "models": [{"name": "fw", "type": "plugin", "file": str(plugin), "romanize": True,
                       "variants": ["bn", "en-prompt"]},
                      {"name": "other", "type": "plugin", "file": str(plugin), "options": {"language": "en"}}]}
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg))
    assert run.main(["--config", str(cfg_file), "--models", "fw"]) == 0
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "% outputs in expected script" in summary
    assert "| fw:bn | (a) language=bn forced | 25.0% (1/4 Bengali) | Devanagari 3, Bengali 1 |" in summary
    assert "| fw:en-prompt | (c) en + prompt | 100.0% (4/4 Latin) | Latin 4 |" in summary
    assert "other" not in summary.split("## Language")[0].split("## Overall")[1]
    assert (out / "fw_bn" / "hypotheses.csv").exists() and (out / "fw_en-prompt" / "hypotheses.csv").exists()


def test_faster_whisper_language_is_passed_and_logged(tmp_path, monkeypatch):
    """language=bn reaches WhisperModel.transcribe; auto -> None; en-prompt passes initial_prompt."""
    import sys
    import types

    calls = []

    class Info:
        def __init__(self, lang):
            self.language, self.language_probability = lang, 0.9

    class Seg:
        text = " ami jabo "

    class FakeWhisper:
        def __init__(self, *a, **k):
            self.feature_extractor = types.SimpleNamespace(sampling_rate=16000)

        def transcribe(self, audio, language=None, initial_prompt=None, **kw):
            calls.append({"language": language, "initial_prompt": initial_prompt})
            return iter([Seg()]), Info(language or "hi")

        def detect_language(self, audio):
            return "hi", 0.7, []

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeWhisper
    fake.decode_audio = lambda path, sampling_rate=16000: [0.0]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    from eval.models.faster_whisper_model import FasterWhisperModel

    m = FasterWhisperModel({"language": "bn"})
    assert m.transcribe("x.wav") == "ami jabo"
    assert m.last_info == {"language_requested": "bn", "language_used": "bn", "language_detected": "hi",
                           "language_detected_prob": 0.7}
    m = FasterWhisperModel({"language": "auto"})
    m.transcribe("x.wav")
    assert calls[-1]["language"] is None and m.last_info["language_requested"] == "auto"
    assert m.last_info["language_used"] == "hi" and m.last_info["language_detected"] == "hi"
    m = FasterWhisperModel({"language": "en", "initial_prompt": "ami jabo.", "detect_language": False})
    m.transcribe("x.wav")
    assert calls[-1] == {"language": "en", "initial_prompt": "ami jabo."}
    assert "language_detected" not in m.last_info
