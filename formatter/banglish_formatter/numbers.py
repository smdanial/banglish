"""Reads digits and Banglish number words ("dui hajar pach sho" -> 2500)."""
from __future__ import annotations

from dataclasses import dataclass

from .text import Token, is_digits
from .vocab import Vocab


@dataclass(frozen=True)
class NumberSpan:
    start: int
    end: int  # exclusive
    value: float
    fractional: bool  # came from sharey/soa/paune/der/arai


def _context_ok(tokens: list[Token], j: int, vocab: Vocab, *, allow_units: bool = True) -> bool:
    """True if tokens[j] confirms the previous word is a number (multiplier, currency, unit, time word)."""
    if j >= len(tokens):
        return False
    low = tokens[j].low
    return (
        low in vocab.multipliers
        or low in vocab.currency
        or low in vocab.time_classifiers
        or (allow_units and low in vocab.quantity_units)
        or _compound(low, vocab) is not None
    )


def _compound(low: str, vocab: Vocab):
    """Joined forms like "pachsho" -> (5, 100)."""
    for mult_word, mult in sorted(vocab.multipliers.items(), key=lambda kv: -len(kv[0])):
        if low.endswith(mult_word) and len(low) > len(mult_word):
            prefix = low[: -len(mult_word)]
            for table in (vocab.words, vocab.compound_prefixes, vocab.fractions):
                if prefix in table and prefix not in vocab.ambiguous:
                    return table[prefix], mult
    return None


def _base_value(tokens: list[Token], j: int, vocab: Vocab):
    """Value of a plain number token, or None. Applies the ambiguity guard."""
    tok = tokens[j]
    if is_digits(tok):
        return float(tok.text)
    low = tok.low
    if low in vocab.words:
        if low in vocab.ambiguous and not _context_ok(tokens, j + 1, vocab):
            return None
        return vocab.words[low]
    return None


def parse_number(tokens: list[Token], i: int, vocab: Vocab) -> NumberSpan | None:
    n = len(tokens)
    total = hundreds = 0.0
    cur = None
    fractional = False
    seen = False
    big = float("inf")
    j = i
    while j < n:
        low = tokens[j].low
        if low in vocab.modifiers:
            if cur is not None or j + 1 >= n:
                break
            nxt = _base_value(tokens, j + 1, vocab)
            if nxt is None:
                break
            cur = nxt + vocab.modifiers[low]
            fractional = seen = True
            j += 2
            continue
        if low in vocab.fractions:
            if cur is not None or not _context_ok(tokens, j + 1, vocab, allow_units=False):
                break
            cur = vocab.fractions[low]
            fractional = seen = True
            j += 1
            continue
        base = _base_value(tokens, j, vocab)
        if base is not None:
            if cur is not None:
                break
            cur = base
            seen = True
            j += 1
            continue
        comp = _compound(low, vocab)
        if comp is not None:
            if cur is not None:
                break
            cur, low_mult = comp
            fractional = fractional or not float(cur).is_integer()
            seen = True
            mult = low_mult
        elif low in vocab.multipliers:
            mult = vocab.multipliers[low]
        else:
            break
        # apply multiplier
        if mult < 1000:
            if hundreds:
                break
            hundreds = (cur if cur is not None else 1) * mult
        else:
            if mult >= big:
                break
            total += (hundreds + (cur if cur is not None else 0) or 1) * mult
            hundreds = 0
            big = mult
        cur = None
        seen = True
        j += 1
    if not seen or j == i:
        return None
    value = total + hundreds + (cur or 0)
    return NumberSpan(i, j, value, fractional)


def find_numbers(tokens: list[Token], vocab: Vocab) -> list[NumberSpan]:
    spans, i = [], 0
    while i < len(tokens):
        span = parse_number(tokens, i, vocab)
        if span:
            spans.append(span)
            i = span.end
        else:
            i += 1
    return spans
