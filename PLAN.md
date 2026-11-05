# Bolo-Log → Banglish Voice for Keyboards: Work Plan

**Goal:** a voice feature that runs well on mid-range Android phones (4 GB RAM minimum, MediaTek or Snapdragon) and can be dropped into Ridmik's keyboard (or our own) as an SDK.
**Two modes:** *Plain* (Banglish speech → Banglish text) and *Smart* (speech → formatted note).
**Builder:** non-coder working with coding agents, so every task below is small, testable, and has a "done when" line.

---

## 1. Decision gates (these decide the architecture; don't skip)

| Gate | Question | How we answer it | Decision |
|---|---|---|---|
| G1 | Which model is accurate enough on real Banglish? | Benchmark on our test set (Task B2) | Pick base model for fine-tuning |
| G2 | Can Plain mode run **on a 4 GB phone** fast enough? | On-device test on 2-3 real phones (Task A2) | Yes → on-device. No → small server for Plain mode |
| G3 | What does one voice request cost us? | Cost log from pilot (Task P2) | Sets the usage cap we give Ridmik |

Targets to set after the first benchmark (write real numbers in `docs/SPEC.md`): error rate (WER) on test set, latency from end of speech to text, max cost per request, max app RAM use.

---

## 2. Workstreams and tasks

### A. Android and on-device
- **A1** Test-harness Android app: mic button → record → send to our server → show text. (Gives us a phone demo fast.)
- **A2** On-device feasibility test: run a small speech model on the test phones. Candidates to evaluate (not promises): whisper.cpp, sherpa-onnx, Cactus. Record RAM, speed, and accuracy per phone.
- **A3** Keyboard fork with a mic button (check the license of the keyboard we fork).
- **A4** Package voice as an **SDK** (Android library): `startListening()`, `stopListening()`, `onResult(text)`, `onError(reason)`. Ridmik should need only these.
- **A5** Permission, consent screen, and a clear "listening" indicator.

### B. Evaluation (do first)
- **B1** Build the **test set**: 150-200 short Banglish sentences, each with correct text, spoken by 10+ different people on different phones. Never train on it.
- **B2** Benchmark script: runs each model over the test set, outputs a WER table and speed per model.
- **B3** Failure log: categories (numbers, names, English words, noise, accents).

### C. Data and fine-tuning
- **C1** Recording web page: shows a prompt sentence, records, saves audio plus the text. Includes consent text.
- **C2** Romanization style guide (1 page): one fixed way to spell common Banglish words, so labels stay consistent.
- **C3** Fine-tune a Whisper model with LoRA on a free Kaggle or Colab GPU (public Bangla speech + our recordings).
- **C4** Export the tuned model for serving (CTranslate2 int8 for server, ggml for whisper.cpp) and re-run B2.

### D. Backend v2 and formatter
- **D1** Backend v2: keep FastAPI; add API-key auth, rate limits, request logging (latency, cost, errors), no audio stored by default.
- **D2** Streaming endpoint (WebSocket) so words appear while the user speaks.
- **D3** **Rule-based formatter** for Smart mode (times, "tk/taka", totals, names) as a standalone module with a test file of 50+ example sentences. LLM only as fallback.
- **D4** Fallback chain: on-device → server model → cloud LLM, with timeouts and retries.

### P. Pilot and partner
- **P1** Pilot with 10-20 users; collect consented audio and corrections.
- **P2** Cost and error report from pilot logs.
- **P3** Partner pack for Ridmik: demo APK, SDK doc, accuracy and latency numbers, usage cap, privacy policy.

---

## 3. Order of work (aggressive but realistic sprint plan)

| When | Do | Gate |
|---|---|---|
| Days 1-3 | B1, B2, C1 (start collecting), D3 | |
| Days 3-7 | A1, A2, B3, D1 | G1, G2 |
| Week 2 | C2, C3, D2, A3 | |
| Week 3 | C4, A4, A5, D4, P1 starts | |
| Week 4 | P1 continues, P2, P3 | G3 |

If A2 shows the phones can't run the model, Plain mode moves to a small server and we skip the on-device parts of A3-A4. Expect slips: Android work is the riskiest for a non-coder, so keep A1 simple before touching A3.

---

## 4. Codebase layout (new repo, replaces the single `bolo-log` folder)

```
banglish-voice/
├── backend/            # FastAPI v2 (auth, streaming, logging)
├── formatter/          # rule-based Smart mode + tests/
├── eval/               # test set, benchmark scripts, results/
├── training/           # fine-tuning notebooks and scripts (run on Kaggle/Colab)
├── data-collector/     # recording web page
├── android/
│   ├── harness-app/    # A1
│   ├── keyboard/       # A3 (fork)
│   └── voice-sdk/      # A4
├── docs/               # SPEC.md, STYLE-GUIDE.md, PRIVACY.md, partner pack
├── HANDOVER.md
└── README.md
```

Keep the old `bolo-log` repo as-is (the hackathon version). Start the new repo by copying only `backend/` and `frontend/` ideas, not the virtual env or model files.

---

## 5. How to work with coding agents (rules that save you)

1. **One task = one prompt = one commit.** Use the task IDs above (e.g. "Task D3").
2. **Every prompt includes:** goal, files to touch, what NOT to touch, and a **"done when"** check you can run yourself.
3. **Ask for tests first** for the formatter (D3) and the benchmark (B2). Tests are how a non-coder knows it works.
4. **Never paste keys into prompts.** Keys live in `.env` only. Rotate any key that appeared in a screenshot or chat.
5. **Keep HANDOVER.md updated** at the end of every task: what changed, how to run, what's untested.
6. **Use branches:** `git checkout -b task-D3`, merge only after it passes.
7. **Model choice:** use a stronger model for architecture, Android, and fine-tuning scripts; a fast cheap model for UI, docs, and small fixes. If an agent fails twice on the same bug, switch models instead of repeating.
8. **Agent can't test on a phone.** You do manual phone tests and report results (screenshot or text) back.

---

## 6. Resources needed

**Hardware**
- 2-3 real test phones: one budget (4 GB RAM), one mid-range, one Samsung. Borrow friends' phones for a day if needed.
- Your laptop (no GPU) is enough for backend and Android builds.

**Accounts and tools (mostly free)**
- GitHub (repo), Hugging Face (models and datasets), Kaggle and Google Colab (free GPU time for fine-tuning)
- Android Studio (build the apps), a USB cable for phone testing
- Google AI Studio key (cloud fallback and pilot), Render or similar (backend hosting)
- Google Play developer account later, only if we publish our own keyboard (one-time fee; check the current amount)

**People**
- 10+ volunteers to record the test set and training sentences (classmates work fine), with a short consent line.
- One person who speaks a different dialect or accent from yours, to catch bias early.
- Someone technical to review the Android code once (a senior student or mentor), because agents make subtle Android mistakes.

**Data**
- Our own recordings (most valuable)
- Public Bangla speech datasets (Common Voice, OpenSLR) as a base

**Docs to write (agent drafts, you review)**
- `SPEC.md` (targets), `STYLE-GUIDE.md` (romanization), `PRIVACY.md` (what we record, retention, consent)

---

## 7. Risks to watch
- **Data is the bottleneck**, not code. Start recording on day 1.
- **Android keyboard work** is hard for non-coders: get the harness app (A1) working before the keyboard fork (A3).
- **Privacy:** keyboards see sensitive input. Record audio only when the mic is pressed, say so on screen, and delete by default.
- **Cloud dependence:** don't rely on a free API tier for the pilot's core path without a fallback.
- **Terms of use:** read the API provider's terms before using any model's outputs as training labels. Use human-corrected labels.
