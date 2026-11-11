"""Expenses rule: "alu 50 tk, piyaj 40 tk" -> "alu - 50\\npiyaj - 40\\ntotal - 90"."""
from __future__ import annotations

from dataclasses import dataclass

from ..numbers import find_numbers
from ..text import Token, fmt_number
from ..vocab import Vocab
from .base import Candidate


@dataclass
class _Item:
    tokens: list[Token]
    amount: float | None


def _clean_name(tokens: list[Token], vocab: Vocab) -> list[Token]:
    toks = [t for t in tokens if t.low not in vocab.currency and t.low not in vocab.fillers and not t.is_sep]
    # drop a spoken header: "aj bazar e khoroch holo alu" -> "alu"
    markers = [k for k, t in enumerate(toks) if t.low in vocab.expense_header_markers]
    if markers:
        rest = toks[markers[-1] + 1:]
        while rest and rest[0].low in vocab.expense_strip:
            rest = rest[1:]
        if rest:
            toks = rest
    while toks and toks[0].low in vocab.expense_strip:
        toks = toks[1:]
    while toks and toks[-1].low in vocab.expense_strip:
        toks = toks[:-1]
    return toks


def expenses_rule(tokens: list[Token], vocab: Vocab) -> Candidate | None:
    lows = [t.low for t in tokens]
    n = len(tokens)
    spans = {s.start: s for s in find_numbers(tokens, vocab)}

    start = 0
    for i, t in enumerate(tokens):
        if t.text == ":":
            if not any(k < i for k in spans):
                start = i + 1
            break

    # numbers that are clock times ("bikal 4 tay") are not prices
    time_like = set()
    for k, sp in spans.items():
        nxt = lows[sp.end] if sp.end < n else None
        p = k - 1
        while p >= 0 and lows[p] in vocab.time_particles:
            p -= 1
        if (nxt in vocab.time_classifiers and nxt not in vocab.quantity_units) or (p >= 0 and lows[p] in vocab.periods):
            time_like.add(k)
    for k in time_like:
        del spans[k]

    items: list[_Item] = []
    cur: list[Token] = []
    i = start
    while i < n:
        t = tokens[i]
        if t.is_sep or t.low in vocab.conjunctions:
            if cur:
                items.append(_Item(cur, None))
                cur = []
            i += 1
            continue
        s = spans.get(i)
        if s:
            nxt = lows[s.end] if s.end < n else None
            if nxt in vocab.quantity_units:
                cur.extend(tokens[i:s.end + 1])
                i = s.end + 1
                continue
            end = s.end + (1 if nxt in vocab.currency else 0)
            items.append(_Item(cur, s.value))
            cur = []
            i = end
            continue
        cur.append(t)
        i += 1
    if cur:
        items.append(_Item(cur, None))

    for it in items:
        it.tokens = _clean_name(it.tokens, vocab)
    # "50 tk rickshaw" -> amount first, name after
    merged: list[_Item] = []
    for it in items:
        if merged and not merged[-1].tokens and merged[-1].amount is not None and it.amount is None and it.tokens:
            merged[-1].tokens = it.tokens
        else:
            merged.append(it)
    # drop leftovers like the "kg" in "65 taka kg" (a per-unit price)
    items = [it for it in merged if it.amount is not None
             or (it.tokens and not all(t.low in vocab.quantity_units or t.low == "per" for t in it.tokens))]

    notes: list[str] = []
    spoken_total = None
    priced: list[_Item] = []
    lines_items: list[_Item] = []
    for it in items:
        words = {t.low for t in it.tokens}
        if it.amount is not None and words and words & vocab.total_words and len(it.tokens) <= 3:
            spoken_total = it.amount
            continue
        lines_items.append(it)
        if it.amount is not None:
            priced.append(it)
    if not priced:
        return None

    lines = []
    missing = False
    for it in lines_items:
        name = " ".join(t.text for t in it.tokens) or "?"
        if not it.tokens:
            missing = True
            notes.append(f"amount {fmt_number(it.amount)} has no item name")
        if it.amount is None:
            missing = True
            notes.append(f"no amount for '{name}'; left out of total")
            lines.append(f"{name} - ?")
        else:
            lines.append(f"{name} - {fmt_number(it.amount)}")

    total = sum(it.amount for it in priced)
    if len(priced) >= 2:
        lines.append(f"total - {fmt_number(total)}")
    if spoken_total is not None:
        if abs(spoken_total - total) > 1e-9:
            notes.append(f"spoken total {fmt_number(spoken_total)} does not match computed total {fmt_number(total)}; used computed")
        else:
            notes.append("spoken total matches")

    money_words = any(low in vocab.currency for low in lows) or any(low in vocab.expense_keywords for low in lows)
    conf = 0.5
    if money_words:
        conf += 0.3
    if len(priced) >= 2:
        conf += 0.15
    if missing:
        conf -= 0.15
    if any(not it.tokens for it in priced):
        conf -= 0.15
    if time_like:
        conf -= 0.3
        notes.append("sentence also has a clock time")
    return Candidate("expenses", lines, round(min(conf, 0.97), 2), notes)
