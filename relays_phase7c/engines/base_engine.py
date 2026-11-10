"""Common interface every STT engine backend implements. Session
lifecycle, VAD buffering, and broadcast are shared (core/); only the
actual inference call is engine-specific, wired in here. Engines are NOT
forced into identical inference strategies -- whisper.cpp still shells
out per-utterance, openai/whisper still does in-process whole-utterance
decoding, faster-whisper still does word-level partial decoding. Only the
shape of "how a session calls into an engine" is shared.
"""
from abc import ABC, abstractmethod


class TranscriptionEngine(ABC):
    #: Whether this engine can produce word-level partial transcripts for
    #: an in-progress utterance. If False, the session loop never calls
    #: transcribe_partial and the client only ever receives finals.
    supports_partial: bool = False
    #: Engines with a priority scheduler accept speaker_id/deadline/ticket
    #: keyword arguments (Phase 7C) and may return None from
    #: transcribe_partial to signal a backpressure skip.
    supports_scheduling: bool = False

    @abstractmethod
    async def transcribe_final(self, pcm_bytes: bytes) -> str:
        """Transcribe a complete utterance. Raises on failure -- callers
        log and drop the utterance rather than silently losing it."""

    async def transcribe_partial(self, pcm_bytes: bytes) -> list[str]:
        """Return the words transcribed so far for an in-progress
        utterance. Only called when `supports_partial` is True."""
        raise NotImplementedError

    async def shutdown(self) -> None:
        """Release engine resources (subprocess pools, model handles).
        Default no-op; override if the engine holds something to close."""
        return None
