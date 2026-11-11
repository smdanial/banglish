# Handover

## Task C3: dataset quality check and speaker-based splits
All files are in `data-collector/`.

### What was built
- `scripts/qc_dataset.py` → `reports/qc_report.md` and `reports/flagged.csv`.
  - **Per-clip checks:** duration (<1 s or >20 s), mostly silence (>70%), no speech, clipping (20+ samples at full scale), low volume (speech < -35 dBFS), leading silence >1.5 s, possible cut-off at the end, wrong format.
  - **Text checks:** empty `actual_text`, Bengali script, unusual characters (emoji/symbols), big difference from the prompt (>50% of words changed). Clips where the text was left as the prompt are counted per speaker.
  - **Duplicates:** same speaker and prompt recorded twice; byte-identical audio.
  - **Summaries:** per-speaker and per-category tables, and a plain-language "Problems to fix" list at the top. Each flagged clip gets a `suggested_action`: remove, fix text or listen.
- `scripts/make_splits.py`: reads `docs/SPLITS.md` (or a `.yaml` file) and splits by speaker only. It refuses to run if a speaker is listed in both test and dev. It writes `splits.json` (speakers, clip paths, summary), prints clips, speakers and minutes per split and per category, and warns when a category has fewer than 15 test clips. `--exclude flagged.csv` leaves out clips marked "remove".
- `export_dataset.py`: `manifest.csv` now has extra columns after the six required ones: `prompt_id, phone_model, age_range, region, recording_id, created_at`. The QC per-speaker table needs `phone_model`. Duplicate takes are matched on `prompt_id`. Manifests without these columns still work: the phone model shows as "-", and duplicates are matched on prompt text.
- `tests/make_sample_data.py` creates a synthetic dataset (beeps, no real voices) in `tests/sample_data/`: 8 speakers, 91 clips, with 15 planted problems. `tests/test_qc_and_splits.py` has 6 unit tests. Audio, `reports/` and `splits.json` are git-ignored.

### Verified (by Devin, on the synthetic sample)
- `python3 -m unittest discover -s tests` passes 6/6. QC finds all 15 planted problem types and flags no clean clips. A speaker listed in both test and dev stops `make_splits.py` with no output. Every speaker ends up in exactly one split. Clips marked "remove" are excluded. The fewer-than-15-test-clips warning fires.
- Both scripts run end to end on `tests/sample_data/`, producing `qc_report.md`, `flagged.csv` and `splits.json`.

### NOT verified
- **Real recordings.** The thresholds were tuned on synthetic beeps, not real phone audio. Expect some false alarms, especially for `mostly_silence`, `cut_off` and `low_volume`. Read the first real report with that in mind and change the constants at the top of `qc_dataset.py` if needed.
- The changed `export_dataset.py` has not been run against Supabase again: it only adds manifest columns, and no Supabase project was available. Older manifests without the new columns still work with both scripts.
- Speed on a large dataset. The checks use numpy and should take seconds per few hundred clips, but this hasn't been measured on hours of audio.
- Opening `flagged.csv` in Excel: it is written as UTF-8 with a BOM so Excel should show Bengali text, but this was not checked in Excel itself.

---

## Task C1: Banglish speech collection page

### What was built
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

### Verified (by Devin, in the dev VM)
- **SQL + RLS** on a local Supabase stack (Supabase CLI 3.0 / Docker), with both key styles (legacy `anon`/`service_role` JWTs and new `sb_publishable_`/`sb_secret_`): `scripts/check_setup.py` → ALL PASS: public key can upload + insert; can NOT read rows, edit rows, delete rows, download audio, use a public URL, list files, delete files or overwrite files; admin key can read/download. `setup.sql` is re-runnable.
- **End-to-end UI** with Playwright (headless Chromium, fake microphone) at 393×851 (Pixel 5), 360×740 and 320×568, the last two with 6× CPU throttling and ~400 kbps / 300 ms network: Continue disabled until "I agree"; microphone NOT requested before consent; profile saved; Skip changes prompt without counting; record → stop → re-record → play → edit text → submit ×3; counter goes 0/50 → 3/50; reload keeps consent, speaker_id and profile; "new speaker" resets to consent with a new id; no horizontal overflow; no JS errors. Each run produced exactly 3 rows + 3 files per speaker in local Supabase, with correct speaker info, edited `actual_text`, `audio/webm;codecs=opus`.
- **Export**: `export_dataset.py` downloaded all files from local Supabase, converted to `pcm_s16le, 16000 Hz, 1 channel`, wrote `manifest.csv` with the required columns; re-run skips existing files.
- **Build**: fails clearly when env vars are missing and when an admin key is given as the public key.
- Page weight: app.js ≈13 KB (≈5 KB gzipped), CSS ≈3 KB, HTML ≈5 KB, prompts.json ≈30 KB (≈7 KB gzipped). Page usable in ~2.5 s on the throttled profile.

### NOT verified (needs you / real devices)
- **The hosted setup**: no real Supabase project, Vercel or Cloudflare account was available to Devin, so the DONE criterion (deployed URL → phone → 3 rows + 3 files in Supabase) has not been run. Follow `docs/SUPABASE_SETUP.md`, then `docs/DEPLOY.md`, then run `python3 scripts/check_setup.py` against the real project.
- **Real phones**: tested in emulated mobile Chromium only. Not tested on a physical Android phone, on **iPhone Safari** (records `audio/mp4` → saved as `.m4a`; allowed in the bucket and handled by the export via ffmpeg, but untested), or inside WhatsApp/Facebook in-app browsers (mic often blocked there → users should "Open in Chrome").
- Dashboard click-paths in the docs were written from Supabase/Vercel/Cloudflare docs and may differ slightly as their UIs change.
- Supabase free-tier limits (1 GB storage, project pause after 7 days of inactivity) – not load-tested.
- Prompts were written by Devin; a native speaker should skim `data/prompts.json` for unnatural phrasing/spelling.

### Known limitations / ideas
- No offline queue: if upload fails, the user sees an error and taps Submit again (the take is kept).
- The public insert-only key could still be abused to upload junk (spam). Mitigations if needed: Supabase rate limits, a Cloudflare Turnstile check via one serverless function, or periodic review.
- If audio upload succeeds but the row insert fails, an orphan audio file remains (harmless; export only uses rows).
