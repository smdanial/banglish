from __future__ import annotations

from .rules import RULES
from .text import light_clean, tokenize
from .vocab import get_vocab

MATCH_THRESHOLD = 0.6


def format_note(text: str) -> dict:
    """Turn a short Banglish transcript into a clean note. No network or LLM calls.

    Returns {type, result, confidence, matched, notes}. When no rule is confident,
    type is "other", result is the lightly cleaned input and matched is False.
    """
    if not isinstance(text, str):
        raise TypeError("format_note expects a string")
    vocab = get_vocab()
    tokens = tokenize(text)
    candidates = [c for rule in RULES if (c := rule(tokens, vocab)) is not None]
    best = max(candidates, key=lambda c: c.confidence, default=None)
    if best and best.confidence >= MATCH_THRESHOLD:
        return {
            "type": best.type,
            "result": best.result,
            "confidence": best.confidence,
            "matched": True,
            "notes": "; ".join(best.notes),
        }
    notes = "no rule was confident"
    if best:
        notes += f" (best guess: {best.type}, {best.confidence})"
    return {
        "type": "other",
        "result": light_clean(text, vocab),
        "confidence": best.confidence if best else 0.0,
        "matched": False,
        "notes": notes,
    }
