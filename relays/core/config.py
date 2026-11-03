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

# Opt-in: track a slow-moving average of silence RMS and classify speech
# relative to it instead of the fixed SILENCE_RMS_THRESHOLD. Off by
# default -- see UtteranceBuffer's docstring for why. Set to "1" to try it.
ADAPTIVE_NOISE_FLOOR = os.environ.get("STT_ADAPTIVE_NOISE_FLOOR", "0") == "1"
NOISE_FLOOR_MULTIPLIER = float(os.environ.get("STT_NOISE_FLOOR_MULTIPLIER", "2.5"))

# A session (one continuous speaker connection) is proactively ended once
# it's been open this long, regardless of activity -- a safety cap, not a
# UX feature; generous by default so normal sessions never hit it.
SESSION_MAX_DURATION_SECONDS = float(os.environ.get("STT_SESSION_MAX_DURATION_SECONDS", str(4 * 3600)))

# Per-relay-process connection limits -- a crude but real guard against
# unbounded resource growth from a session with many viewers or a flood
# of connections.
MAX_VIEWERS_PER_SESSION = int(os.environ.get("STT_MAX_VIEWERS_PER_SESSION", "50"))
MAX_TOTAL_CONNECTIONS = int(os.environ.get("STT_MAX_TOTAL_CONNECTIONS", "200"))
