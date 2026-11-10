"""Word error rate with a transparent normalizer. No third-party deps.

Normalization (applied to reference AND hypothesis): lowercase, curly
apostrophes -> ', drop everything except letters/digits/apostrophes/spaces,
collapse whitespace. Numbers are NOT converted ("20" != "twenty"): Parakeet
emits digits, so write references the way the model writes them, or accept
that number-heavy clips inflate WER. Keep the rule identical across runs.
"""
import re

import numpy as np

_KEEP = re.compile(r"[^a-z0-9' ]+")


def normalize(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("-", " ")
    return _KEEP.sub(" ", text).split()


def edit_counts(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    """Returns (substitutions, deletions, insertions) from a Levenshtein
    alignment of ref->hyp."""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    d[:, 0] = np.arange(n + 1)
    d[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + cost)
    i, j, s, dele, ins = n, m, 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            s += 0 if ref[i - 1] == hyp[j - 1] else 1
            i, j = i - 1, j - 1
        elif i > 0 and d[i, j] == d[i - 1, j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return s, dele, ins


def wer(reference: str, hypothesis: str) -> dict:
    ref, hyp = normalize(reference), normalize(hypothesis)
    s, d, i = edit_counts(ref, hyp)
    return {"ref_words": len(ref), "sub": s, "del": d, "ins": i, "errors": s + d + i}


def corpus_wer(rows: list[dict], n_boot: int = 1000, seed: int = 0) -> dict:
    """Micro-averaged WER over clips (sum errors / sum ref words) with a
    bootstrap 95% CI resampling clips. With few clips the CI is wide --
    that is the point: report it."""
    if not rows:
        return {"wer": None, "ci95": None, "clips": 0, "ref_words": 0}
    errs = np.array([r["errors"] for r in rows], dtype=float)
    words = np.array([r["ref_words"] for r in rows], dtype=float)
    total_words = words.sum()
    point = float(errs.sum() / total_words) if total_words else None
    ci = None
    if len(rows) >= 5 and total_words:
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, len(rows), size=(n_boot, len(rows)))
        boots = errs[idx].sum(axis=1) / np.maximum(words[idx].sum(axis=1), 1)
        ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
    return {"wer": point, "ci95": ci, "clips": len(rows), "ref_words": int(total_words)}
