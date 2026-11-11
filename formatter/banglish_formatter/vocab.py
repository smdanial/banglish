"""Loads the YAML vocabulary in formatter/data/."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DATA_DIR = Path(os.environ.get("BANGLISH_FORMATTER_DATA", Path(__file__).resolve().parent.parent / "data"))


def _load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _str_map(section: dict, name: str) -> dict[str, float]:
    out = {}
    for key, value in (section or {}).items():
        if not isinstance(key, str):
            raise ValueError(f"{name}: spelling {key!r} must be quoted in the YAML file")
        out[key.lower()] = float(value)
    return out


def _str_set(items, name: str) -> frozenset[str]:
    out = set()
    for item in items or []:
        if not isinstance(item, str):
            raise ValueError(f"{name}: entry {item!r} must be quoted in the YAML file")
        out.add(item.lower())
    return frozenset(out)


def _phrases(items, name: str) -> tuple[tuple[str, ...], ...]:
    phrases = {tuple(p.split()) for p in _str_set(items, name)}
    return tuple(sorted(phrases, key=len, reverse=True))


@dataclass(frozen=True)
class Vocab:
    words: dict
    multipliers: dict
    modifiers: dict
    fractions: dict
    compound_prefixes: dict
    ambiguous: frozenset
    currency: frozenset
    expense_keywords: frozenset
    quantity_units: frozenset
    total_words: frozenset
    expense_header_markers: frozenset
    expense_strip: frozenset
    conjunctions: frozenset
    time_classifiers: frozenset
    past_words: frozenset
    minute_words: frozenset
    am_words: frozenset
    pm_words: frozenset
    periods: dict  # word -> "am" | "noon" | "pm" | "night"
    time_particles: frozenset
    day_words: frozenset
    date_words: frozenset
    event_words: frozenset
    reminder_phrases: tuple
    with_phrases: tuple
    schedule_strip: frozenset
    name_stop: frozenset
    fillers: frozenset


@lru_cache(maxsize=1)
def get_vocab() -> Vocab:
    n = _load("numbers.yaml")
    lx = _load("lexicon.yaml")
    periods = {}
    for period, words in (lx.get("periods") or {}).items():
        for w in _str_set(words, f"periods.{period}"):
            periods[w] = period
    ampm = lx.get("ampm") or {}
    return Vocab(
        words=_str_map(n.get("words"), "words"),
        multipliers=_str_map(n.get("multipliers"), "multipliers"),
        modifiers=_str_map(n.get("modifiers"), "modifiers"),
        fractions=_str_map(n.get("fractions"), "fractions"),
        compound_prefixes=_str_map(n.get("compound_prefixes"), "compound_prefixes"),
        ambiguous=_str_set(n.get("ambiguous"), "ambiguous"),
        currency=_str_set(lx.get("currency"), "currency"),
        expense_keywords=_str_set(lx.get("expense_keywords"), "expense_keywords"),
        quantity_units=_str_set(lx.get("quantity_units"), "quantity_units"),
        total_words=_str_set(lx.get("total_words"), "total_words"),
        expense_header_markers=_str_set(lx.get("expense_header_markers"), "expense_header_markers"),
        expense_strip=_str_set(lx.get("expense_strip"), "expense_strip"),
        conjunctions=_str_set(lx.get("conjunctions"), "conjunctions"),
        time_classifiers=_str_set(lx.get("time_classifiers"), "time_classifiers"),
        past_words=_str_set(lx.get("past_words"), "past_words"),
        minute_words=_str_set(lx.get("minute_words"), "minute_words"),
        am_words=_str_set(ampm.get("am"), "ampm.am"),
        pm_words=_str_set(ampm.get("pm"), "ampm.pm"),
        periods=periods,
        time_particles=_str_set(lx.get("time_particles"), "time_particles"),
        day_words=_str_set(lx.get("day_words"), "day_words"),
        date_words=_str_set(lx.get("date_words"), "date_words"),
        event_words=_str_set(lx.get("event_words"), "event_words"),
        reminder_phrases=_phrases(lx.get("reminder_phrases"), "reminder_phrases"),
        with_phrases=_phrases(lx.get("with_phrases"), "with_phrases"),
        schedule_strip=_str_set(lx.get("schedule_strip"), "schedule_strip"),
        name_stop=_str_set(lx.get("name_stop"), "name_stop"),
        fillers=_str_set(lx.get("fillers"), "fillers"),
    )
