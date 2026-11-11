# banglish
Banglish voice input for keyboards. See [PLAN.md](PLAN.md) for the work plan and [HANDOVER.md](HANDOVER.md) for the latest status.

## Speech data collector (Task C1)

[`data-collector/`](data-collector/) is a mobile web page that volunteers open on their phones to record Banglish sentences. It shows a consent notice (English + Bangla), then one prompt at a time with Record / Play / Re-record, a "What you actually said" box, Submit and Skip. Audio and metadata go to Supabase (free tier); the public key can only insert.

### Setup (once)
1. **Supabase:** follow [data-collector/docs/SUPABASE_SETUP.md](data-collector/docs/SUPABASE_SETUP.md): create the project, run `data-collector/supabase/setup.sql`, copy the keys.
2. **Deploy:** follow [data-collector/docs/DEPLOY.md](data-collector/docs/DEPLOY.md) (Vercel or Cloudflare Pages, root directory `data-collector`). Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` as environment variables on the host. Never put the admin key there.
3. **Check:** open the link on your phone, record 3 sentences, and confirm 3 rows (Table Editor → `recordings`) and 3 files (Storage → `recordings`).

### Sharing the link with volunteers
Send the **production** https link (not a Vercel preview link). Ask people to open it in Chrome (Android) or Safari (iPhone), not inside WhatsApp/Facebook, and to record somewhere quiet on their own phone. A ready-to-send English + Bangla message and more tips are in [data-collector/README.md](data-collector/README.md#sharing-the-link-with-volunteers).

### Exporting the data
`python3 data-collector/scripts/export_dataset.py` (needs ffmpeg and the admin key in `data-collector/.env`) writes 16 kHz mono WAVs and `manifest.csv`. Details: [data-collector/README.md](data-collector/README.md#exporting-the-dataset).

## Dataset quality check and splits (Task C3)

Run these on your laptop after exporting. They need Python 3 and ffmpeg (for the export only):
```bash
cd data-collector && pip install numpy
python3 scripts/export_dataset.py                       # skip if dataset/ is already exported
python3 scripts/qc_dataset.py --dataset dataset         # read reports/qc_report.md, then flagged.csv
# list your test and dev speaker_ids in docs/SPLITS.md, then:
python3 scripts/make_splits.py --dataset dataset --exclude reports/flagged.csv   # writes splits.json
```
If your exported folder is somewhere else, replace `dataset` with its path. For details, see [data-collector/README.md](data-collector/README.md#quality-check-and-traindevtest-splits).
