"""Bengali script -> romanized Banglish, with an on-disk cache.

Whisper with language="bn" sometimes writes Devanagari, Urdu or other scripts instead of Bengali,
so every non-Latin text is romanized ("rules" handles Bengali and Devanagari only).

method "llm"   : asks an OpenAI-compatible LLM (Gemini by default). Default.
method "rules" : offline letter-by-letter transliteration (rough; used as fallback when no API key).
method "none"  : leave the text unchanged.
Text without Bengali letters is never sent anywhere.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import unicodedata

from .textnorm import BN_DIGITS, has_non_latin

RULES_VERSION = "rules-v2"

# Devanagari is laid out like Bengali (+0x80); these have no direct Bengali twin.
_DEVA_SPECIAL = {"व": "ব", "ॉ": "ো", "ॅ": "ে", "ऍ": "এ", "ऑ": "ও", "क़": "ক", "ख़": "খ", "ग़": "গ",
                 "ज़": "জ", "फ़": "ফ", "य़": "য়", "ऩ": "ন", "ऱ": "র", "ऴ": "ল", "ऎ": "এ", "ऒ": "ও",
                 "ॆ": "ে", "ॊ": "ো", "ऌ": "ঌ", "़": "়"}


def _deva_to_bengali(text: str) -> str:
    out = []
    for ch in unicodedata.normalize("NFC", text):
        if "\u0900" <= ch <= "\u097F" and ch not in "\u0964\u0965":
            if ch in _DEVA_SPECIAL:
                out.append(_DEVA_SPECIAL[ch])
                continue
            b = chr(ord(ch) + 0x80)
            out.append(b if unicodedata.name(b, "") else "")
        else:
            out.append(ch)
    return "".join(out)

_CONS = {
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng", "চ": "ch", "ছ": "ch", "জ": "j", "ঝ": "jh",
    "ঞ": "n", "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n", "ত": "t", "থ": "th", "দ": "d",
    "ধ": "dh", "ন": "n", "প": "p", "ফ": "f", "ব": "b", "ভ": "bh", "ম": "m", "য": "j", "র": "r",
    "ল": "l", "শ": "sh", "ষ": "sh", "স": "s", "হ": "h", "\u09dc": "r", "\u09dd": "rh", "\u09df": "y", "ৎ": "t",
}
_VOWELS = {"অ": "o", "আ": "a", "ই": "i", "ঈ": "i", "উ": "u", "ঊ": "u", "ঋ": "ri", "এ": "e",
           "ঐ": "oi", "ও": "o", "ঔ": "ou"}
_MATRAS = {"া": "a", "ি": "i", "ী": "i", "ু": "u", "ূ": "u", "ৃ": "ri", "ে": "e", "ৈ": "oi",
           "ো": "o", "ৌ": "ou", "ৗ": "ou"}
_SIGNS = {"ং": "ng", "ঃ": "h", "ঁ": ""}
_HASANTA = "্"


def _rules_word(word: str) -> str:
    # tokens: (kind, latin, vowel) where kind = 'C' consonant / 'V' vowel / 'X' other
    toks = []
    chars = list(word)
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch in _CONS:
            vowel, j = None, i + 1
            if j < len(chars) and chars[j] == _HASANTA:
                vowel = ""
                if j + 1 < len(chars) and chars[j + 1] in "যব":  # ya-phala / ba-phala: silent
                    j += 1
                    if j + 1 < len(chars) and chars[j + 1] in _MATRAS:
                        vowel = _MATRAS[chars[j + 1]]
                        j += 1
                j += 1
            elif j < len(chars) and chars[j] in _MATRAS:
                vowel = _MATRAS[chars[j]]
                j += 1
            toks.append(["C", _CONS[ch], vowel])
            i = j
        elif ch in _VOWELS:
            toks.append(["V", _VOWELS[ch], None])
            i += 1
        elif ch in _MATRAS:  # vowel sign without a consonant (bad model output)
            toks.append(["V", _MATRAS[ch], None])
            i += 1
        elif ch in _SIGNS:
            toks.append(["X", _SIGNS[ch], None])
            i += 1
        else:
            toks.append(["X", ch, None])
            i += 1
    # inherent vowel 'o': keep word-initially, drop word-finally and in V C _ C V position
    for k, t in enumerate(toks):
        if t[0] != "C" or t[2] is not None:
            continue
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        if nxt is None or nxt[0] == "X":
            t[2] = ""
        elif k == 0:
            t[2] = "o"
        else:
            prev_vowel = toks[k - 1][0] == "V" or (toks[k - 1][0] == "C" and toks[k - 1][2])
            nxt_final = k + 2 >= len(toks) or toks[k + 2][0] == "X"
            next_cv = nxt[0] == "C" and (bool(nxt[2]) or (nxt[2] is None and not nxt_final))
            t[2] = "" if (prev_vowel and next_cv) else "o"
    return "".join(t[1] + (t[2] or "") if t[0] == "C" else t[1] for t in toks)


def rules_romanize(text: str) -> str:
    t = ((_deva_to_bengali(text or "")).replace("\u09a1\u09bc", "\u09dc").replace("\u09a2\u09bc", "\u09dd")
         .replace("\u09af\u09bc", "\u09df").replace("\u0981", "").replace("\u09bc", "").translate(BN_DIGITS))
    t = t.replace("।", ".").replace("॥", ".")
    out, word = [], []
    for ch in t:
        if "\u0980" <= ch <= "\u09FF":
            word.append(ch)
        else:
            if word:
                out.append(_rules_word("".join(word)))
                word = []
            out.append(ch)
    if word:
        out.append(_rules_word("".join(word)))
    return "".join(out)


class Romanizer:
    def __init__(self, cfg: dict, api_cfg: dict, cache_dir: Path):
        self.requested = (cfg.get("method") or "llm").lower()
        self.prompt = cfg.get("prompt") or ""
        self.method = self.requested
        self.note = ""
        self.fallbacks = 0
        self.client = None
        if self.method == "llm":
            from .models.openai_compat import make_client
            client, model, reason = make_client(api_cfg)
            if client is None:
                fb = cfg.get("fallback")
                if fb:
                    self.method = fb
                    self.note = f"LLM romanizer unavailable ({reason}); used '{fb}' instead"
                    print(f"WARNING: {self.note}", file=sys.stderr)
                else:
                    self.method = "unavailable"
                    self.note = f"LLM romanizer unavailable ({reason})"
            else:
                self.client, self.model = client, model
        self.cache_path = Path(cache_dir) / "romanizer_cache.jsonl"
        self.cache = {}
        if self.cache_path.exists():
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                    self.cache[rec["key"]] = rec["out"]
                except (ValueError, KeyError):
                    pass

    @property
    def available(self) -> bool:
        return self.method != "unavailable"

    @property
    def label(self) -> str:
        if self.method == "llm":
            return f"llm:{self.model}"
        return {"rules": "rules", "none": "none"}.get(self.method, self.method)

    @property
    def method_id(self) -> str:
        if self.method == "llm":
            ph = hashlib.sha256(self.prompt.encode()).hexdigest()[:8]
            return f"llm:{self.model}:{ph}"
        return RULES_VERSION if self.method == "rules" else self.method

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.method_id}\n{text}".encode("utf-8")).hexdigest()

    def _store(self, key: str, out: str):
        self.cache[key] = out
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "method": self.method_id, "out": out}, ensure_ascii=False) + "\n")

    def __call__(self, text: str) -> str:
        if self.method == "none" or not has_non_latin(text):
            return text
        key = self._key(text)
        if key in self.cache:
            return self.cache[key]
        if self.method == "rules":
            return rules_romanize(text)  # cheap and deterministic: not cached
        else:
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, temperature=0,
                    messages=[{"role": "system", "content": self.prompt},
                              {"role": "user", "content": text}])
                out = (resp.choices[0].message.content or "").strip()
            except Exception as e:  # noqa: BLE001
                self.fallbacks += 1
                print(f"WARNING: romanizer LLM call failed ({type(e).__name__}); used rules for this clip",
                      file=sys.stderr)
                return rules_romanize(text)  # not cached: retried next run
        self._store(key, out)
        return out
