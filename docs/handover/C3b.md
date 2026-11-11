# C3b notes: `make_splits.py --exclude` excluded nothing

## Why (what was found)
- I don't have your `flagged.csv` or `manifest.csv`, so I could not see exactly which mismatch you hit. What I checked:
  - Files written by the current scripts **do match**. `export_dataset.py` writes `path` = `wavs/<recording_id>.wav`, `qc_dataset.py` copies that same `path` column into `flagged.csv`, and the old `make_splits.py` compared the two strings exactly. On the synthetic sample and on the earlier local-Supabase run, the right clips were dropped. The column names (`path`, `suggested_action`) have not changed in git history.
  - So the old code could only drop **0** clips without an error if (a) no row in `flagged.csv` had `suggested_action` exactly `remove`, or (b) the `remove` rows' `path` didn't exactly equal a manifest path. The old code then just left out the "(N clips ... were left out)" line. There was no warning.
- **(a) is the most likely cause.** "About a third flagged" in `qc_report.md` counts every flagged clip, but `--exclude` only drops **remove** clips. On real phone audio most flags are expected to be **listen** (`mostly_silence`, `cut_off`, `low_volume`, `long_leading_silence`, `big_text_change`). The C3 handover already warned that those thresholds were tuned on synthetic beeps. Look at "...suggested: remove" in the Overview table of `qc_report.md`. If it says 0, this is the cause.
- **(b) can happen if `flagged.csv` was edited in a spreadsheet and saved.** For example, LibreOffice's AutoCorrect turns a typed `remove` into `Remove`, paths can end up with `\` or `./`, or the file can be saved with a different separator. It can also happen if `flagged.csv` came from a different export than the `manifest.csv` you passed. A real LibreOffice 7 round-trip that keeps the comma separator stayed matching. A semicolon save made the old script crash (`KeyError: 'path'`) rather than silently drop nothing.
- **Next step for you:** run step 5 of RUN_ME again. If it still stops, the `STOPPED:` message names which of (a) or (b) it is. That message shows only clip paths and action counts, no text people said, so it is safe to send.

## What changed (`data-collector/scripts/make_splits.py`)
- **Matching is tolerant.**
  - Column names are matched ignoring case, spaces and BOM; `path`/`file` and `suggested_action`/`action` are both accepted.
  - The separator is detected (`,`, `;` or tab).
  - Action values are compared ignoring case and spaces.
  - Paths are compared ignoring quotes, the Excel `'` prefix, `\` vs `/` and a leading `./`. If the folder part differs (e.g. an absolute path), the file name `<recording_id>.wav` is used, but only when it is unique in the manifest. A `recording_id` column is also matched if present.
- **Per-speaker counts.** With `--exclude`, the script prints `Excluded N clips ...; kept M.`, then a table: speaker, split, kept, excluded. `splits.json` keeps `excluded_clips` and adds `excluded` (the list of excluded paths).
- **Zero matches = stop.** If `--exclude` matches 0 clips, the script exits with code 1 and writes no `splits.json`. There are two messages:
  - no `remove` rows: it shows the counts per action and says "run again without --exclude" if that's intended;
  - `remove` rows that aren't in the manifest: it shows 3 example paths from each file and says to re-run QC on the same dataset folder.
- **Partial matches.** If some `remove` rows match and others don't, the script prints a `WARNING` with how many were ignored, then continues.
- **Wrong file.** A file without `path`/`suggested_action` columns (e.g. passing manifest.csv by mistake) stops with the list of columns it found.

## Tests (`tests/test_qc_and_splits.py`, class `ExcludeMatchesRealFormat`)
- The test builds a small manifest with `export_dataset.MANIFEST_FIELDS` and `wavs/<uuid>.wav` paths: 8 clips, 3 speakers, 3 that should be removed and 1 listen. It then runs the real `qc_dataset.py` to make `flagged.csv`, so the format is exactly what the scripts produce.
- The tests check:
  - the 3 `remove` clips are excluded and the listen clip is kept;
  - the per-speaker table shows the right kept/excluded counts;
  - a "re-saved by spreadsheet" copy (`;`, quoted, no BOM, Title-case headers, `Remove `, `.\wavs\...`) still matches;
  - a flagged.csv from another export stops;
  - a file with only listen rows stops;
  - passing manifest.csv as `--exclude` stops.
- `python3 -m unittest discover -s tests` (in data-collector/): 13 tests OK.

## Docs
- RUN_ME.md step 5: updated the expected output and added what to do about `STOPPED: --exclude matched 0 clips`. data-collector/README.md: one line updated.
- HANDOVER.md was not edited; these notes are here instead.

## NOT verified
- Your real files: the exact cause in your data is not confirmed (see "Why").
- Excel was not tested, only LibreOffice 7 headless conversions and hand-made variants.
