"""Transcribe clips with one model and append results to transcripts.jsonl (resumable).
Runs in its own process by default so peak RAM is measured per model."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path


class PeakRSS:
    """Peak resident memory (MB) of this process: sampled with psutil + OS high-water mark."""

    def __init__(self, interval=0.05):
        import psutil
        self.proc = psutil.Process()
        self.peak = self.proc.memory_info().rss
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, args=(interval,), daemon=True)

    def _run(self, interval):
        while not self._stop.wait(interval):
            try:
                self.peak = max(self.peak, self.proc.memory_info().rss)
            except Exception:  # noqa: BLE001
                return

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=1)

    def mb(self) -> float:
        peak = self.peak
        mi = self.proc.memory_info()
        peak = max(peak, getattr(mi, "peak_wset", 0))  # Windows
        try:
            import resource
            r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak = max(peak, r if sys.platform == "darwin" else r * 1024)
        except ImportError:
            pass
        return peak / (1024 * 1024)


def language_line(rec: dict) -> str:
    from .textnorm import main_script
    det = rec.get("language_detected")
    det = f"{det} ({rec.get('language_detected_prob', 0):.2f})" if det else "not checked"
    return (f"language passed={rec.get('language_requested')}, used={rec.get('language_used')}, "
            f"Whisper detects={det}, output script={main_script(rec.get('raw', ''))}")


def transcribe_all(job: dict) -> int:
    """job = {entry, api, todo: [[path, abs_path, duration], ...], out_dir, fingerprint, label}"""
    from . import models

    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    tpath = out_dir / "transcripts.jsonl"
    todo, label = job["todo"], job["label"]
    done = failed = 0
    with PeakRSS() as mem:
        t0 = time.perf_counter()
        model = models.load(job["entry"], job["api"])
        load_s = time.perf_counter() - t0
        print(f"[{label}] model loaded in {load_s:.1f}s; transcribing {len(todo)} clips", flush=True)
        if hasattr(model, "describe"):
            print(f"[{label}] settings: {model.describe()}", flush=True)
        with open(tpath, "a", encoding="utf-8") as f:
            for i, (path, abs_path, dur) in enumerate(todo, 1):
                rec = {"path": path, "fingerprint": job["fingerprint"], "audio_seconds": dur}
                t = time.perf_counter()
                try:
                    rec["raw"] = model.transcribe(abs_path)
                    rec["seconds"] = time.perf_counter() - t
                    done += 1
                    li = getattr(model, "last_info", None)
                    if li:
                        rec.update(li)
                        print(f"[{label}] {path}: {language_line(rec)}", flush=True)
                except Exception as e:  # noqa: BLE001
                    rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                    failed += 1
                    print(f"[{label}] {path}: FAILED {rec['error']}", file=sys.stderr, flush=True)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                if i % 10 == 0 or i == len(todo):
                    print(f"[{label}] {i}/{len(todo)}", flush=True)
    with open(out_dir / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "fingerprint": job["fingerprint"],
                            "transcribed": done, "failed": failed, "load_seconds": round(load_s, 2),
                            "peak_ram_mb": round(mem.mb(), 1), "pid": os.getpid()}) + "\n")
    return 0


def _child(job):
    sys.exit(transcribe_all(job))


def run_job(job: dict, isolate: bool = True) -> int:
    if not isolate:
        return transcribe_all(job)
    import multiprocessing as mp
    p = mp.get_context("spawn").Process(target=_child, args=(job,))
    p.start()
    try:
        p.join()
    except KeyboardInterrupt:
        p.terminate()
        p.join()
        raise
    return p.exitcode
