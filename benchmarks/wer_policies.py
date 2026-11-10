"""Declared, separate WER normalization policies (Phase 4, Task 3).

DIAGNOSTIC ONLY. Normalized WER does NOT represent improved recognition
accuracy: the transcript is identical, only the scoring convention differs.
It estimates how much of the raw WER comes from number formatting (policy C)
or compound spelling (policy D) rather than from different words. The raw
WER (wer.normalize, policy A) is the baseline and is never replaced.

Policies (identical to Phase 3 `svarah_error_analysis.py`, which is final):
  raw      A: wer.normalize (lowercase, strip punctuation, no number mapping)
  number   C: both sides get a pre-pass (1,000 -> 1000; 3.5 -> 3 point 5;
              % -> percent); runs of >=2 digits / digit words become one digit
              string; runs of number words become one integer
              (units, teens, tens, hundred, thousand, lakh, crore, million;
              'and' only between number words)
  compound D: C plus a symmetric join of adjacent tokens `x y` -> `xy` when `xy`
              (length >= 4, not digits) exists on the other side
Filler removal (Phase 3 policy E) is NOT implemented here: not approved.
"""
import re

from wer import edit_counts, normalize

UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000,
          "million": 1000000, "crore": 10000000, "crores": 10000000}
DIGITWORDS = {w: UNITS[w] for w in "zero one two three four five six seven eight nine".split()}
NUMW = set(UNITS) | set(TENS) | set(SCALES)

DISCLAIMER = ("Normalized WER is a diagnostic estimate of formatting-related scoring differences. "
              "It does not represent improved recognition accuracy; the transcripts are unchanged. "
              "Raw WER (wer_raw) is the baseline.")


def pre_text(t: str) -> str:
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = re.sub(r"(?<=\d)\.(?=\d)", " point ", t)
    return t.replace("%", " percent ")


def parse_cardinal(run: list[str]) -> str:
    total, cur = 0, 0
    for w in run:
        if w == "and":
            continue
        if w in UNITS:
            cur += UNITS[w]
        elif w in TENS:
            cur += TENS[w]
        elif w == "hundred":
            cur = max(cur, 1) * 100
        else:
            total += max(cur, 1) * SCALES[w]
            cur = 0
    return str(total + cur)


def num_norm(toks: list[str]) -> list[str]:
    out, i, n = [], 0, len(toks)
    isd = lambda t: (len(t) == 1 and t.isdigit()) or t in DIGITWORDS  # noqa: E731
    dval = lambda t: t if t.isdigit() else str(DIGITWORDS[t])  # noqa: E731
    while i < n:
        t = toks[i]
        if isd(t):
            j = i
            while j < n and isd(toks[j]):
                j += 1
            if j - i >= 2:
                out.append("".join(dval(x) for x in toks[i:j]))
                i = j
                continue
        if t in NUMW:
            j = i
            while j < n and (toks[j] in NUMW or (toks[j] == "and" and j + 1 < n and toks[j + 1] in NUMW and j > i)):
                j += 1
            out.append(parse_cardinal(toks[i:j]))
            i = j
            continue
        out.append(t)
        i += 1
    return out


def _join(toks: list[str], other: list[str]) -> list[str]:
    o, res, i = set(other), [], 0
    while i < len(toks):
        if i + 1 < len(toks) and not toks[i].isdigit() and not toks[i + 1].isdigit():
            j = toks[i] + toks[i + 1]
            if len(j) >= 4 and j in o and j not in toks:
                res.append(j)
                i += 2
                continue
        res.append(toks[i])
        i += 1
    return res


def policy_tokens(reference: str, hypothesis: str) -> dict:
    """{'raw': (ref, hyp), 'number': (ref, hyp), 'compound': (ref, hyp)} token lists."""
    raw = (normalize(reference), normalize(hypothesis))
    rc, hc = num_norm(normalize(pre_text(reference))), num_norm(normalize(pre_text(hypothesis)))
    r1 = _join(rc, hc)
    h1 = _join(hc, r1)
    r2 = _join(r1, h1)
    return {"raw": raw, "number": (rc, hc), "compound": (r2, h1)}


def _score(ref: list[str], hyp: list[str]) -> dict:
    s, d, i = edit_counts(ref, hyp)
    return {"ref_words": len(ref), "sub": s, "del": d, "ins": i, "errors": s + d + i}


def policy_wer(reference: str, hypothesis: str) -> dict:
    """Per-clip scores under each policy: {'raw': {...}, 'number': {...}, 'compound': {...}}."""
    return {k: _score(*v) for k, v in policy_tokens(reference, hypothesis).items()}
