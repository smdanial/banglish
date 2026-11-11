# Handover – Task B2: speech model evaluation harness

## What was built
Everything lives in [`eval/`](eval/); how to run it on real data is in [`eval/README.md`](eval/README.md) (7 steps).

- `python -m eval.run --config eval/config.yaml [--data DIR] [--splits splits.json] [--split test] [--models a,b] [--output DIR] [--limit N]`.
- Input: export folder with `manifest.csv` (`path, speaker_id, prompt_text, actual_text, category, duration`) + 16 kHz mono WAVs. With `--splits`, only the chosen split (default `test`) is evaluated; without it every clip is evaluated and `summary.md` says so in bold.
- Models (`eval/config.yaml`): faster-whisper tiny/base/small/medium (CPU, int8, `language: bn`), large-v3 (in config, `enabled: false`), Gemini via the OpenAI-compatible endpoint (`GEMINI_API_KEY`/`GOOGLE_API_KEY`, model from `GEMINI_MODEL`, default `gemini-2.5-flash`), and a plug-in interface (`eval/plugins/example_plugin.py`: one function `transcribe(path) -> text`).
- Romanizer: Whisper output in a non-Latin script is converted to Banglish before scoring. Default = LLM (Gemini) with an on-disk cache (`eval/cache/`); falls back to a rule-based transliterator when no key is set. Such models are labelled e.g. `whisper-small + romanizer (llm:gemini-2.5-flash)` / `+ romanizer (rules)`; raw model output and romanized text are both kept in `results/<model>/hypotheses.csv`.
- Normalization (both sides): lowercase, strip punctuation, collapse spaces, spelling-variant map in `eval/normalization.yaml` (extend it freely). Number/time words (`char tay`, `sharhe 5`, `18 hajar`, Bengali digits, phone numbers) are turned into digits for key-field matching.
- Metrics per model, overall and per category: WER, CER (jiwer), key-field accuracy (% of utterances whose reference contains numbers/times where ALL of them match exactly), seconds per audio second, peak RAM (each model runs in its own process). Output: `results/summary.md`, `results/<model>/worst.csv` (20 worst), `hypotheses.csv`, resumable `transcripts.jsonl`.
- Synthetic sample: `eval/sample/` (12 clips, 3 fake speakers, 9 categories, with `splits.json`). Only the texts and generator are committed; the WAVs are generated on first run (Google TTS Bengali voice, offline fallbacks espeak-ng → tones) and gitignored.
- Privacy: `*.wav` and other audio, `eval/results/`, `eval/cache/`, `.env` are gitignored. API keys are never printed.

### Deviations / decisions
- Results go to `eval/results/` (not repo-root `results/`), next to the harness, and are gitignored because on real data they contain private transcripts.
- `make_splits.py` does not exist yet, so `splits.json` is read in several shapes: `{"test": [clip paths or speaker_ids]}`, `{"splits": {...}}`, `{"test": {"speakers": [...]}}`, or `{"<clip path>": "test"}`. **Check this when make_splits.py is written.**
- Key-field accuracy is computed only over utterances whose reference contains a number/time (the summary shows the count, e.g. `2/7`); a hypothesis that adds numbers the reference lacks is not penalised by this metric (WER catches it).
- Whisper with `language="bn"` on the synthetic audio often wrote Devanagari, Urdu/Arabic or even Telugu script instead of Bengali, so the romanizer handles any non-Latin script; the rules fallback only knows Bengali and Devanagari. `summary.md` lists the raw-output scripts per model and how many outputs stayed non-Latin.

## Verified (by Devin, in the dev VM: 8-core x86 CPU, no GPU, Python 3.10)
- `python -m pytest eval/tests` → 37 passed (normalization, number/time extraction, romanizer + cache, manifest/WAV checks, all splits shapes, end-to-end run with a fake plug-in, resume).
- `python -m eval.run --config eval/config.yaml` on `eval/sample` end to end with whisper tiny/base/small/medium → `eval/results/summary.md` + per-model `worst.csv` (~9 min first run incl. model downloads, <1 s re-run).
- `--splits eval/sample/splits.json` → evaluates only the 8 test clips / 2 speakers; without it → all 12 clips and the "evaluated ALL clips" notice.
- Resume: run interrupted with Ctrl-C after 7/12 clips; re-run transcribed only the remaining 5.
- Measured on this VM (synthetic sample): speed tiny 0.15, base 0.13, small 0.6, medium 6.4 s per audio second; peak RAM tiny 0.34 GB, base 0.44 GB, small 1.0 GB, medium 4.0 GB.

## NOT verified (needs you)
- **Gemini** (both as a model and as the LLM romanizer): no API key on the VM, so it was skipped and the rules romanizer was used. The request format follows Google's OpenAI-compatibility docs (`input_audio`, base64 WAV) but was never sent for real. First thing to check on your laptop: add the key to `.env`, run `--models gemini --limit 3`.
- **Real recordings**: never seen by Devin. The sample WER/key-field numbers are from robotic TTS audio and say nothing about which model is best — do not use them for decision G1.
- large-v3 (not run; disabled by default).
- Your laptop: speed/RAM will differ from the VM; Windows/Mac paths not tested (only Linux).
- The rules romanizer is approximate (e.g. inherent-vowel guessing); WER for "+ romanizer (rules)" rows includes its errors. Prefer the LLM romanizer for real numbers.

---

# Handover – Task C1 (previous task): Banglish speech collection page

## What was built
All C1 files live in [`data-collector/`](data-collector/); paths below are relative to that folder.

- `public/` static page: consent (EN + BN, "I agree" gate) → optional speaker info (age range, district dropdown, phone model, random `speaker_id` in localStorage) → one prompt at a time with Record/Stop (MediaRecorder), Play, Re-record, editable "What you actually said", Submit, Skip, progress counter `n/50`, thank-you screen.
- `data/prompts.json`: 300 Banglish sentences, 5–15 words each, 11 categories (27–28 each), ids `p001`–`p300`.
- `supabase/setup.sql`: `recordings` table, private `recordings` bucket (10 MB, audio MIME types only), RLS: anon may INSERT rows / upload objects only.
- `scripts/build.mjs` (env → `public/config.js`), `scripts/export_dataset.py`, `scripts/check_setup.py`.
- Docs: `README.md`, `docs/SUPABASE_SETUP.md`, `docs/DEPLOY.md`, `.env.example`, `vercel.json`, `public/_headers` (Cloudflare).

### Deviations / additions to the spec (deliberate)
- Table has extra nullable columns `category`, `age_range`, `region`, `phone_model` (spec asked for the speaker info but listed no columns for it).
- "Someone else using this phone?" button on the profile screen → new speaker_id + consent again (shared phones are common).
- Recording auto-stops at 30 s; recordings shorter than 0.6 s are rejected client-side.
- Mic is opened with `echoCancellation:false, noiseSuppression:false` (rawer audio is better for ASR training); `autoGainControl` on.
- Age range includes "Under 18". **Decision for you:** if minors should not take part (consent from a minor is legally weak), remove that option and add "I am 18 or older" to the consent text.

## Verified (by Devin, in the dev VM)
- **SQL + RLS** on a local Supabase stack (Supabase CLI 3.0 / Docker), with both key styles (legacy `anon`/`service_role` JWTs and new `sb_publishable_`/`sb_secret_`): `scripts/check_setup.py` → ALL PASS: public key can upload + insert; can NOT read rows, edit rows, delete rows, download audio, use a public URL, list files, delete files or overwrite files; admin key can read/download. `setup.sql` is re-runnable.
- **End-to-end UI** with Playwright (headless Chromium, fake microphone) at 393×851 (Pixel 5), 360×740 and 320×568, the last two with 6× CPU throttling and ~400 kbps / 300 ms network: Continue disabled until "I agree"; microphone NOT requested before consent; profile saved; Skip changes prompt without counting; record → stop → re-record → play → edit text → submit ×3; counter goes 0/50 → 3/50; reload keeps consent, speaker_id and profile; "new speaker" resets to consent with a new id; no horizontal overflow; no JS errors. Each run produced exactly 3 rows + 3 files per speaker in local Supabase, with correct speaker info, edited `actual_text`, `audio/webm;codecs=opus`.
- **Export**: `export_dataset.py` downloaded all files from local Supabase, converted to `pcm_s16le, 16000 Hz, 1 channel`, wrote `manifest.csv` with the required columns; re-run skips existing files.
- **Build**: fails clearly when env vars are missing and when an admin key is given as the public key.
- Page weight: app.js ≈13 KB (≈5 KB gzipped), CSS ≈3 KB, HTML ≈5 KB, prompts.json ≈30 KB (≈7 KB gzipped). Page usable in ~2.5 s on the throttled profile.

## NOT verified (needs you / real devices)
- **The hosted setup**: no real Supabase project, Vercel or Cloudflare account was available to Devin, so the DONE criterion (deployed URL → phone → 3 rows + 3 files in Supabase) has not been run. Follow `docs/SUPABASE_SETUP.md`, then `docs/DEPLOY.md`, then run `python3 scripts/check_setup.py` against the real project.
- **Real phones**: tested in emulated mobile Chromium only. Not tested on a physical Android phone, on **iPhone Safari** (records `audio/mp4` → saved as `.m4a`; allowed in the bucket and handled by the export via ffmpeg, but untested), or inside WhatsApp/Facebook in-app browsers (mic often blocked there → users should "Open in Chrome").
- Dashboard click-paths in the docs were written from Supabase/Vercel/Cloudflare docs and may differ slightly as their UIs change.
- Supabase free-tier limits (1 GB storage, project pause after 7 days of inactivity) – not load-tested.
- Prompts were written by Devin; a native speaker should skim `data/prompts.json` for unnatural phrasing/spelling.

## Known limitations / ideas
- No offline queue: if upload fails, the user sees an error and taps Submit again (the take is kept).
- The public insert-only key could still be abused to upload junk (spam). Mitigations if needed: Supabase rate limits, a Cloudflare Turnstile check via one serverless function, or periodic review.
- If audio upload succeeds but the row insert fails, an orphan audio file remains (harmless; export only uses rows).
