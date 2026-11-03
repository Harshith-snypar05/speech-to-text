"""Shared relay tuning constants. All overridable via env vars so a
deployment (or a future Settings-screen-driven client) can tune VAD
sensitivity without editing code -- see STT_* below.
"""
import os

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2

# Below this RMS level a chunk counts as silence.
SILENCE_RMS_THRESHOLD = float(os.environ.get("STT_SILENCE_RMS_THRESHOLD", "0.01"))
# Pause length (seconds of continuous silence) that triggers a flush.
SILENCE_HANG_SECONDS = float(os.environ.get("STT_SILENCE_HANG_SECONDS", "0.6"))
# Ignore blips shorter than this.
MIN_UTTERANCE_SECONDS = float(os.environ.get("STT_MIN_UTTERANCE_SECONDS", "0.3"))
# Force-flush long continuous speech/noise even without a pause -- kept
# short because a long ambiguous chunk is exactly what sends Whisper into
# a repetition loop ("no, no, no, no...").
MAX_UTTERANCE_SECONDS = float(os.environ.get("STT_MAX_UTTERANCE_SECONDS", "8.0"))
# How often engines that support word-level partials re-transcribe the
# in-progress utterance.
PARTIAL_CYCLE_SECONDS = float(os.environ.get("STT_PARTIAL_CYCLE_SECONDS", "0.5"))
# Final transcription must complete within this long on disconnect, or
# it's abandoned rather than hanging session cleanup forever.
FINAL_FLUSH_TIMEOUT_SECONDS = float(os.environ.get("STT_FINAL_FLUSH_TIMEOUT_SECONDS", "10.0"))
