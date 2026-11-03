"""ctypes binding against whisper.cpp's compiled libparakeet shared
library -- loads the model ONCE (like faster-whisper) instead of
ParakeetEngine's subprocess-per-utterance approach. Fixes the real
per-utterance latency problem documented in parakeet_engine.py and
parakeet_relay.py: a fresh `parakeet-cli` process reloads the full
668MB model from disk on every single utterance (~350-520ms measured),
even though pure inference on an already-loaded model is only ~130ms.

Requires a shared-library build of whisper.cpp (the vendored fork's
default build is static-only): from whisper.cpp/,
    cmake -B build-shared -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
        -DWHISPER_BUILD_EXAMPLES=OFF -DWHISPER_BUILD_TESTS=OFF
    cmake --build build-shared --target parakeet -j 8
"""
import asyncio
import ctypes
from pathlib import Path

from core.transcript_manager import collapse_repetition
from engines.base_engine import TranscriptionEngine


class _ParakeetContextParams(ctypes.Structure):
    _fields_ = [("use_gpu", ctypes.c_bool), ("gpu_device", ctypes.c_int)]


class _ParakeetFullParams(ctypes.Structure):
    _fields_ = [
        ("strategy", ctypes.c_int),
        ("n_threads", ctypes.c_int),
        ("offset_ms", ctypes.c_int),
        ("duration_ms", ctypes.c_int),
        ("no_context", ctypes.c_bool),
        ("audio_ctx", ctypes.c_int),
        ("new_segment_callback", ctypes.c_void_p),
        ("new_segment_callback_user_data", ctypes.c_void_p),
        ("new_token_callback", ctypes.c_void_p),
        ("new_token_callback_user_data", ctypes.c_void_p),
        ("progress_callback", ctypes.c_void_p),
        ("progress_callback_user_data", ctypes.c_void_p),
        ("encoder_begin_callback", ctypes.c_void_p),
        ("encoder_begin_callback_user_data", ctypes.c_void_p),
        ("abort_callback", ctypes.c_void_p),
        ("abort_callback_user_data", ctypes.c_void_p),
    ]


_SAMPLING_GREEDY = 0

# Load order matters: dependencies before the library that needs them,
# RTLD_GLOBAL so libparakeet's @rpath-relative lookups resolve against
# the already-loaded images rather than failing.
_DEPENDENCY_LIBS = [
    "libggml-base.dylib", "libggml-cpu.dylib", "libggml-blas.dylib",
    "libggml-metal.dylib", "libggml.dylib",
]


def _load_library(build_dir: Path):
    for name in _DEPENDENCY_LIBS:
        ctypes.CDLL(str(build_dir / name), mode=ctypes.RTLD_GLOBAL)
    lib = ctypes.CDLL(str(build_dir / "libparakeet.dylib"), mode=ctypes.RTLD_GLOBAL)

    lib.parakeet_context_default_params.restype = _ParakeetContextParams
    lib.parakeet_init_from_file_with_params.restype = ctypes.c_void_p
    lib.parakeet_init_from_file_with_params.argtypes = [ctypes.c_char_p, _ParakeetContextParams]
    lib.parakeet_full_default_params.restype = _ParakeetFullParams
    lib.parakeet_full_default_params.argtypes = [ctypes.c_int]
    lib.parakeet_full.restype = ctypes.c_int
    lib.parakeet_full.argtypes = [ctypes.c_void_p, _ParakeetFullParams, ctypes.POINTER(ctypes.c_float), ctypes.c_int]
    lib.parakeet_full_n_segments.restype = ctypes.c_int
    lib.parakeet_full_n_segments.argtypes = [ctypes.c_void_p]
    lib.parakeet_full_get_segment_text.restype = ctypes.c_char_p
    lib.parakeet_full_get_segment_text.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.parakeet_free.argtypes = [ctypes.c_void_p]
    return lib


class ParakeetNativeEngine(TranscriptionEngine):
    """In-process Parakeet via ctypes -- model loaded once at
    construction, reused for every transcribe_final() call. No
    streaming/partial API in the C layer used here, same as the
    subprocess version; final-only.
    """

    supports_partial = False

    def __init__(self, build_dir: Path, model: Path, use_gpu: bool = True):
        if not (build_dir / "libparakeet.dylib").exists():
            raise SystemExit(
                f"libparakeet.dylib not found in {build_dir} -- build it first "
                f"(cmake -B build-shared -DBUILD_SHARED_LIBS=ON ...; see this file's docstring)"
            )
        if not model.exists():
            raise SystemExit(f"model not found at {model}")

        self._lib = _load_library(build_dir)
        # Native calls run on a shared context; the executor-thread calls
        # below are serialized with this lock so two concurrent speakers
        # on the same relay process can't call into the C library at the
        # same time on the same ctx (no guarantee the library is safe for
        # that -- see the *_with_state variants in parakeet.h for the
        # proper per-session-state API, not used here to keep this change
        # scoped to "load once" rather than a full concurrency rework).
        self._call_lock = asyncio.Lock()

        ctx_params = self._lib.parakeet_context_default_params()
        ctx_params.use_gpu = use_gpu
        self._ctx = self._lib.parakeet_init_from_file_with_params(str(model).encode(), ctx_params)
        if not self._ctx:
            raise RuntimeError(f"parakeet_init_from_file_with_params failed for {model}")

    def _transcribe_sync(self, samples) -> str:
        import numpy as np
        samples_ptr = samples.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        full_params = self._lib.parakeet_full_default_params(_SAMPLING_GREEDY)
        ret = self._lib.parakeet_full(self._ctx, full_params, samples_ptr, len(samples))
        if ret != 0:
            raise RuntimeError(f"parakeet_full returned {ret}")
        n = self._lib.parakeet_full_n_segments(self._ctx)
        parts = []
        for i in range(n):
            text = self._lib.parakeet_full_get_segment_text(self._ctx, i)
            if text:
                parts.append(text.decode("utf-8", errors="replace"))
        return collapse_repetition(" ".join(parts).strip())

    async def transcribe_final(self, pcm_bytes: bytes) -> str:
        import numpy as np
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        loop = asyncio.get_running_loop()
        async with self._call_lock:
            return await loop.run_in_executor(None, self._transcribe_sync, samples)

    async def shutdown(self) -> None:
        if self._ctx:
            self._lib.parakeet_free(self._ctx)
            self._ctx = None
