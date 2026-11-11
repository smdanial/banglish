# RUN_ME notes (laptop run guide)

## What was added
- `RUN_ME.md` (repo root): 8-step copy-paste guide for a non-coder on Ubuntu without GPU: clone → setup → admin key as env var → export → QC → splits → formatter tests → benchmark (test split, tiny/base/small, `--quick` first) → what to send back.
- `requirements.txt` (root): one environment for everything (`-r eval/requirements.txt`, `-r formatter/requirements.txt`, `numpy`). The exporter itself needs only the standard library + ffmpeg.
- `setup.sh` (root): checks python3/venv/ffmpeg/git (prints the `apt install` line if something is missing, never runs sudo), creates `.venv/`, installs `requirements.txt`, imports the key packages, prints `Setup OK`. Re-runnable.
- `eval/run.py --quick`: same as `--limit 30` (summary says `(--quick)`). Test: `test_quick_limits_to_30_clips` in `eval/tests/test_run.py`.
- `eval/requirements.txt`: `av<19`. PyAV 19 removed `av.open(metadata_errors=...)`, which faster-whisper 1.2.1 still passes, so every clip failed with `TypeError` on a fresh Python 3.12 install (3.10 resolves av 17, so the dev VM never saw it). av 17.1 and 18.1 verified OK.
- `.gitignore`: added `.venv/`, `venv/`, `dataset/`, `banglish-data/`, `reports/`, `results/` anywhere in the repo.

## Decisions
- All private outputs go to `~/banglish-data/` (dataset/, reports/, splits.json, results/), outside the repo, via the scripts' existing `--out` / `--output` flags. So "results/summary.md" in the task = `~/banglish-data/results/summary.md`.
- Admin key: entered with `read -rsp` + `export` (not echoed, not in shell history, gone when the terminal closes). The guide also checks that no old key is left in `data-collector/.env`. Env vars win over `.env` in `sbhttp.load_dotenv`.
- Benchmark runs without a Gemini key, so the offline `rules` romanizer is used and no transcript text leaves the laptop.
- `qc_report.md` and `summary.md` were checked by reading `qc_dataset.build_report` and `eval/report.write_summary`: they contain aggregates, speaker ids, phone models, machine info and the data folder path; no transcripts, audio or keys. Per-clip text lives only in `flagged.csv`, `results/<model>/*.csv|jsonl` (marked "don't send").
- HANDOVER.md not edited (as asked).

## Verified (Devin VM: 8-core x86, 31 GB RAM, no GPU)
- Fresh clone → `./setup.sh` → `Setup OK` (Python 3.10, .venv 563 MB). Also a fresh Python 3.12 venv from `requirements.txt` (after the `av<19` pin).
- End to end against a **local** Supabase (`supabase start` + `data-collector/supabase/setup.sql`), filled with 60 gTTS clips uploaded as webm/opus with the anon key like the phone page does (5 speakers, incl. the 3 test speakers in `data-collector/docs/SPLITS.md`): export with the key only in an env var → 60 WAVs in `~/banglish-data/dataset`; QC → 4 flagged (duplicate audio, an artefact of the fake data); splits → test 36 clips / 3 speakers; formatter `125 passed`; `--quick` → 30 clips × 3 models; full run reuses those 30 and does the remaining 6. Wrong key → HTTP 401 message; no key → "Missing environment variable" message (both quoted in RUN_ME).
- `git status` in the clone stayed clean through all steps; `git check-ignore` confirms `.env`, `.env.*`, every audio extension, `dataset/`, `banglish-data/`, `reports/`, `results/`, `eval/results/`, `eval/cache/`, `splits.json` (data-collector) and `.venv/` are ignored, while `data-collector/.env.example` and `eval/sample/splits.json` stay tracked.
- Tests: `eval/tests` 39 passed, `formatter` 125 passed, `data-collector` unittest OK.
- Speed/RAM (36 test clips, ~4.8 s each, transcription time only, restricted with `taskset`):

  | Model | 4 cores: per 100 clips | 2 cores: per 100 clips | Peak RAM |
  |---|---|---|---|
  | tiny | 1.4 min | 2.0 min | 0.31-0.35 GB |
  | base | 1.1 min | 2.0 min | 0.46-0.53 GB |
  | small | 3.0 min | 5.9 min | 0.82-1.03 GB |

## NOT verified
- A real Supabase project and real phone recordings (only local Supabase + TTS audio).
- A real Ubuntu laptop: `apt install` line, `xdg-open`, file-manager steps, and real laptop CPU speed (numbers above are from a server CPU limited to 2/4 cores; RUN_ME says "up to 2x slower").
- The Supabase dashboard click path for the key was taken from `data-collector/docs/SUPABASE_SETUP.md`, not re-checked in the dashboard.
