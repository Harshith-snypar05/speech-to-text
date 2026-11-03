import asyncio
import tempfile
import wave
from pathlib import Path

from core.transcript_manager import collapse_repetition
from engines.base_engine import TranscriptionEngine


class WhisperCppEngine(TranscriptionEngine):
    """Shells out to whisper.cpp's `whisper-cli` per utterance -- it ships
    no streaming/partial API, so this is final-only."""

    supports_partial = False

    def __init__(self, whisper_cli: Path, model: Path, sample_rate: int, bytes_per_sample: int):
        if not whisper_cli.exists():
            raise SystemExit(f"whisper-cli not found at {whisper_cli}")
        if not model.exists():
            raise SystemExit(f"model not found at {model}")
        self.whisper_cli = whisper_cli
        self.model = model
        self.sample_rate = sample_rate
        self.bytes_per_sample = bytes_per_sample

    def _write_wav(self, path: str, pcm_bytes: bytes):
        with wave.open(path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(self.bytes_per_sample)
            f.setframerate(self.sample_rate)
            f.writeframes(pcm_bytes)

    async def transcribe_final(self, pcm_bytes: bytes) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            self._write_wav(tmp.name, pcm_bytes)
            tmp_path = tmp.name
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.whisper_cli), "-m", str(self.model), "-f", tmp_path, "--no-prints", "-nt",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            return collapse_repetition(stdout.decode("utf-8", errors="replace").strip())
        finally:
            Path(tmp_path).unlink(missing_ok=True)
