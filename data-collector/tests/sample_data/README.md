# Synthetic sample dataset

Fake data for testing `scripts/qc_dataset.py` and `scripts/make_splits.py`. The "voices" are generated beeps, not real people. Only `manifest.csv` and `SPLITS.md` are in git. Re-create the WAV files with:

```bash
python3 tests/make_sample_data.py
```

8 speakers, 91 clips, with planted problems: too short or too long, mostly silent, no speech, clipped, very quiet, long silence at the start, cut off at the end, empty text, Bengali script, emoji, a very different text, a repeated take, a byte-identical copy, and a missing file. `python3 -m unittest discover -s tests` checks that QC finds every one of them and flags no clean clips.
