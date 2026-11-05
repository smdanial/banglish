# Deploying the page (free, HTTPS)

Browsers only allow the microphone on **https://** pages, so the site must be hosted. Both options below are free and give you an https link. Pick **one**. You need the repo on GitHub and the two public values from [SUPABASE_SETUP.md](SUPABASE_SETUP.md) (`SUPABASE_URL`, `SUPABASE_ANON_KEY`).

All files for the page live in the **`data-collector/`** folder of the repo, so the host must be told to use that folder as its root (steps below).

There is no server to run: the host runs `npm run build` (which writes `public/config.js` from your environment variables and copies `data/prompts.json`) and then serves the `public/` folder.

## Option A – Vercel (recommended)
1. Go to <https://vercel.com/signup> and **Continue with GitHub**. Choose the free **Hobby** plan.
2. Click **Add New… → Project**.
3. Find **banglish** in the list and click **Import**. (If it's missing: **Adjust GitHub App Permissions** → give Vercel access to the repo.)
4. On the configure screen:
   - **Project Name:** `banglish-voice` (this becomes the link name).
   - **Root Directory:** click **Edit** and choose **`data-collector`**. (Important: without this the build fails.)
   - **Framework Preset:** `Other` (build settings come from `vercel.json` automatically: build command `npm run build`, output directory `public`).
   - Open **Environment Variables** and add:
     | Key | Value |
     |---|---|
     | `SUPABASE_URL` | your Project URL |
     | `SUPABASE_ANON_KEY` | your publishable / anon public key |
     | `CONTACT_TEXT` (optional) | e.g. `voice-project@example.com` – shown on the consent screen |
     | `SESSION_GOAL` (optional) | number of sentences per session, default `50` |
   - **Do not** add the service_role / secret key here.
5. Click **Deploy**. After about 30 seconds you get a link like `https://banglish-voice.vercel.app`. Open it on your phone.

Notes:
- Vercel deploys **`main`** as the public (production) link. Until the PR is merged, the `task-C1` branch gets a *Preview* link (shown on the PR and in Vercel → Deployments). Preview links are protected by Vercel login by default — fine for your own test, but for volunteers either merge to `main` or turn off **Settings → Deployment Protection → Vercel Authentication**.
- If you change an environment variable later: **Deployments → ⋯ → Redeploy**.
- If the build log says `BUILD FAILED: SUPABASE_URL is not set`, the environment variables are missing or were only added for one environment (Production/Preview) – add them for both and redeploy.

## Option B – Cloudflare Pages
1. Go to <https://dash.cloudflare.com/sign-up> and create a free account.
2. Sidebar: **Workers & Pages → Create → Pages → Connect to Git**. (If you only see Workers options, look for the **Pages** tab / "Looking to deploy Pages? Get started".)
3. Authorize GitHub, choose **banglish**, click **Begin setup**.
4. Settings:
   - **Project name:** `banglish-voice`
   - **Production branch:** `main`
   - **Framework preset:** `None`
   - **Build command:** `npm run build`
   - **Build output directory:** `public`
   - **Root directory (advanced):** `data-collector`
   - **Environment variables:** add `SUPABASE_URL` and `SUPABASE_ANON_KEY` (and optionally `CONTACT_TEXT`, `SESSION_GOAL`).
5. **Save and Deploy**. Your link looks like `https://banglish-voice.pages.dev`. Other branches (like `task-C1`) get preview links such as `https://task-c1.banglish-voice.pages.dev`.
6. Changing a variable later: **Settings → Environment variables**, then **Deployments → Retry deployment**.

## After deploying – 2-minute check on your phone
1. Open the link in **Chrome (Android)** or **Safari (iPhone)**.
2. Tick **I agree**, tap **Continue**, optionally fill in your details, tap **Start recording**.
3. Allow the microphone when asked. Tap **Record**, read the sentence, tap **Stop**, tap **Play** to listen, then **Submit & next**. Do this 3 times.
4. In Supabase: **Table Editor → recordings** shows 3 rows; **Storage → recordings → spk_…** shows 3 audio files.
