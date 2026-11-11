"""Text normalization before scoring, and key-field (numbers/times) extraction."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

import yaml

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
APOSTROPHES = "'’‘`´"


def has_bengali(text: str) -> bool:
    return bool(BENGALI_RE.search(text or ""))


def script_of(ch: str) -> str:
    """'LATIN', 'BENGALI', 'DEVANAGARI', 'ARABIC', ... for a letter; '' for anything else."""
    if not (ch.isalpha() or unicodedata.category(ch).startswith("M")):
        return ""
    if ord(ch) < 128:
        return "LATIN"
    return unicodedata.name(ch, "UNKNOWN").split()[0]


def has_non_latin(text: str) -> bool:
    return any(script_of(c) not in ("", "LATIN") for c in (text or ""))


def main_script(text: str) -> str:
    counts = Counter(s for s in map(script_of, text or "") if s)
    return counts.most_common(1)[0][0].title() if counts else "Empty"


def _basic(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "").lower().translate(BN_DIGITS)
    t = re.sub(r"(?<=\d),(?=\d)", "", t)  # 1,500 -> 1500 ; 1,00,000 -> 100000
    for a in APOSTROPHES:
        t = t.replace(a, "")
    return t


def _strip_punct(text: str, keep_numeric_sep: bool = False) -> str:
    out = []
    for i, ch in enumerate(text):
        cat = unicodedata.category(ch)
        if cat[0] in "PS" or ch in "\u0964\u0965":  # incl. Bengali dari
            if (keep_numeric_sep and ch in ":." and 0 < i < len(text) - 1
                    and text[i - 1].isdigit() and text[i + 1].isdigit()):
                out.append(ch)
            else:
                out.append(" ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())


class Normalizer:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        variants = {str(k).lower().strip(): str(v).lower().strip()
                    for k, v in (cfg.get("variants") or {}).items()}
        self.variants = variants
        if variants:
            keys = sorted(variants, key=len, reverse=True)
            self._variant_re = re.compile(
                r"(?<!\S)(" + "|".join(re.escape(k) for k in keys) + r")(?!\S)")
        else:
            self._variant_re = None
        kf = cfg.get("key_fields") or {}
        self.number_words = {str(k).lower(): int(v) for k, v in (kf.get("number_words") or {}).items()}
        self.multipliers = {str(k).lower(): int(v) for k, v in (kf.get("multipliers") or {}).items()}
        self.mult_prefixes = dict(self.number_words)
        self.mult_prefixes.update({str(k).lower(): int(v) for k, v in (kf.get("multiplier_prefixes") or {}).items()})
        self.suffixes = sorted((str(s).lower() for s in (kf.get("suffixes") or [])), key=len, reverse=True)
        self.time_words = {str(k).lower(): int(v) for k, v in (kf.get("time_words") or {}).items()}

    @classmethod
    def from_file(cls, path) -> "Normalizer":
        p = Path(path)
        if not p.exists():
            return cls({})
        return cls(yaml.safe_load(p.read_text(encoding="utf-8")) or {})

    def apply_variants(self, text: str) -> str:
        if not self._variant_re:
            return text
        return self._variant_re.sub(lambda m: self.variants[m.group(1)], text)

    def normalize(self, text: str) -> str:
        """lowercase, strip punctuation, collapse spaces, apply spelling-variant map."""
        return self.apply_variants(_strip_punct(_basic(text)))

    # ---------------- key fields ----------------
    def _lookup(self, word: str):
        """Return ('num', v) / ('mult', v) / ('numult', (n, m)) / ('time', minutes) or None."""
        cands = [word] + [word[: -len(s)] for s in self.suffixes if word.endswith(s) and len(word) > len(s)]
        for w in cands:
            if w in self.number_words:
                return ("num", str(self.number_words[w]))
            if w in self.multipliers:
                return ("mult", self.multipliers[w])
            for mw, mv in self.multipliers.items():  # glued: "atsho", "ponerosho", "dushoto"
                if w.endswith(mw) and w[: -len(mw)] in self.mult_prefixes:
                    return ("numult", (self.mult_prefixes[w[: -len(mw)]], mv))
        if word in self.time_words:
            return ("time", self.time_words[word])
        return None

    def key_fields(self, text: str) -> Counter:
        """All numbers and times in an utterance, canonicalized, as a multiset."""
        t = _strip_punct(_basic(text), keep_numeric_sep=True)
        t = re.sub(r"(?<!\d)(\d{1,2})[:.](\d{2})(?!\d)", r"\1:\2", t)
        t = self.apply_variants(t)
        items = []  # (kind, value)
        for tok in t.split():
            m = re.fullmatch(r"(\d{1,2}):(\d{2})\D*", tok)
            if m:
                items.append(("clock", (int(m.group(1)), int(m.group(2)))))
                continue
            m = re.fullmatch(r"(\d+(?:\.\d+)?)\D*", tok)
            if m:
                items.append(("num", m.group(1)))
                continue
            hit = self._lookup(tok)
            if hit is None:
                items.append(("word", tok))
            elif hit[0] == "numult":
                items.append(("num", str(hit[1][0])))
                items.append(("mult", hit[1][1]))
            else:
                items.append(hit)

        fields: list[str] = []
        i = 0
        while i < len(items):
            kind, val = items[i]
            if kind == "time" and i + 1 < len(items) and items[i + 1][0] == "num" and items[i + 1][1].isdigit():
                h, mins = int(items[i + 1][1]), val
                if mins < 0:
                    h, mins = (h - 1) % 12 or 12, 60 + mins
                fields.append(f"{h}:{mins:02d}")
                i += 2
                continue
            if kind == "clock":
                h, mins = val
                fields.append(str(h) if mins == 0 else f"{h}:{mins:02d}")
                i += 1
                continue
            if kind in ("num", "mult"):
                j = i
                run = []
                while j < len(items) and items[j][0] in ("num", "mult"):
                    run.append(items[j])
                    j += 1
                fields.extend(self._combine(run))
                i = j
                continue
            i += 1
        return Counter(fields)

    @staticmethod
    def _canon(v: str) -> str:
        if "." in v:
            v = v.rstrip("0").rstrip(".")
        return v if v.startswith("0") and len(v) > 1 and "." not in v else (str(int(v)) if v.isdigit() else v)

    def _combine(self, run):
        has_mult = any(k == "mult" for k, _ in run)
        nums = [v for k, v in run if k == "num"]
        if not has_mult:
            # "01712 345678" / "zero one eight" / "9 9 9" are one number (phone-like).
            if len(nums) > 1 and (nums[0].startswith("0") or all(len(n) == 1 for n in nums)):
                return ["".join(nums)]
            return [self._canon(n) for n in nums]
        out, total, cur, prev = [], 0, 0, None
        for k, v in run:
            if k == "num":
                if prev == "num":  # two bare numbers in a row: close the previous number
                    out.append(str(total + cur))
                    total, cur = 0, 0
                try:
                    cur += float(v) if "." in v else int(v)
                except ValueError:
                    pass
            else:
                if v >= 1000:
                    total += (cur or 1) * v
                    cur = 0
                else:
                    cur = (cur or 1) * v
            prev = k
        val = total + cur
        out.append(str(int(val)) if float(val).is_integer() else str(val))
        return out
