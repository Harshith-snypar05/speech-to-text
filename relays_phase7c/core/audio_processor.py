import numpy as np


def pcm_bytes_to_float32(pcm_bytes: bytes) -> np.ndarray:
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


class UtteranceBuffer:
    """VAD-pause-triggered buffering: accumulates raw PCM16 audio, tracks
    how much of it is silence vs speech, and reports when an utterance
    boundary has been reached (a pause after enough speech, or a hard
    time cap) so the caller knows when to flush.
    """

    def __init__(self, sample_rate, bytes_per_sample, silence_rms_threshold,
                 silence_hang_seconds, min_utterance_seconds, max_utterance_seconds,
                 adaptive_noise_floor=False, noise_floor_multiplier=2.5):
        self.sample_rate = sample_rate
        self.bytes_per_sample = bytes_per_sample
        self.silence_rms_threshold = silence_rms_threshold
        self.silence_hang_seconds = silence_hang_seconds
        self.min_utterance_seconds = min_utterance_seconds
        self.max_utterance_seconds = max_utterance_seconds
        self.buffer = bytearray()
        self.silence_s = 0.0
        self.speech_s = 0.0

        # Opt-in (default off): instead of a fixed RMS cutoff, track a
        # slow-moving average of the RMS seen during silence and classify
        # a chunk as speech only once it's noise_floor_multiplier times
        # above that. Off by default because it hasn't been benchmarked
        # against real noisy audio the way the engine comparison was
        # (see engine_benchmark_comparison.pdf) -- the fixed threshold is
        # the proven baseline. This does NOT introduce a VAD model (no
        # Silero, nothing ML-based); it's the same RMS mechanism made
        # adaptive. Silero was tried earlier in this project (see
        # whisper_streaming evaluation) and rejected for causing
        # premature buffer resets from VAD flicker -- this path avoids
        # that failure mode entirely since it's just a threshold, not a
        # separate speech/silence classifier with its own state machine.
        self.adaptive_noise_floor = adaptive_noise_floor
        self.noise_floor_multiplier = noise_floor_multiplier
        self._noise_floor = silence_rms_threshold
        self._noise_floor_alpha = 0.1  # EMA smoothing factor

    def _effective_threshold(self) -> float:
        if not self.adaptive_noise_floor:
            return self.silence_rms_threshold
        # Never adapt below the configured floor -- a near-silent room
        # shouldn't let the threshold collapse to near-zero and start
        # treating faint electrical noise as speech.
        return max(self.silence_rms_threshold, self._noise_floor * self.noise_floor_multiplier)

    def add_chunk(self, message: bytes) -> bool:
        """Feeds one audio chunk in. Returns True if this chunk completed
        an utterance boundary (caller should flush now)."""
        samples = pcm_bytes_to_float32(message)
        if len(samples) == 0:
            return False
        chunk_s = len(samples) / self.sample_rate
        rms = float(np.sqrt(np.mean(samples ** 2)))
        self.buffer.extend(message)
        is_silence = rms < self._effective_threshold()
        if is_silence:
            self.silence_s += chunk_s
            if self.adaptive_noise_floor:
                self._noise_floor += self._noise_floor_alpha * (rms - self._noise_floor)
        else:
            self.silence_s = 0.0
            self.speech_s += chunk_s
        total_s = len(self.buffer) / (self.sample_rate * self.bytes_per_sample)
        return (
            (self.silence_s >= self.silence_hang_seconds and self.speech_s >= self.min_utterance_seconds)
            or total_s >= self.max_utterance_seconds
        )

    def has_pending_utterance(self) -> bool:
        return bool(self.buffer) and self.speech_s >= self.min_utterance_seconds

    def take(self) -> bytes:
        """Snapshots the buffer and resets state. Call once per flush."""
        snapshot = bytes(self.buffer)
        self.buffer = bytearray()
        self.silence_s = 0.0
        self.speech_s = 0.0
        return snapshot
