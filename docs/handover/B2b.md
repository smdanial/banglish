# B2b: Whisper language check, run variants, script column

Why: in the real benchmark whisper-small wrote Devanagari for 25 of 30 clips and whisper-base wrote Arabic
script for 7, although the config says `language: bn`.

## Answer: language="bn" IS passed, and Whisper still writes the wrong script

- `eval/models/faster_whisper_model.py` passes `language=` straight to `WhisperModel.transcribe()`. faster-whisper
  1.2.1 builds its decoder prompt from that value; checked on whisper-small: `language="bn"` gives
  `<|startoftranscript|> <|bn|> <|transcribe|>`, so Bengali is really forced.
- Each clip now logs the language passed, the language faster-whisper decoded with (`info.language`) and the
  language Whisper hears in the audio (extra `detect_language()` pass when the language is forced). On the
  12-clip sample (gTTS audio) every forced run shows `passed=bn, used=bn` on 12/12 clips, and Whisper detects
  `bn` on 9/12. Even so:

| Model | (a) bn forced: raw script | (b) auto-detect: raw script | (c) en + prompt: raw script |
|---|---|---|---|
| whisper-tiny | Latin 12 | Latin 12 | Latin 12 |
| whisper-base | Arabic 8, Latin 4 | Arabic 8, Latin 4 | Latin 12 |
| whisper-small | Devanagari 12 | Devanagari 12 | Latin 12 |

  So the wrong script comes from the models themselves, not from our config: with the `<|bn|>` token,
  whisper-small writes Bangla words in Devanagari letters (e.g. `आमर नंबर शुन्नो एक ...` for "Amar number
  shunno ek ...") and whisper-base in Urdu letters. This matches what you saw on the real data.
- On the sample, (c) `language=en` + romanized-Banglish `initial_prompt` was best for every model
  (whisper-small WER 60.2% vs 75.5% for bn-forced; key-field acc 42.9% vs 14.3%), and its output is Banglish
  in Latin letters, e.g. `Bikal shar e paach tay dhan mondite dakha korbo.` This is synthetic TTS audio only:
  re-run on the real test split before deciding anything.

## What changed

- `eval/config.yaml`: new `run_variants:` block with three variants; each Whisper model lists
  `variants: [bn, auto, en-prompt]` and runs once per variant, named `whisper-small:bn` etc.:
  - (a) `bn`: `language: bn` forced, expected script Bengali.
  - (b) `auto`: `language: auto` (faster-whisper gets `language=None`), expected script Bengali.
  - (c) `en-prompt`: `language: en` forced + `initial_prompt` of two short romanized Banglish lines (written
    fresh, not taken from `data-collector/data/prompts.json`, so no test answers leak), expected script Latin.
- Gemini baseline: the `gemini` entry was already in config.yaml with a romanized-Banglish prompt. It now has
  the label `baseline: romanized-Banglish prompt` and expected script Latin; the prompt and model settings are
  unchanged, so its cached transcripts are reused. **There is no app prompt in the repo yet** (no Gemini
  call in `data-collector/`, and `backend/`/`android/` aren't built), so this is the eval's own prompt. If the app
  has a different one, paste it into `models: - name: gemini - prompt:`.
- `eval/worker.py`: prints the settings once per run
  (`faster-whisper language='bn' (forced), no initial_prompt`) and one line per clip
  (`language passed=bn, used=bn, Whisper detects=hi (0.79), output script=Devanagari`). The same fields go
  into `transcripts.jsonl` and `hypotheses.csv`/`worst.csv` (`language_requested`, `language_used`,
  `language_detected`, `raw_script`).
- `summary.md`: the Overall table has new **Run variant** and **% outputs in expected script** columns
  (raw output, before the romanizer, e.g. `0.0% (0/12 Bengali)`). A new **Language and script check**
  table lists, per run in config order, the script counts and the language passed / used / detected. Notes warn if
  faster-whisper ever decodes in a language other than the one passed, or if old cached transcripts have no
  language info.
- `--models whisper-small` runs all variants of that model; `--models whisper-small:bn` runs one. Unknown
  names now print a warning instead of being silently ignored. RUN_ME.md commands still work but take ~3x
  longer (RUN_ME.md step 7 updated: example output, timing, folder names).

## Decisions

- Results folders are now `<model>_<variant>` (e.g. `whisper-small_bn`), so old `whisper-small/` results are
  not reused. Re-running is needed anyway to record the language per clip.
- The forced-language runs do one extra language-detection pass per clip (about one encoder pass, included in the speed number).
  Turn it off with `detect_language: false` on a model or variant.
- "Expected script" for auto-detect is Bengali: the speech is Bangla, so Hindi/Urdu letters count as wrong.
- All variants keep `romanize: true`, so wrong-script output is still converted and scored. The new column
  shows the raw script, so romanizer rescues are visible.

## Verified (VM, Python 3.10, faster-whisper 1.2.1)

- `python -m pytest eval/tests`: 41 passed. New tests: variant expansion + `--models <base>` + script column +
  results folders (`test_run_variants_expected_script_and_language_log`), and that `language`/`initial_prompt`
  reach `WhisperModel.transcribe` with `auto` -> `None` (`test_faster_whisper_language_is_passed_and_logged`,
  fake faster-whisper).
- Real run on the 12-clip sample: `--models whisper-tiny,whisper-base,whisper-small` (9 runs); numbers above.
- Gemini row and its Latin script column checked against a local fake OpenAI-compatible server.

## NOT verified

- Real recordings: not available on the VM. Run step 7 of RUN_ME.md and send back summary.md.
- Real Gemini API: no key on the VM (same as B2).
- whisper-medium / large-v3 variants: not run here (slow); same code path as tiny/base/small.
