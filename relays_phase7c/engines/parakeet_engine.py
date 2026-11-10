import asyncio
import tempfile
import wave
from pathlib import Path

from core.transcript_manager import collapse_repetition
from engines.base_engine import TranscriptionEngine


class ParakeetEngine(TranscriptionEngine):
    """Shells out to whisper.cpp's `parakeet-cli` (native Parakeet TDT
    support) per utterance. No streaming/partial API -- final-only.
    parakeet-cli does expose per-token timing with word_start markers
    (enough to reconstruct word-level partials), but re-invoking a CLI
    subprocess every PARTIAL_CYCLE_SECONDS would add real subprocess-spawn
    and model-reload overhead -- see ParakeetNativeEngine
    (parakeet_native_engine.py) for the in-process version that doesn't
    have that problem and does support partials; this subprocess version
    exists only as a fallback for when the shared library required by
    ParakeetNativeEngine hasn't been built.
    """

    supports_partial = False

    def __init__(self, parakeet_cli: Path, model: Path, sample_rate: int, bytes_per_sample: int):
        if not parakeet_cli.exists():
            raise SystemExit(f"parakeet-cli not found at {parakeet_cli}")
        if not model.exists():
            raise SystemExit(f"model not found at {model}")
        self.parakeet_cli = parakeet_cli
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
                str(self.parakeet_cli), "-m", str(self.model), "-f", tmp_path, "-np",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            lines = [l for l in stdout.decode("utf-8", errors="replace").strip().split("\n")
                     if l and not l.startswith("read_audio_data")]
            text = lines[-1] if lines else ""
            return collapse_repetition(text.strip())
        finally:
            Path(tmp_path).unlink(missing_ok=True)
