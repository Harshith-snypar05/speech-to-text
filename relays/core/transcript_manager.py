"""Collapses degenerate repetition Whisper-family models sometimes produce
on long/ambiguous audio (e.g. "no, no, no, no..." or "a little bit of a
little bit of..."). Shared by all three engines since they're all Whisper
derivatives and can hallucinate the same way.
"""
import re

# Catches runs of an n-word phrase repeated 3+ times in a row. Smallest
# unit size first and to a fixpoint, so "no, no, no" (1-word unit) fully
# collapses before a larger unit like "no, no" gets a chance to lock in
# and only partially collapse it.
_REPEAT_RES = [
    re.compile(r'\b(' + r'\w+' + (r'[\s,]+\w+' * (n - 1)) + r')\b(?:[\s,]+\1\b){2,}', re.IGNORECASE)
    for n in (1, 2, 3, 4)
]


def collapse_repetition(text: str) -> str:
    for pattern in _REPEAT_RES:
        prev = None
        while prev != text:
            prev = text
            text = pattern.sub(r'\1', text)
    return text
