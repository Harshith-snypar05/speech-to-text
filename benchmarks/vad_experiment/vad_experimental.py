"""EXPERIMENTAL adaptive-threshold VAD. NOT used by any relay. Production
`relays/core/audio_processor.py` is imported unmodified and subclassed here;
only the speech/silence classification differs. Flush rule (hang, min,
max cap) is inherited verbatim.

Design (answers the failure modes found in ADAPTIVE_NOISE_FLOOR_REPORT.md):

1. First-second initialisation. Production starts its floor at the fixed
   threshold, so the effective threshold is 2.5x too high from chunk one and
   can never rise to meet loud noise. Here the floor is seeded from a low
   percentile of the first `init_s` seconds. During init, chunks are
   classified with the plain fixed threshold `lo` (== baseline behaviour).
2. Floor tracking by a LOW PERCENTILE of recent RMS (window `window_s`), not
   by an EMA fed only with chunks already judged silent. Noise above the
   current threshold therefore still moves the floor. Falls are immediate;
   rises are rate-limited (`up_rate` per second) so a sudden loud event or a
   long run of speech cannot yank the threshold up.
3. Threshold = clamp(mult * floor, lo, hi_cap).
4. Speech-level cap (the quiet-speech guard): hi_cap = hi_frac * median RMS
   of recently detected speech chunks. The threshold can never climb to a
   large fraction of the speaker's own level, so a quiet speaker is not
   absorbed into the noise estimate. If SNR is too low for this to leave the
   noise below the threshold, the VAD degrades to "noise looks like speech"
   (cap flushes), which is reported as a failure case, never hidden.
5. Hysteresis: once in speech, a chunk stays speech down to `exit_ratio` x
   threshold, so soft syllables / word dips don't accumulate silence.

`lo` is the absolute minimum threshold. 0.01 (production's fixed value) is the
conservative setting; a lower `lo` additionally recovers quiet speakers in
quiet rooms where the fixed threshold itself discards speech.
"""
import importlib.util
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_AP = Path(__file__).resolve().parents[2] / "relays" / "core" / "audio_processor.py"
_spec = importlib.util.spec_from_file_location("ap_prod", _AP)
ap_prod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ap_prod)
UtteranceBuffer = ap_prod.UtteranceBuffer
pcm_bytes_to_float32 = ap_prod.pcm_bytes_to_float32


@dataclass(frozen=True)
class VadParams:
    lo: float = 0.01          # absolute minimum threshold
    mult: float = 3.0         # threshold = mult * floor
    hi_frac: float = 0.4      # threshold <= hi_frac * median recent speech RMS
    init_s: float = 1.0
    percentile: float = 20.0  # floor = this percentile of the recent window
    window_s: float = 4.0
    up_rate: float = 1.15     # max floor growth factor per second
    exit_ratio: float = 0.5   # hysteresis: speech persists down to exit_ratio*threshold
    speech_hist_s: float = 6.0
    gate_speech: bool = True  # v2: only chunks >= mult*floor feed the speech-level estimate (False = v1)


class AdaptiveVadBuffer(UtteranceBuffer):
    def __init__(self, sample_rate, bytes_per_sample, silence_rms_threshold,
                 silence_hang_seconds, min_utterance_seconds, max_utterance_seconds,
                 params: VadParams = VadParams(), **_ignored):
        super().__init__(sample_rate, bytes_per_sample, silence_rms_threshold,
                         silence_hang_seconds, min_utterance_seconds, max_utterance_seconds)
        self.p = params
        self._hist = deque()          # recent chunk rms (all)
        self._speech_hist = deque()   # recent rms of chunks judged speech
        self._elapsed = 0.0
        self._floor = None
        self._in_speech = False
        self.last_is_speech = False
        self.last_threshold = params.lo

    def _threshold(self) -> float:
        p = self.p
        if self._floor is None:
            return p.lo
        thr = max(p.lo, p.mult * self._floor)
        if len(self._speech_hist) >= 3:
            thr = min(thr, max(p.lo, p.hi_frac * float(np.median(self._speech_hist))))
        return thr

    def add_chunk(self, message: bytes) -> bool:
        samples = pcm_bytes_to_float32(message)
        if len(samples) == 0:
            return False
        p = self.p
        chunk_s = len(samples) / self.sample_rate
        rms = float(np.sqrt(np.mean(samples ** 2)))
        self.buffer.extend(message)

        thr = self._threshold()
        enter = thr
        stay = thr * p.exit_ratio if self._floor is not None else thr
        is_speech = rms >= (stay if self._in_speech else enter)
        self._in_speech = is_speech
        self.last_is_speech, self.last_threshold = is_speech, thr

        # history / floor update
        self._elapsed += chunk_s
        self._hist.append(rms)
        while len(self._hist) * chunk_s > p.window_s:
            self._hist.popleft()
        admit = is_speech and (not p.gate_speech or (self._floor is not None and rms >= p.mult * self._floor))
        if admit:
            self._speech_hist.append(rms)
            while len(self._speech_hist) * chunk_s > p.speech_hist_s:
                self._speech_hist.popleft()
        if self._elapsed >= p.init_s:
            target = float(np.percentile(self._hist, p.percentile))
            if self._floor is None:
                self._floor = target
            elif target > self._floor:
                self._floor = min(target, self._floor * (p.up_rate ** chunk_s))
            else:
                self._floor = target

        if is_speech:
            self.silence_s = 0.0
            self.speech_s += chunk_s
        else:
            self.silence_s += chunk_s
        total_s = len(self.buffer) / (self.sample_rate * self.bytes_per_sample)
        return ((self.silence_s >= self.silence_hang_seconds and self.speech_s >= self.min_utterance_seconds)
                or total_s >= self.max_utterance_seconds)

    def take(self) -> bytes:
        # Keep the learned floor / speech level across utterances (like production).
        return super().take()
