# Banglish note formatter (Task D3)

Turns a short Banglish transcript into a clean note using rules only (no LLM, no internet).

| Input | Output (`result`) |
|---|---|
| `akash er sathe meeting ache bikal 4 tay` | `Meeting with Akash - 4:00 PM` |
| `alu 50 tk, piyaj 40 tk, total 100 tk` | `alu - 50` / `piyaj - 40` / `total - 90` (notes: spoken total 100 does not match) |
| `ami bhalo achi` | `ami bhalo achi` with `matched: false` (caller should fall back to the LLM) |

## Run it (once: `pip install -r formatter/requirements.txt`)
Open a terminal in the `formatter` folder, then:
- Run all tests: `python3 -m pytest`  → should end with "passed" and no "failed".
- Pass rate per type: `python3 scripts/coverage_report.py` (add `--show-failures` to see what broke).
- Try one sentence: `python3 -m banglish_formatter "kal shokal 9 tay doctor appointment"`

## Use it from Python
```python
from banglish_formatter import format_note
format_note("rat 10 tay mone koriye dio oshudh khete hobe")
# {'type': 'schedule', 'result': 'Oshudh khete hobe - 10:00 PM', 'confidence': 0.9, 'matched': True, 'notes': ''}
```
`type` is `schedule`, `expenses` or `other`; `matched` is True when `confidence >= 0.6` (`MATCH_THRESHOLD`). `notes` explains guesses (e.g. "AM/PM not said; guessed PM", total mismatch).

## How to add a vocabulary word or a rule
1. **New spelling of a number** (e.g. `ponchas` = 50): add `ponchas: 50` under `words:` in `data/numbers.yaml`.
2. **Other words** (currency, time-of-day, day names, event words, filler sounds...): add them to the matching list in `data/lexicon.yaml`.
3. Quote a word YAML might read as yes/no, e.g. `"no"` or `"on"` (the loader stops with a clear error otherwise).
4. Add an example to `tests/cases.yaml` (`id`, `input`, `type`, `expected`), then run `python3 -m pytest`.
5. **New rule**: copy `banglish_formatter/rules/expenses.py` as a template: a function `(tokens, vocab) -> Candidate | None`
   that returns `Candidate(type, lines, confidence, notes)`.
6. Register it in `RULES` in `banglish_formatter/rules/__init__.py`; the most confident rule wins. Add test cases.

## Behaviour notes
- Time words: shokal/bhor = AM, dupur = PM (alone = 12:00 PM), bikal/shondha = PM, rat = PM except rat 12 = 12:00 AM and rat 1-4 = AM.
  No time word → guess (7-11 AM, 12-6 PM), lower confidence, and a note. `4:30`, `16:30`, `4 ta 30`, `sharey 4`, `paune 5`, `soa 4`, `der tay` (1:30) all work.
- Day words (`kal`, `porshu`, `shombar`, `15 tarikh`) are kept as spoken: `Meeting - kal 3:00 PM`.
- Expenses: `item - amount` per line; tk/taka/৳ removed; quantities stay in the item (`2 kg alu - 60`); a missing amount shows `- ?` and is left out of the total.
- Sentences that mix a clock time and money ("bikal 4 tay rahim ke 500 taka dite hobe"), sentences with two separate times ("meeting 10:00 am, call 4:00 pm"), and impossible clocks (`25:99`) are returned as `other` on purpose.
