# RUN ME: export, check and benchmark the recordings on your Ubuntu laptop

For: an Ubuntu laptop (22.04 or 24.04) with no GPU. You only copy and paste. Do the steps in order.

How to use this guide:
- Open a terminal: press **Ctrl + Alt + T**.
- Copy a grey box, click in the terminal, paste with **Ctrl + Shift + V** (plain Ctrl + V does not work in the terminal), press **Enter**.
- Wait until the terminal shows the prompt (`...$`) again before pasting the next box.
- Your numbers (clip counts, minutes, times) will differ from the "Expected output" examples. Those examples come from a test run with 60 fake recordings.
- All private data goes in one folder **outside** the repo: `~/banglish-data` (`~` = your home folder). Audio, transcripts and results never sit inside the repo, so they cannot be committed by accident.

---

## 1. Get the code and set up Python (once, about 10 minutes)

**1a. Install the system tools.** Asks for your laptop password. Nothing shows while you type it; that is normal.
```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip ffmpeg
```
Expected output: many lines, ending with something like `Setting up ffmpeg ...` or `ffmpeg is already the newest version`. No line starting with `E:`.

**1b. Download the repo.** First time:
```bash
cd ~ && git clone https://github.com/smdanial/banglish.git && cd ~/banglish
```
Expected output:
```
Cloning into 'banglish'...
...
Resolving deltas: 100% (...), done.
```
Already downloaded it before? Get the latest version instead:
```bash
cd ~/banglish && git checkout main && git pull
```
Expected output: `Already up to date.` or a list of changed files.

**1c. Create the Python environment.** One environment (`~/banglish/.venv`) for the exporter, QC, splits, benchmark and formatter tests:
```bash
cd ~/banglish && ./setup.sh
```
Expected output (takes 2-10 minutes the first time and downloads about 600 MB; your version numbers may differ):
```
Creating .venv ...
Installing Python packages (first time: 2-10 minutes, about 600 MB) ...
Python 3.12.3, numpy 2.5.4, faster-whisper 1.2.1
Setup OK. Before running anything, type:  source .venv/bin/activate
```
If it says `Missing system packages`, run step 1a again, then `./setup.sh` again.

**1d. Turn the environment on.** Do this **every time you open a new terminal**:
```bash
cd ~/banglish && source .venv/bin/activate
```
Expected output: nothing, but the prompt now starts with `(.venv)`. All commands below assume you are in `~/banglish` with `(.venv)` showing.

---

## 2. Give the export script the Supabase admin key (every new terminal)

The admin key can read and delete all recordings, so it is **never** saved in a file. You type it into the terminal, and it is forgotten when you close the terminal window.

**Where to find it:** open https://supabase.com/dashboard, click your project, then **Project Settings** (gear icon, bottom of the left sidebar) → **API Keys**.
- Admin key: the **Secret key** (starts with `sb_secret_`). Click the eye/copy icon next to it. On older projects use the **Legacy API keys** tab → **service_role** → **Reveal** → copy (starts with `eyJ`).
- Project URL: **Project Settings → Data API** (or the **Connect** button at the top). It looks like `https://abcd1234.supabase.co`.

Do **not** use the "publishable" or "anon" key: it can only add recordings, not read them.

**2a.** Set the project URL. Replace `abcd1234` with your project's code before pressing Enter:
```bash
export SUPABASE_URL=https://abcd1234.supabase.co
```
Expected output: nothing.

**2b.** Set the admin key. Paste this box, press Enter, then paste the key (Ctrl + Shift + V) and press Enter again. **Nothing appears while you paste the key**: that is on purpose, so it is never shown on screen or saved in your terminal history.
```bash
read -rsp "Paste the admin key, then press Enter: " SUPABASE_SERVICE_ROLE_KEY && export SUPABASE_SERVICE_ROLE_KEY && echo && echo "Key set (${#SUPABASE_SERVICE_ROLE_KEY} characters)"
```
Expected output:
```
Paste the admin key, then press Enter:
Key set (41 characters)
```
A `sb_secret_` key is about 41 characters long; an old `eyJ` key is about 200. `Key set (0 characters)` means nothing was pasted: run 2b again.

**2c.** Make sure no old copy of the key is lying in a file in the repo (older instructions said to put it in `data-collector/.env`):
```bash
grep -sq "^SUPABASE_SERVICE_ROLE_KEY=." data-collector/.env && echo "WARNING: admin key found in data-collector/.env - open that file and delete the key after the = sign" || echo "OK: no admin key in the repo"
```
Expected output: `OK: no admin key in the repo`

---

## 3. Export the dataset to ~/banglish-data (outside the repo)

Downloads every recording and converts it to 16 kHz mono WAV. Run it in the same terminal as step 2.
```bash
mkdir -p ~/banglish-data && python data-collector/scripts/export_dataset.py --out ~/banglish-data/dataset
```
Expected output (about 1 second per recording, depending on your internet):
```
60 rows in the recordings table
  50/60
Done: 60 clips in manifest (60 newly converted, 0 failed) -> /home/YOU/banglish-data/dataset/manifest.csv
```
Result: `~/banglish-data/dataset/manifest.csv` plus `~/banglish-data/dataset/wavs/*.wav`.
- Running it again later only downloads the new recordings.
- `Missing environment variable: SUPABASE_SERVICE_ROLE_KEY` → this terminal doesn't have the key: do step 2 again.
- `Could not read the recordings table (HTTP 401)` → wrong key (probably the publishable/anon key) or wrong URL: do step 2 again with the **Secret** key.
- `... failed` greater than 0 → run the same command again; if it still fails, send me the lines that say `download failed` or `ffmpeg failed` (they only contain file names, no audio).

---

## 4. Quality check

```bash
python data-collector/scripts/qc_dataset.py --dataset ~/banglish-data/dataset --out ~/banglish-data/reports
```
Expected output:
```
Checked 60 clips: 4 flagged.
Report:  /home/YOU/banglish-data/reports/qc_report.md
Flagged: /home/YOU/banglish-data/reports/flagged.csv
```
**Open this file first:** `~/banglish-data/reports/qc_report.md`
```bash
xdg-open ~/banglish-data/reports/qc_report.md
```
It opens in the text editor. Read the **Problems to fix** list at the top, and the **Per speaker** table (you use it to choose test speakers in step 5).

Then, to see the individual clips, open `flagged.csv` (opens in LibreOffice Calc; pick "UTF-8" and "comma" if it asks):
```bash
xdg-open ~/banglish-data/reports/flagged.csv
```
`suggested_action` says **remove**, **fix text** or **listen**. `flagged.csv` contains what people said, so keep it private (don't send it).

---

## 5. Create the train/dev/test splits

The speaker lists are in `data-collector/docs/SPLITS.md`. It already lists 3 test speakers under `## test`; `## dev` is empty. To change them, open the file:
```bash
xdg-open data-collector/docs/SPLITS.md
```
Write one speaker per line, like `- spk_a7a1ba3e2e6e47a8`, under `## test` or `## dev` (copy the ids from the Per speaker table in qc_report.md). Every speaker not listed goes to train. Save and close.

Then:
```bash
python data-collector/scripts/make_splits.py --dataset ~/banglish-data/dataset --config data-collector/docs/SPLITS.md --exclude ~/banglish-data/reports/flagged.csv --out ~/banglish-data/splits.json
```
Expected output (shortened):
```
WARNING: the dev split has no speakers.

split   clips  speakers  minutes
train      20         2      1.5
dev         0         0      0.0
test       36         3      2.9

Excluded 4 clips marked 'remove' in /home/YOU/banglish-data/reports/flagged.csv; kept 56.
speaker              split   kept  excluded
spk_...              train     10         2
...

category             train clips/min     dev clips/min    test clips/min
...
WARNING: these categories have fewer than 15 clips in the test split:
  ...
Wrote /home/YOU/banglish-data/splits.json
```
- `the dev split has no speakers` is fine for now (the benchmark only uses test).
- `fewer than 15 clips in the test split` means those categories are measured on few clips: OK for a first look; add test speakers when you have more recordings.
- `STOPPED: --exclude matched 0 clips` → the message says why: either flagged.csv has no clip marked `remove` (only **remove** clips are left out; **listen** and **fix text** clips stay in), or flagged.csv was made from a different export (run step 4 again on the same dataset folder).
- `REFUSING TO RUN: ... listed in BOTH test and dev` → a speaker is in both lists; fix SPLITS.md and run again.
- `the test split has no speakers` → none of the ids in SPLITS.md are in your export. Copy them from qc_report.md.

---

## 6. Run the formatter tests

```bash
cd formatter && python -m pytest; cd ~/banglish
```
Expected output (last line):
```
============================= 125 passed in 0.19s ==============================
```
Any `failed` in the last line → send me the whole output.

---

## 7. Benchmark the speech models on the TEST split (tiny, base, small)

Runs Whisper tiny, then base, then small, on your laptop's CPU, only on the test speakers from step 5. The first run downloads the models once (tiny 75 MB, base 145 MB, small 480 MB). No audio or text is uploaded anywhere.

**7a. Quick mode first:** `--quick` evaluates only the first 30 test clips, to check that everything works (about 2-6 minutes on a laptop, plus the downloads):
```bash
python -m eval.run --config eval/config.yaml --data ~/banglish-data/dataset --splits ~/banglish-data/splits.json --split test --models whisper-tiny,whisper-base,whisper-small --output ~/banglish-data/results --quick
```
Expected output (shortened):
```
WARNING: LLM romanizer unavailable (no API key (GEMINI_API_KEY or GOOGLE_API_KEY not set in .env / environment)); used 'rules' instead
30 clips, 3 speakers. Split: test from `splits.json`; limited to first 30 clips (--quick)
== whisper-tiny + romanizer (rules): 0 already done, 30 to transcribe
[whisper-tiny] model loaded in 3.3s; transcribing 30 clips
[whisper-tiny] 10/30
...
== whisper-base + romanizer (rules): 0 already done, 30 to transcribe
...
== whisper-small + romanizer (rules): 0 already done, 30 to transcribe
...
Wrote /home/YOU/banglish-data/results/summary.md
```
The `LLM romanizer unavailable` warning is expected: Whisper writes Bengali letters, and without a Gemini key a built-in offline converter turns them into Banglish. Messages like `Warning: You are sending unauthenticated requests to the HF Hub` are harmless.

**7b. Full test split:** the same command without `--quick`. The 30 clips from 7a are reused, so only the rest are transcribed:
```bash
python -m eval.run --config eval/config.yaml --data ~/banglish-data/dataset --splits ~/banglish-data/splits.json --split test --models whisper-tiny,whisper-base,whisper-small --output ~/banglish-data/results
```
Expected output: like 7a, but without `limited to first 30 clips`, ending with `Wrote /home/YOU/banglish-data/results/summary.md`.

Stopped it halfway (Ctrl + C, laptop went to sleep)? Run the same command again: clips that are done are skipped.

**How long and how much memory.** Measured on a test machine with fake recordings of about 5 seconds each; your laptop may be up to 2x slower. Time grows with the minutes of audio, not just the number of clips.

| Model | First-time download | Time per 100 clips, 4-core laptop | Time per 100 clips, 2-core laptop | RAM it uses |
|---|---|---|---|---|
| whisper-tiny | 75 MB | about 1.5 min | about 2 min | about 0.35 GB |
| whisper-base | 145 MB | about 1.5 min | about 2 min | about 0.5 GB |
| whisper-small | 480 MB | about 3 min | about 6 min | about 0.8-1.0 GB |
| **all three** | 700 MB | **about 6 min** | **about 10 min** | 1 GB at a time |

The models run one after another, so 2 GB of free RAM is enough (close Chrome if your laptop has only 4 GB). tiny is not always faster than base: when it is confused it repeats words, which takes longer.

**Results:** `~/banglish-data/results/summary.md` (the table you read), plus one folder per model with `worst.csv` (the 20 worst clips, with what people said and what the model heard: private, don't send).
```bash
xdg-open ~/banglish-data/results/summary.md
```

---

## 8. Send back two files for review

Send these two files (attach them in the chat):
1. `~/banglish-data/reports/qc_report.md`
2. `~/banglish-data/results/summary.md`

Run the summary in 7b (without `--quick`) before you send it. In the file manager, press **Ctrl + H** to see hidden folders, or type the path after pressing **Ctrl + L**.

**What's in them (checked):**
- No audio. Both are small text files; the scripts only write counts, minutes, percentages and tables.
- No keys. The scripts never write the Supabase key (or any key) into a file.
- No transcripts. Neither file contains what people said.
- They do contain: the anonymous speaker ids (`spk_...`), phone models, region/category counts, your laptop's CPU/RAM, and the folder path (which includes your Ubuntu user name).

Optional double-check that no key is in them:
```bash
grep -c -E "sb_secret_|sb_publishable_|eyJ" ~/banglish-data/reports/qc_report.md ~/banglish-data/results/summary.md
```
Expected output (both must be 0):
```
/home/YOU/banglish-data/reports/qc_report.md:0
/home/YOU/banglish-data/results/summary.md:0
```

**Do NOT send:** anything in `~/banglish-data/dataset/` (audio), `flagged.csv`, `splits.json`, or the model folders in `results/` (they contain what people said).

Optional: check that nothing private is waiting to be committed in the repo:
```bash
git status --short
```
Expected output: nothing, or only ` M data-collector/docs/SPLITS.md` if you edited the speaker list in step 5.
