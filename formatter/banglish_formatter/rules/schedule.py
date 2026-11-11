"""Schedule / reminder rule: "akash er sathe meeting ache bikal 4 tay" -> "Meeting with Akash - 4:00 PM"."""
from __future__ import annotations

from dataclasses import dataclass

from ..numbers import find_numbers
from ..text import Token, is_clock
from ..vocab import Vocab
from .base import Candidate, cap_first, match_phrase


@dataclass
class _Time:
    start: int
    end: int
    hour: float
    minute: int
    score: int
    ampm: str | None = None  # explicit "am" / "pm" next to the number


def _find_times(tokens: list[Token], vocab: Vocab) -> list[_Time]:
    lows = [t.low for t in tokens]
    n = len(tokens)
    out: list[_Time] = []

    def ampm_at(k):
        if k < n and lows[k] in vocab.am_words:
            return "am"
        if k < n and lows[k] in vocab.pm_words:
            return "pm"
        return None

    def preceded_by_period(k):
        p = k - 1
        while p >= 0 and lows[p] in vocab.time_particles:
            p -= 1
        return p >= 0 and lows[p] in vocab.periods

    for i, tok in enumerate(tokens):
        clock = is_clock(tok)
        if clock:
            h, m = clock
            ap = ampm_at(i + 1)
            out.append(_Time(i, i + 1 + bool(ap), h, m, 3, ap))

    spans = find_numbers(tokens, vocab)
    starts = {s.start: s for s in spans}
    for s in spans:
        if is_clock(tokens[s.start]):
            continue
        k, end, score, minute = s.end, s.end, 0, 0
        if k < n and lows[k] in vocab.time_classifiers:
            score = 1 if lows[k] == "ta" else 2
            end = k + 1
            m = end
            if m < n and lows[m] in vocab.past_words:
                m += 1
            ms = starts.get(m)
            after = lows[ms.end] if ms and ms.end < n else None
            # "9 tay 2 ta class" / "9 tay 2 kg alu": a count or quantity, not minutes
            counted = after in vocab.currency or (after in vocab.quantity_units and after not in vocab.minute_words)
            if ms and not ms.fractional and float(ms.value).is_integer() and 0 <= ms.value < 60 and not counted:
                minute, end = int(ms.value), ms.end
                if end < n and lows[end] in vocab.minute_words:
                    end += 1
                score = max(score, 2)
        if score == 1 and minute == 0 and end < n and not tokens[end].is_sep \
                and lows[end] not in vocab.time_particles and lows[end] not in vocab.am_words | vocab.pm_words:
            score = 0  # "3 ta class" = three classes, not 3 o'clock
        ap = ampm_at(end)
        if ap:
            end += 1
            score = 3
        if preceded_by_period(s.start):
            score = max(score, 3 if score else 2)
        elif s.start > 0 and lows[s.start - 1] == "at" and score == 0:
            score = 1
        if score == 0:
            continue
        hour = s.value
        if s.fractional:
            whole = int(hour)
            minute = round((hour - whole) * 60)
            hour = whole or 12  # "paune 1" = 12:45 on a 12-hour clock
        if not float(hour).is_integer() or not 0 <= hour <= 24:
            continue
        out.append(_Time(s.start, end, hour, minute, score, ap))
    return out


def _resolve(hour: int, minute: int, ampm: str | None, period: str | None, notes: list[str]):
    """Returns (12-hour hour, "AM"/"PM", explicit?)."""
    if hour == 24:
        hour = 0
    if hour >= 13 or hour == 0:
        suffix = "PM" if hour >= 12 else "AM"
        return (hour - 12 if hour > 12 else 12), suffix, True
    if ampm:
        return hour, ampm.upper(), True
    if period == "am":
        return hour, ("PM" if hour == 12 else "AM"), True
    if period == "noon":
        return hour, ("AM" if hour == 11 else "PM"), True
    if period == "pm":
        return hour, "PM", True
    if period == "night":
        if hour == 12:
            notes.append("rat 12 read as midnight (12 AM)")
            return 12, "AM", True
        if hour <= 4:
            notes.append(f"rat {hour} read as after midnight ({hour} AM)")
            return hour, "AM", True
        return hour, "PM", True
    guess = "AM" if 7 <= hour <= 11 else "PM"
    notes.append(f"AM/PM not said; guessed {guess}")
    return hour, guess, False


def _join_names(name_tokens: list[Token], vocab: Vocab) -> str:
    groups, cur = [], []
    for t in name_tokens:
        if t.low in vocab.conjunctions or t.low == "o":
            if cur:
                groups.append(cur)
            cur = []
        else:
            cur.append(cap_first(t.text))
    if cur:
        groups.append(cur)
    names = [" ".join(g) for g in groups]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _name_span(lows: list[str], removed: list[bool], start: int, step: int, vocab: Vocab) -> list[int]:
    """Indices of the name next to "er sathe" (step=-1, reading backwards) or after "with" (step=1)."""
    idx, p, n = [], start, len(lows)
    joiners = vocab.conjunctions | {"o"}
    while 0 <= p < n and not removed[p] and lows[p] not in vocab.event_words and len(idx) < 5:
        if lows[p] in vocab.name_stop:
            q = p + step
            joins = idx and lows[p] in joiners and 0 <= q < n and not removed[q] \
                and lows[q] not in vocab.name_stop and lows[q] not in vocab.event_words
            if not joins:
                break
        idx.append(p)
        p += step
    return sorted(idx)


def schedule_rule(tokens: list[Token], vocab: Vocab) -> Candidate | None:
    if not tokens:
        return None
    lows = [t.low for t in tokens]
    n = len(tokens)
    notes: list[str] = []
    times = _find_times(tokens, vocab)
    removed = [False] * n
    has_period_word = any(low in vocab.periods for low in lows)

    if times:
        best = max(times, key=lambda t: (t.score, -t.start))
        other_times = [t for t in times if t.score >= 2 and (t.end <= best.start or t.start >= best.end)]
        for k in range(best.start, best.end):
            removed[k] = True
        if best.start > 0 and lows[best.start - 1] == "at":
            removed[best.start - 1] = True
        k = best.end
        while k < n and lows[k] in ("e", "te"):
            removed[k] = True
            k += 1
    else:
        best, other_times = None, []

    # time-of-day words (and a particle right after them) are folded into the time
    period, period_dist = None, n + 1
    for i, low in enumerate(lows):
        if low in vocab.periods:
            dist = abs(i - best.start) if best else 0
            if dist < period_dist:
                period, period_dist = vocab.periods[low], dist
            removed[i] = True
            j = i + 1
            while j < n and lows[j] in vocab.time_particles and not removed[j]:
                removed[j] = True
                j += 1

    if best is None:
        if period == "noon":  # "dupure meeting" -> 12:00 PM
            best = _Time(0, 0, 12, 0, 1)
            notes.append("no hour said; dupur read as 12:00 PM")
        else:
            return None

    hour, suffix, explicit = _resolve(int(best.hour), best.minute, best.ampm, period, notes)
    if best.hour >= 13:
        notes.append("24-hour time converted")
    time_str = f"{hour}:{best.minute:02d} {suffix}"

    # days and dates ("kal", "15 tarikh")
    day_parts = []
    for i, low in enumerate(lows):
        if removed[i]:
            continue
        if low in vocab.day_words:
            removed[i] = True
            day_parts.append((i, tokens[i].text))
        elif low in vocab.date_words and i > 0 and lows[i - 1].isdigit() and not removed[i - 1]:
            removed[i] = removed[i - 1] = True
            day_parts.append((i - 1, f"{tokens[i - 1].text} {tokens[i].text}"))
            if i + 1 < n and lows[i + 1] in ("e", "te"):
                removed[i + 1] = True

    # reminder phrases
    reminder = False
    i = 0
    while i < n:
        k = match_phrase(lows, i, vocab.reminder_phrases)
        if k:
            reminder = True
            for j in range(i, i + k):
                removed[j] = True
            i += k
        else:
            i += 1

    for i, low in enumerate(lows):
        if low in vocab.schedule_strip or tokens[i].is_sep or low in vocab.currency or low in vocab.fillers:
            removed[i] = True

    event = any(low in vocab.event_words for low in lows)

    # "<name> er sathe <rest>"
    title = ""
    with_at = None
    for i in range(n):
        if removed[i]:
            continue
        k = match_phrase(lows, i, vocab.with_phrases)
        if k:
            with_at = (i, i + k)
            break
    if with_at:
        a, b = with_at
        english = lows[a] == "with"
        name_idx = _name_span(lows, removed, b if english else a - 1, 1 if english else -1, vocab)
        # possessive glued to the name: "akasher sathe"
        name_tokens = [tokens[k] for k in name_idx]
        if name_tokens and lows[a] != "er" and lows[a] != "r" and name_tokens[-1].low.endswith("er") \
                and len(name_tokens[-1].text) > 4:
            name_tokens[-1] = Token(name_tokens[-1].text[:-2])
        if english:  # "meeting with boss": the name follows, the event comes before
            skip = set(name_idx) | set(range(a, b))
            before = []
            after = [tokens[k].text for k in range(n) if not removed[k] and k not in skip]
        else:
            before = [tokens[k].text for k in range(name_idx[0] if name_idx else a) if not removed[k]]
            after = [tokens[k].text for k in range(b, n) if not removed[k]]
        names = _join_names(name_tokens, vocab)
        event_part, extra = (after, before) if after else (before, [])
        if names and event_part:
            title = f"{cap_first(' '.join(event_part))} with {names}"
            if extra:
                title += ", " + " ".join(extra)
        else:
            with_at = None
    if not title:
        kept = [tokens[i].text for i in range(n) if not removed[i]]
        title = cap_first(" ".join(kept))
    if not title:
        if not reminder:
            return None
        title = "Reminder"

    day = " ".join(text for _, text in sorted(day_parts))
    when = f"{day} {time_str}" if day else time_str

    conf = 0.5
    if event or reminder:
        conf += 0.25
    if explicit:
        conf += 0.15
    if with_at:
        conf += 0.05
    if best.score <= 1 and not has_period_word:
        conf -= 0.1
    # one note holds one time and no money; leave mixed sentences to the caller's fallback
    if best.score and other_times:
        conf = min(conf, 0.4)
        notes.append("more than one time mentioned")
    if any(low in vocab.currency for low in lows):
        conf = min(conf, 0.4)
        notes.append("sentence also mentions money")
    return Candidate("schedule", [f"{title} - {when}"], round(min(conf, 0.97), 2), notes)
