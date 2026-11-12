# eval/ — compare speech models on our Banglish recordings (Task B2)

**Run it on your real data (laptop, no GPU), from the repo folder:**
1. One-time setup: `python -m venv .venv`, then activate it (Windows: `.venv\Scripts\activate`, Mac/Linux: `source .venv/bin/activate`), then `pip install -r eval/requirements.txt`.
2. Optional, for Gemini and the better romanizer: put `GEMINI_API_KEY=...` (and if you like `GEMINI_MODEL=...`) in a file called `.env` in the repo folder.
3. Start small: `python -m eval.run --config eval/config.yaml --data PATH/TO/dataset --splits PATH/TO/splits.json --models whisper-tiny,whisper-base,gemini`
4. When that works, add the slower ones: `--models whisper-small,whisper-medium` (medium needs ~4 GB free RAM and is ~6x slower than real time). large-v3 only if you have time and 8 GB+ free RAM: `--models whisper-large-v3`.
5. Open `eval/results/summary.md`. The bad clips for each model are in `eval/results/<model>/worst.csv`.
6. Stopped halfway? Run the same command again: clips that are already done get skipped.
7. No splits.json? Leave out `--splits` and every clip is evaluated (summary.md says so).

`PATH/TO/dataset` is the folder `export_dataset.py` made (it has `manifest.csv` and `wavs/`). The first run downloads each Whisper model (tiny 75 MB, base 145 MB, small 480 MB, medium 1.5 GB).

---

## Reference

**Try it without real data:** `python -m eval.run --config eval/config.yaml` uses the 12-clip synthetic sample in `eval/sample/`. The sample is Google text-to-speech reading Bengali-script versions of our prompts; the audio files are generated on the first run and are never committed. Tests: `python -m pytest eval/tests`.

**Models** (`eval/config.yaml`, `models:`): faster-whisper tiny/base/small/medium (CPU, int8), large-v3 (disabled by default), a Gemini baseline through its OpenAI-compatible API (asked for romanized Banglish directly), and `example-plugin`. To add your own model, copy `eval/plugins/example_plugin.py`, write `transcribe(path) -> text`, and add an entry like `example-plugin` with `enabled: true`. Set `romanize: true` if it writes Bengali (or any non-Latin) script.

**Run variants** (`run_variants:` in the config): each Whisper model runs once per variant in its `variants:` list, named `<model>:<id>` (results folder `<model>_<id>`):
- `bn`: (a) `language="bn"` forced.
- `auto`: (b) auto-detect (faster-whisper gets `language=None`).
- `en-prompt`: (c) `language="en"` forced, with an `initial_prompt` of short romanized Banglish sentences, so Whisper writes Latin letters itself.

`--models whisper-small` runs all its variants and `--models whisper-small:bn` runs one. For every clip, `transcripts.jsonl` and `hypotheses.csv` record the language passed to faster-whisper (`language_requested`), the language it decoded with (`language_used`), the language Whisper detects in the audio (`language_detected`, an extra detection pass when the language is forced; `detect_language: false` turns it off) and the script of the raw output (`raw_script`). The console prints the same per clip.

**% outputs in expected script** (summary.md): the share of clips whose raw output (before the romanizer) is mostly in the variant's `expected_script`: Bengali for `bn`/`auto`, Latin for `en-prompt` and Gemini. The "Language and script check" table in summary.md lists language passed / used / detected per run.

**Bengali script vs Banglish:** with `language: bn`, Whisper writes Bengali script. Our references are Latin. Models with `romanize: true` get converted first, and the report labels them `whisper-small + romanizer (llm:gemini-…)`, so the score includes romanizer mistakes. The romanizer is set under `romanizer:` in the config:
- `llm`: the default. Answers are cached in `eval/cache/`.
- `rules`: a rough offline converter. It's used automatically when there is no API key, and the label then says `rules`.

The raw model output is kept in `<model>/hypotheses.csv`.

**Normalization** (`eval/normalization.yaml`): lowercase, no punctuation, collapsed spaces, plus the `variants:` spelling map. Add lines like `amii: ami` to it whenever `worst.csv` shows a "mistake" that is only a spelling difference. The same rules are applied to reference and output.

**Metrics:**
- WER/CER: jiwer, after normalization.
- **Key-field accuracy**: the share of clips with numbers/times where ALL of them are exactly right. It understands `4 tay` = `char tay` = `4:00`, `sharhe 5` = `5:30`, `18 hajar` = `18000`, `01712 345678` = `01712345678`. Word lists are under `key_fields:`.
- Speed: processing seconds per audio second, with model loading excluded.
- Peak RAM of the process running each model. Each model runs in its own process.

**Options:** `--split dev`, `--all` (ignore splits), `--limit 20` (quick try), `--output other/folder`, `--no-isolate`.

**splits.json:** the file written by `data-collector/scripts/make_splits.py` is read directly (its `clips` list is used, so clips left out with `--exclude` stay out). Also accepted: `{"test": [...], "train": [...]}`, `{"splits": {...}}`, `{"test": {"speakers": [...]}}`, or `{"<clip path>": "test"}`; entries can be speaker_ids, manifest paths or file names.

**Privacy:** `eval/results/` and `eval/cache/` contain transcripts of private recordings. Both are gitignored, so don't commit or share them. No audio file is ever committed (`*.wav` etc. are gitignored).
