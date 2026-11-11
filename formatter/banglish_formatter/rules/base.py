from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    type: str
    lines: list[str]
    confidence: float
    notes: list[str] = field(default_factory=list)

    @property
    def result(self) -> str:
        return "\n".join(self.lines)


def match_phrase(lows: list[str], i: int, phrases) -> int:
    """Length of the longest phrase starting at lows[i], or 0."""
    for phrase in phrases:  # sorted longest first
        if tuple(lows[i:i + len(phrase)]) == phrase:
            return len(phrase)
    return 0


def cap_first(s: str) -> str:
    return s[:1].upper() + s[1:]
