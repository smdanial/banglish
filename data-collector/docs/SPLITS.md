# Speaker splits (train / dev / test)

`scripts/make_splits.py` reads this file. Every speaker listed under **test** goes to the test set, every speaker under **dev** goes to the dev set, and **all other speakers go to train**. Splits are by speaker, never by clip, so the model is always tested on voices it has never heard.

How to choose: open `reports/qc_report.md`, look at the *Per speaker* table and pick speakers with a mix of regions, ages, genders and phone models. Aim for about 10% of the minutes in test and 10% in dev, and at least 15 test clips per category. Once you have trained on a split, do not move speakers out of test.

Write one speaker_id per line, starting with `- ` (or as `speaker_id=spk_...`). Anything after the id is ignored, so you can add a note, e.g. `- spk_1a2b3c4d5e6f7a8b  Sylhet, Redmi`. A speaker may appear in only one list; the script refuses to run otherwise.

## test

## dev

## Not yet sorted
Move each line below under `## test` or `## dev` (or delete it to keep that speaker in train). The script refuses to run while any are left here.

speaker_id=spk_a7a1ba3e2e6e47a8
speaker_id=spk_10f939513bb142a5
speaker_id=spk_e3134623afd148ac
