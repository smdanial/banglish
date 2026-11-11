"""Run with:  python3 -m unittest discover -s tests   (from the data-collector folder)"""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PLANTED = {"too_short", "too_long", "mostly_silence", "no_speech", "clipping", "low_volume",
           "long_leading_silence", "cut_off", "empty_text", "bengali_script", "odd_characters",
           "big_text_change", "duplicate_take", "duplicate_audio", "missing_file"}


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True)


class QcAndSplits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name) / "data"
        cls.reports = Path(cls.tmp.name) / "reports"
        r = run("tests/make_sample_data.py", "--out", cls.data)
        assert r.returncode == 0, r.stderr
        r = run("scripts/qc_dataset.py", "--dataset", cls.data, "--out", cls.reports)
        assert r.returncode == 0, r.stderr
        with open(cls.reports / "flagged.csv", newline="", encoding="utf-8-sig") as f:
            cls.flagged = list(csv.DictReader(f))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_planted_problem_is_found(self):
        found = {i.strip() for r in self.flagged for i in r["issues"].split(";")}
        self.assertEqual(PLANTED - found, set())

    def test_clean_clips_are_not_flagged(self):
        # 91 clips, 15 planted problem clips (one row carries two planted issues)
        self.assertEqual(len(self.flagged), 15)

    def test_report_has_problem_list_and_tables(self):
        text = (self.reports / "qc_report.md").read_text(encoding="utf-8")
        for heading in ("## Problems to fix", "## Per speaker", "## Per category"):
            self.assertIn(heading, text)
        self.assertIn("spk_sample03", text.split("## Overview")[0])  # high-flag speaker called out

    def write(self, name, text):
        p = Path(self.tmp.name) / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_splits_by_speaker(self):
        cfg = self.write("s.md", "# Splits\nSome notes.\n## test\n- spk_sample01 note\nspeaker_id=spk_sample02\n"
                                 "## dev\n- `spk_sample04`\n")
        out = Path(self.tmp.name) / "splits.json"
        r = run("scripts/make_splits.py", "--dataset", self.data, "--config", cfg, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(out.read_text())
        self.assertEqual(d["speakers"]["test"], ["spk_sample01", "spk_sample02"])
        self.assertEqual(d["speakers"]["dev"], ["spk_sample04"])
        self.assertIn("spk_sample05", d["speakers"]["train"])
        sets = [set(v) for v in d["speakers"].values()]
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        with open(self.data / "manifest.csv", newline="", encoding="utf-8") as f:
            self.assertEqual(sum(len(v) for v in d["clips"].values()), len(list(csv.DictReader(f))))
        self.assertIn("fewer than 15 clips in the test split", r.stdout)

    def test_refuses_speaker_in_two_sets(self):
        cfg = self.write("bad.yaml", "test: [spk_sample01, spk_sample02]\ndev:\n  - spk_sample02\n")
        out = Path(self.tmp.name) / "bad.json"
        r = run("scripts/make_splits.py", "--dataset", self.data, "--config", cfg, "--out", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("spk_sample02", r.stderr)
        self.assertFalse(out.exists())

    def test_refuses_speaker_outside_test_and_dev(self):
        cfg = self.write("loose.md", "# Splits\nspeaker_id=spk_sample05\n## test\n- spk_sample01\n")
        out = Path(self.tmp.name) / "loose.json"
        r = run("scripts/make_splits.py", "--dataset", self.data, "--config", cfg, "--out", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("spk_sample05", r.stderr)
        self.assertFalse(out.exists())

    def test_exclude_drops_remove_clips(self):
        cfg = self.write("e.yaml", "test:\n  - spk_sample01\ndev: []\n")
        out = Path(self.tmp.name) / "e.json"
        r = run("scripts/make_splits.py", "--dataset", self.data, "--config", cfg, "--out", out,
                "--exclude", self.reports / "flagged.csv")
        self.assertEqual(r.returncode, 0, r.stderr)
        removed = {f["path"] for f in self.flagged if f["suggested_action"] == "remove"}
        kept = {p for v in json.loads(out.read_text())["clips"].values() for p in v}
        self.assertFalse(removed & kept)
        self.assertEqual(json.loads(out.read_text())["excluded_clips"], len(removed))


def tone(path, freq, width=2, silent=False, sec=2.0, rate=16000):
    t = np.arange(int(sec * rate)) / rate
    x = np.zeros_like(t) if silent else 0.3 * np.sin(2 * np.pi * freq * t)
    x[: int(0.3 * rate)] = 0
    x[-int(0.3 * rate):] = 0
    v = np.round(x * (2 ** (8 * width - 1) - 1)).astype("<i4")
    raw = v.astype("<i2").tobytes() if width == 2 else b"".join(int(s).to_bytes(width, "little", signed=True) for s in v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(raw)


class QcEdgeCases(unittest.TestCase):
    def test_retake_kept_24bit_not_removed_formula_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            text = "ami aj bikal 4 tay bazar e jabo"
            tone(d / "a.wav", 0, silent=True)        # broken first take
            tone(d / "b.wav", 220)                   # good retake of the same prompt
            tone(d / "c.wav", 330, width=3)          # playable, but 24-bit
            tone(d / "d.wav", 440)
            rows = [("a.wav", "spk_x", "p001", text), ("b.wav", "spk_x", "p001", text),
                    ("c.wav", "spk_y", "p002", text), ("d.wav", "spk_y", "p003", '=HYPERLINK("http://x")')]
            with open(d / "manifest.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["path", "speaker_id", "prompt_id", "prompt_text", "actual_text", "category", "duration"])
                for p, s, pid, actual in rows:
                    w.writerow([p, s, pid, text, actual, "travel", "2.0"])
            r = run("scripts/qc_dataset.py", "--dataset", d, "--out", d / "reports")
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(d / "reports" / "flagged.csv", newline="", encoding="utf-8-sig") as f:
                flagged = {row["path"]: row for row in csv.DictReader(f)}
        self.assertNotIn("b.wav", flagged)
        self.assertIn("no_speech", flagged["a.wav"]["issues"])
        self.assertIn("wrong_format", flagged["c.wav"]["issues"])
        self.assertNotIn("unreadable", flagged["c.wav"]["issues"])
        self.assertEqual(flagged["c.wav"]["suggested_action"], "listen")
        self.assertTrue(flagged["d.wav"]["actual_text"].startswith("'="))


if __name__ == "__main__":
    unittest.main()
