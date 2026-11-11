"""Tokenizing and light cleanup."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .vocab import Vocab

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
SEPARATORS = frozenset({",", ";", ":", "-", "|", "।", ".", "!", "?"})
_TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")
_DIGITS_RE = re.compile(r"^\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class Token:
    text: str

    @property
    def low(self) -> str:
        return self.text.lower()

    @property
    def is_sep(self) -> bool:
        return self.text in SEPARATORS


def is_clock(token: Token):
    m = _TIME_RE.match(token.text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def is_digits(token: Token) -> bool:
    return bool(_DIGITS_RE.match(token.text))


def fmt_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _thousands(m: re.Match) -> str:
    return fmt_number(float(m.group(1)) * 1000)


def tokenize(text: str) -> list[Token]:
    s = text.translate(_BN_DIGITS)
    s = s.replace("৳", " ৳ ")
    s = re.sub(r"[\"'()\[\]{}“”‘’]", " ", s)
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)          # 1,200 -> 1200
    s = re.sub(r"(\d)\s*/-", r"\1", s)                    # 50/- -> 50
    s = re.sub(r"\b(\d+(?:\.\d+)?)k\b", _thousands, s, flags=re.IGNORECASE)  # 2k -> 2000
    s = re.sub(r"\b([ap])\.\s?m\b\.?", r"\1m", s, flags=re.IGNORECASE)        # p.m. -> pm
    s = re.sub(r"(?<=\d)(?=[^\W\d_])|(?<=[^\W\d_])(?=\d)", " ", s)    # 4tay -> 4 tay
    s = re.sub(r"([,;!?|।\n])", r" \1 ", s)
    s = re.sub(r"(?<!\d)([:.])|([:.])(?!\d)", r" \1\2 ", s)          # keep 4:30 / 12.5
    s = re.sub(r"(?:^|\s)[-–—]+(?=\s|$)", " - ", s)
    return [Token(t) for t in s.split()]


def light_clean(text: str, vocab: Vocab) -> str:
    """Collapse whitespace and drop hesitation sounds; otherwise keep the user's words."""
    words = [w for w in text.split() if w.lower().strip(",.!?") not in vocab.fillers]
    s = " ".join(words)
    s = re.sub(r"\s+([,.!?;:])", r"\1", s)
    return s.strip()
