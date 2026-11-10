"""Spoken numbers -> digits for refined transcript lines ("seven hundred and eighty one" -> "781",
"nine zero one four" -> "9014", "two sixty two" -> "262").

Conservative on purpose: a run of number words is converted only when it parses cleanly; anything odd is left as the
words the model produced. A lone single digit word ("one", "five") is never converted ("one of them", "five minutes"
stay as written); teens/tens ("fifteen", "twenty") and any multi-word run are converted.
Pure string work, microseconds per line; it is applied to the refined text only, never on the live path.
"""
import re

_DIGITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"thousand": 1000, "million": 1_000_000}
_REPEAT = {"double": 2, "triple": 3}
_NUMWORDS = set(_DIGITS) | set(_TEENS) | set(_TENS) | set(_SCALES) | {"hundred"}
_TOKEN = re.compile(r"[A-Za-z']+|[^A-Za-z']+")
_JOIN = re.compile(r"^[ \t-]+$")  # what may sit between the words of one number


def _below_1000(w: list[str], i: int):
    """Parse [digit hundred] [tens [digit] | teen | digit] starting at i. Returns (value, next_index) or None."""
    start, v = i, 0
    if i < len(w) and w[i] in _DIGITS and i + 1 < len(w) and w[i + 1] == "hundred":
        v, i = _DIGITS[w[i]] * 100, i + 2
        if i + 1 < len(w) and w[i] == "and" and w[i + 1] in (_DIGITS.keys() | _TEENS.keys() | _TENS.keys()):
            i += 1
    if i < len(w) and w[i] in _TENS:
        v += _TENS[w[i]]
        i += 1
        if i < len(w) and w[i] in _DIGITS and _DIGITS[w[i]] > 0:
            v += _DIGITS[w[i]]
            i += 1
    elif i < len(w) and w[i] in _TEENS:
        v, i = v + _TEENS[w[i]], i + 1
    elif i < len(w) and w[i] in _DIGITS and (v == 0 or _DIGITS[w[i]] > 0):
        v, i = v + _DIGITS[w[i]], i + 1
    return (v, i) if i > start else None


def _cardinal(w: list[str]):
    """Run containing hundred/thousand/million -> int, or None when it is not a well-formed cardinal."""
    total, i, last_scale = 0, 0, 10**9
    while i < len(w):
        part = _below_1000(w, i)
        if part is None:
            return None
        val, i = part
        if i < len(w) and w[i] in _SCALES:
            if _SCALES[w[i]] >= last_scale:
                return None
            total += val * _SCALES[w[i]]
            last_scale = _SCALES[w[i]]
            i += 1
            if i < len(w) and w[i] == "and":
                i += 1
        else:
            total += val
            if i != len(w):
                return None
    return total


def _groups(w: list[str]):
    """Run without scale words -> digit string, or None. Digit-by-digit speech joins up ("nine zero one" -> "901")."""
    out, i, n_tokens = [], 0, 0
    while i < len(w):
        t = w[i]
        if t in _REPEAT:
            if i + 1 >= len(w) or w[i + 1] not in _DIGITS:
                return None
            out.append((str(_DIGITS[w[i + 1]]) * _REPEAT[t], True))
            i += 2
        elif t in _TENS:
            v, i = _TENS[t], i + 1
            if i < len(w) and w[i] in _DIGITS and _DIGITS[w[i]] > 0:
                v, i = v + _DIGITS[w[i]], i + 1
            out.append((str(v), False))
        elif t in _TEENS:
            out.append((str(_TEENS[t]), False))
            i += 1
        elif t in _DIGITS:
            out.append((str(_DIGITS[t]), True))
            i += 1
        else:
            return None
        n_tokens += 1
    if len(out) == 1 and out[0][1] and len(out[0][0]) == 1:
        return None  # a lone "one"/"five": leave as a word
    return "".join(s for s, _ in out)


def _convert(words: list[str]):
    low = [x.lower() for x in words]
    if any(x == "hundred" or x in _SCALES for x in low):
        v = _cardinal(low)
        return None if v is None else str(v)
    return _groups(low)


def to_digits(text: str) -> str:
    toks = _TOKEN.findall(text or "")
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        starts = t.lower() in _NUMWORDS or t.lower() in _REPEAT
        if not starts:
            out.append(t)
            i += 1
            continue
        # extend the run over number words joined by plain spaces/hyphens ("and" only after hundred/thousand/million)
        run, j = [t], i + 1
        while j + 1 < len(toks) and _JOIN.match(toks[j]):
            nxt = toks[j + 1].lower()
            if nxt in _NUMWORDS or nxt in _REPEAT:
                run.append(toks[j + 1])
                j += 2
            elif nxt == "and" and run[-1].lower() in ("hundred", "thousand", "million") and j + 3 < len(toks) \
                    and _JOIN.match(toks[j + 2]) and toks[j + 3].lower() in _NUMWORDS:
                run.extend([toks[j + 1], toks[j + 3]])
                j += 4
            else:
                break
        conv = _convert(run)
        if conv is None:
            out.extend(toks[i:j])
        else:
            out.append(conv)
        i = j
    return "".join(out)
