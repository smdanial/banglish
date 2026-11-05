# Supabase setup (step by step, no coding needed)

Takes about 10 minutes. Supabase's free tier is enough to start (500 MB database, 1 GB file storage).
A 5-second recording is about 40–60 KB, so 1 GB holds roughly 15,000–20,000 recordings.

## 1. Create a project
1. Go to <https://supabase.com> and click **Start your project**. Sign in (GitHub or email).
2. Click **New project**.
3. Fill in:
   - **Name:** `banglish-voice`
   - **Database password:** click **Generate a password** and save it in your password manager (you won't need it for this app, but keep it).
   - **Region:** pick the closest one to your volunteers, e.g. **Southeast Asia (Singapore)** or **South Asia (Mumbai)**.
4. Click **Create new project** and wait 1–2 minutes until the dashboard is ready.

## 2. Create the table, the storage bucket and the security rules (one SQL paste)
1. In the left sidebar, open **SQL Editor**.
2. Click **New query** (or the **+** button).
3. Open the file [`supabase/setup.sql`](../supabase/setup.sql) from this repo, copy **everything**, and paste it into the editor.
4. Click **Run** (bottom right) or press Ctrl+Enter / Cmd+Enter.
5. You should see **Success. No rows returned.** If Supabase shows a warning about "destructive operations", click **Run this query** — the script only drops and recreates its own two security rules.

This creates:
- a table **`recordings`** (Table Editor → `recordings`) with the columns: id, speaker_id, prompt_id, prompt_text, actual_text, audio_path, duration_sec, mime_type, user_agent, created_at, consent_version, plus the optional speaker info (age_range, region, phone_model) and the prompt category;
- a **private** storage bucket called **`recordings`** (Storage → `recordings`), max 10 MB per file, audio files only;
- **row-level security** rules: the public key can only **add** new rows and upload new audio. It cannot read, list, download, change or delete anything.

You can run the script again at any time; it will not delete data.

> Prefer clicking instead of SQL for the bucket? Storage → **New bucket** → name `recordings`, leave **Public bucket OFF** → Save. You still need to run the SQL for the table and the rules.

## 3. Copy your keys
1. Click **Project Settings** (gear icon at the bottom of the sidebar) → **API Keys**. (On some accounts it is **Settings → API**.)
2. You need three values:
   | Name in this repo | Where to find it | Secret? |
   |---|---|---|
   | `SUPABASE_URL` | **Project URL** (Settings → Data API, or the **Connect** button at the top), looks like `https://abcd1234.supabase.co` | no |
   | `SUPABASE_ANON_KEY` | **Publishable key** (`sb_publishable_...`) or, under **Legacy API keys**, the **anon public** key (`eyJ...`) | no – it is meant for the browser |
   | `SUPABASE_SERVICE_ROLE_KEY` | **Secret key** (`sb_secret_...`) or, under **Legacy API keys**, **service_role** (`eyJ...`) | **YES – keep private** |
3. The public key goes into the website (Vercel/Cloudflare). The **secret/service_role key never goes into the website** — only into the `.env` file on your own computer for the export script. The site build refuses to start if you paste the admin key by mistake.

## 4. (Recommended) Check the security rules
On your computer, in the repo's `data-collector` folder (needs Python 3):
```bash
cd data-collector
cp .env.example .env      # then open .env and paste the three values
python3 scripts/check_setup.py
```
You should see a list of `[PASS]` lines ending in **ALL GOOD**. It uploads one tiny test file and row with the public key, confirms the public key cannot read/list/download/change/delete them, then (using the admin key) confirms they exist and deletes them.

## 5. Where to look at the data
- **Rows:** Table Editor → `recordings`.
- **Audio files:** Storage → `recordings` → one folder per speaker (`spk_...`). Click a file → **Download** to listen.
- **Everything at once:** run `python3 scripts/export_dataset.py` (see the README).

## Troubleshooting
- **"permission denied for table recordings" or 401/403 when submitting:** the SQL in step 2 didn't run completely. Run it again and check for errors.
- **"Bucket not found":** the bucket name must be exactly `recordings` (or set `SUPABASE_BUCKET` everywhere to your name and change it in the SQL).
- **"mime type not supported":** the phone recorded in a format not in the allowed list; add it to `allowed_mime_types` in `supabase/setup.sql` and re-run.
- **Free projects pause after 7 days with no activity.** If the site suddenly can't save, open the Supabase dashboard and click **Restore project**.
