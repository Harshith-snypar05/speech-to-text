import asyncio

import numpy as np
from faster_whisper import WhisperModel

from core.transcript_manager import collapse_repetition
from engines.base_engine import TranscriptionEngine


class FasterWhisperEngine(TranscriptionEngine):
    """In-process faster-whisper (CTranslate2). Supports word_timestamps,
    which is what makes word-level partial streaming possible -- the real
    win over the other two engines isn't raw throughput, it's this."""

    supports_partial = True

    def __init__(self, model_name: str = "base.en", device: str = "cpu", compute_type: str = "float32"):
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    @staticmethod
    def _pcm_to_float32(pcm_bytes: bytes) -> np.ndarray:
        return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    def _transcribe_final_sync(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(audio, language="en", beam_size=1)
        return collapse_repetition(" ".join(s.text.strip() for s in segments).strip())

    def _transcribe_words_sync(self, audio: np.ndarray) -> list[str]:
        segments, _ = self.model.transcribe(audio, language="en", beam_size=1, word_timestamps=True)
        words = []
        for s in segments:
            for w in s.words:
                words.append(w.word.strip())
        return words

    async def transcribe_final(self, pcm_bytes: bytes) -> str:
        audio = self._pcm_to_float32(pcm_bytes)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_final_sync, audio)

    async def transcribe_partial(self, pcm_bytes: bytes) -> list[str]:
        audio = self._pcm_to_float32(pcm_bytes)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_words_sync, audio)
