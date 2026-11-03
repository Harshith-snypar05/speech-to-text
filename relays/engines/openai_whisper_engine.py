import asyncio

import numpy as np
import whisper

from core.transcript_manager import collapse_repetition
from engines.base_engine import TranscriptionEngine


class OpenAIWhisperEngine(TranscriptionEngine):
    """In-process openai/whisper. No streaming API (batch-only,
    transcribe() runs on a full array), so this is final-only."""

    supports_partial = False

    def __init__(self, model_name: str = "base.en"):
        self.model = whisper.load_model(model_name)

    @staticmethod
    def _pcm_to_float32(pcm_bytes: bytes) -> np.ndarray:
        return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    async def transcribe_final(self, pcm_bytes: bytes) -> str:
        audio = self._pcm_to_float32(pcm_bytes)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            # No fixed temperature: let Whisper fall back to higher
            # temperatures when the greedy decode looks degenerate (high
            # compression ratio / low confidence) -- that fallback IS the
            # anti-repetition-loop mechanism built into the library.
            # Pinning temperature=0.0 disables it entirely.
            lambda: self.model.transcribe(audio, language="en", fp16=False),
        )
        return collapse_repetition(result.get("text", "").strip())
