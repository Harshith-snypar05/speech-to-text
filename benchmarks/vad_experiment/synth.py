"""Synthetic scenes for VAD experiments. SYNTHETIC ONLY: noises are crude
statistical stand-ins (fan, cafe, street, keyboard), not recordings.

A scene = JFK speech pieces joined by short (0.3 s, must NOT flush) or long
(1.2 s, must flush) pauses, mixed with noise at an ABSOLUTE rms level, with a
speech gain. Ground truth is derived from the clean composition, so it is
independent of gain and noise.
"""
from dataclasses import dataclass
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_utils import SAMPLE_RATE as SR, find_utterances, read_wav  # noqa: E402

JFK = Path(__file__).resolve().parents[2] / "whisper.cpp" / "samples" / "jfk.wav"
CHUNK = 1600  # 100 ms, as the bench / app send
SHORT_GAP, LONG_GAP, TAIL_S = 0.3, 1.2, 2.5
TRUTH_RMS = 0.01  # a gain-1 clean chunk at/above this is "speech" ground truth
ROOM_TONE = 0.002  # always-on faint room noise under every scene


def _pieces():
    x = read_wav(JFK)
    return [x[int(u["start"] * SR):int(u["end"] * SR)] for u in find_utterances(x, hang_s=0.25)]


def _lp(x, a):  # one-pole low-pass
    from scipy.signal import lfilter
    return lfilter([a], [1, a - 1], x)


def make_noise(kind: str, n: int, rms: float, rng) -> np.ndarray:
    t = np.arange(n) / SR
    w = rng.standard_normal(n)
    if kind == "fan":  # steady, low-passed (brown-ish) + blade-pass hum
        x = _lp(w, 0.05) * 4 + 0.15 * np.sin(2 * np.pi * 120 * t)
    elif kind == "cafe":  # babble: several syllable-modulated band-limited voices + clinks
        x = np.zeros(n)
        for _ in range(8):
            mod = 0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(2.5, 6) * t + rng.uniform(0, 6.28))
            x += mod * _lp(rng.standard_normal(n), rng.uniform(0.12, 0.35))
        for k in rng.integers(0, n - 800, size=int(3 * n / SR)):  # clinks
            x[k:k + 800] += 3 * rng.standard_normal(800) * np.exp(-np.arange(800) / 120)
    elif kind == "street":  # rumble + slow vehicle swells + occasional tonal horn
        x = _lp(w, 0.02) * 6
        for c in rng.uniform(0, n / SR, size=max(1, int(n / SR / 4))):
            x += 3 * np.exp(-0.5 * ((t - c) / 0.9) ** 2) * _lp(rng.standard_normal(n), 0.04) * 3
        for c in rng.uniform(0, n / SR, size=max(1, int(n / SR / 6))):
            x += 2 * ((t > c) & (t < c + 0.3)) * np.sin(2 * np.pi * 420 * t)
    elif kind == "keyboard":  # sparse click bursts over a low floor
        x = 0.05 * w
        for c in rng.uniform(0, n / SR, size=int(6 * n / SR)):
            k = int(c * SR)
            m = min(500, n - k)
            x[k:k + m] += 4 * rng.standard_normal(m) * np.exp(-np.arange(m) / 60)
    elif kind == "white":
        x = w
    else:
        raise ValueError(kind)
    x = x - x.mean()
    return (x / (np.sqrt(np.mean(x ** 2)) + 1e-12) * rms).astype(np.float32)


@dataclass
class Scene:
    name: str
    audio: np.ndarray            # float32, what the VAD sees
    truth_speech: np.ndarray     # bool per 100 ms chunk
    groups: list                 # [(S_k, E_k)] seconds: spans that should yield exactly one flush each
    n_chunks: int
    meta: dict


def build_scene(gap_pattern: str, gain: float, noise_kind: str, noise_rms: float,
                lead_s: float, seed: int) -> Scene:
    """gap_pattern: two letters from {S,L} for the gaps between the 3 pieces."""
    rng = np.random.default_rng(seed)
    pcs = _pieces()
    gaps = [SHORT_GAP if c == "S" else LONG_GAP for c in gap_pattern]
    clean, spans, pos = [np.zeros(int(lead_s * SR), np.float32)], [], int(lead_s * SR)
    for i, p in enumerate(pcs):
        spans.append((pos / SR, (pos + len(p)) / SR))
        clean.append(p); pos += len(p)
        if i < len(gaps):
            g = np.zeros(int(gaps[i] * SR), np.float32); clean.append(g); pos += len(g)
    clean.append(np.zeros(int(TAIL_S * SR), np.float32))
    clean = np.concatenate(clean)
    n = (len(clean) // CHUNK) * CHUNK
    clean = clean[:n]
    # truth: gain-1 clean chunks above TRUTH_RMS
    truth = np.sqrt(np.mean(clean.reshape(-1, CHUNK) ** 2, axis=1)) >= TRUTH_RMS
    # groups = pieces joined by short gaps
    groups, cur = [], [spans[0]]
    for i, g in enumerate(gaps):
        if g == SHORT_GAP:
            cur.append(spans[i + 1])
        else:
            groups.append(cur); cur = [spans[i + 1]]
    groups.append(cur)
    g_spans = []
    for grp in groups:
        idx = np.nonzero(truth[int(grp[0][0] * SR) // CHUNK: int(grp[-1][1] * SR) // CHUNK + 1])[0] \
            + int(grp[0][0] * SR) // CHUNK
        g_spans.append((idx[0] * 0.1, (idx[-1] + 1) * 0.1))
    noise = make_noise(noise_kind, n, noise_rms, rng) if noise_rms > 0 else np.zeros(n, np.float32)
    room = ROOM_TONE * rng.standard_normal(n).astype(np.float32)
    audio = np.clip(clean * gain + noise + room, -1, 1).astype(np.float32)
    return Scene(f"{gap_pattern}|g{gain}|{noise_kind}{noise_rms}|lead{lead_s}", audio, truth, g_spans, n // CHUNK,
                 dict(gap_pattern=gap_pattern, gain=gain, noise=noise_kind, noise_rms=noise_rms, lead_s=lead_s,
                      seed=seed))
