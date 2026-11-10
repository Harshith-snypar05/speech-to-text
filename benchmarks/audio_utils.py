"""WAV helpers shared by the corpus builder and the benchmark client.
16 kHz mono int16 is the relay's wire format (core/config.py)."""
import wave

import numpy as np

SAMPLE_RATE = 16000


def read_wav(path) -> np.ndarray:
    """Returns float32 mono samples in [-1, 1] at 16 kHz (linear-resampled
    if the file is another rate; fine for benchmarking, not for hi-fi)."""
    with wave.open(str(path), "rb") as f:
        rate, ch, width = f.getframerate(), f.getnchannels(), f.getsampwidth()
        raw = f.readframes(f.getnframes())
    if width != 2:
        raise ValueError(f"{path}: only 16-bit PCM WAV supported (got {width * 8}-bit)")
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if rate != SAMPLE_RATE:
        x = resample(x, rate, SAMPLE_RATE)
    return x


def write_wav(path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(x) == 0:
        return x
    n = int(round(len(x) * dst / src))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


def rms_frames(x: np.ndarray, frame_s: float = 0.02) -> np.ndarray:
    n = int(SAMPLE_RATE * frame_s)
    k = len(x) // n
    if k == 0:
        return np.zeros(0)
    return np.sqrt(np.mean(x[: k * n].reshape(k, n) ** 2, axis=1))


def simulate_flushes(x: np.ndarray, chunk_s: float = 0.1, tail_s: float = 1.5, rms_threshold: float = 0.01,
                     hang_s: float = 0.6, min_s: float = 0.3, max_s: float = 8.0,
                     adaptive: bool = False, noise_mult: float = 2.5, alpha: float = 0.1) -> list[dict]:
    """Replays relays/core/audio_processor.UtteranceBuffer's flush rule over
    the clip (plus the trailing silence the bench sends), chunk by chunk, so
    ground-truth utterances match what the relay will actually flush --
    including forced splits at the max-utterance cap. Returns
    [{start, end, forced}] in seconds: start = first speech chunk, end = last
    speech chunk end (or the cap time if forced). Keep params equal to the
    relay's STT_* settings."""
    n = int(chunk_s * SAMPLE_RATE)
    x = np.concatenate([x, np.zeros(int(tail_s * SAMPLE_RATE), np.float32)])
    out, total, silence, speech, first, last = [], 0.0, 0.0, 0.0, None, None
    floor = rms_threshold  # mirrors UtteranceBuffer._noise_floor: init = fixed threshold, persists across flushes
    for k in range(0, len(x) - n + 1, n):
        t0 = k / SAMPLE_RATE
        rms = float(np.sqrt(np.mean(x[k:k + n] ** 2)))
        total += chunk_s
        thr = max(rms_threshold, floor * noise_mult) if adaptive else rms_threshold
        if rms < thr:
            silence += chunk_s
            if adaptive:
                floor += alpha * (rms - floor)
        else:
            silence, speech = 0.0, speech + chunk_s
            first = t0 if first is None else first
            last = t0 + chunk_s
        capped = total >= max_s
        if (silence >= hang_s and speech >= min_s) or capped:
            if speech >= min_s:
                out.append({"start": first, "end": (t0 + chunk_s) if capped else last, "forced": capped})
            total = silence = speech = 0.0
            first = last = None
    return out


def find_utterances(x: np.ndarray, rms_threshold: float = 0.01, hang_s: float = 0.6,
                    min_s: float = 0.3, frame_s: float = 0.02) -> list[dict]:
    """Speech segments as the relay's RMS VAD would see them: runs of
    above-threshold frames, merged across pauses shorter than hang_s, dropped
    if shorter than min_s. Returns [{start, end}] in seconds, where `end` is
    the last speech frame (i.e. before the hang silence). Run this on the
    CLEAN source, not the noisy mix, to get ground-truth speech timing."""
    r = rms_frames(x, frame_s)
    speech = r >= rms_threshold
    segs, start, last = [], None, None
    for i, s in enumerate(speech):
        if s:
            if start is None:
                start = i
            elif (i - last) * frame_s > hang_s:
                segs.append((start, last))
                start = i
            last = i
    if start is not None:
        segs.append((start, last))
    return [{"start": a * frame_s, "end": (b + 1) * frame_s}
            for a, b in segs if (b + 1 - a) * frame_s >= min_s]
