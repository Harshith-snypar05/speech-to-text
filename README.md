# ST Transcribe

Live speech-to-text: a Flutter app (speaker + read-only viewer via share links) backed by a Python WebSocket relay running NVIDIA's Parakeet TDT model locally.

whisper.cpp, openai/whisper, and faster-whisper relays existed earlier in this project and were removed after head-to-head testing (same audio clip, same noise-degraded variants, same WER methodology) showed Parakeet ahead on both accuracy and latency. See `relays/parakeet_relay.py`'s docstring for the numbers.

## Structure

- `st_transcribe_app/` — the Flutter app. Speaker screen (record, see live transcript, share a link), viewer screen (read-only, opens from a shared link), transcript history, Settings (backend URL, theme, text size, mic).
- `relays/parakeet_relay.py` — the WebSocket relay. VAD-pause-triggered: transcribes once per utterance, the instant you pause. Session/broadcast protocol: a speaker connects with `?role=speaker&session=<token>`, a viewer connects with `?role=viewer&session=<token>` and gets the same transcript messages read-only.
- `relays/engines/parakeet_native_engine.py` — ctypes binding against a shared-library build of whisper.cpp's Parakeet support. Model loaded once, reused for every utterance, supports word-by-word partial streaming. Used automatically when available.
- `relays/engines/parakeet_engine.py` — fallback: shells out to `parakeet-cli` per utterance (slower, no partials). Used automatically if the shared library hasn't been built.
- `relays/core/` — session lifecycle, VAD buffering, protocol, access-code auth, connection limits -- shared infrastructure, kept separate from the engine in case another one is added later.
- `relays/supervisor.py` — process supervisor: start/stop/restart-on-crash with backoff, log capture.
- `relays/combined_proxy.py` — serves the built Flutter web app and proxies WebSocket traffic to the relay on the same port, so one URL (one Cloudflare tunnel, say) covers both.
- `relays/tests/` — pytest suite (`pytest`).
- `st_transcribe_app/test/` — Flutter test suite (`flutter test`).

## Dependency: whisper.cpp

Parakeet support lives in whisper.cpp, not as a standalone package. Fork, cloned as a sibling of this directory (not vendored -- large binaries, unrelated git history):

- [whisper.cpp](https://github.com/Harshith-snypar05/whisper.cpp) (this fork has native Parakeet support built in)

Build it, then download the model:

```bash
cd whisper.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target parakeet-cli -j 8

curl -L -o models/ggml-parakeet-tdt-0.6b-v3-q8_0.bin \
  https://huggingface.co/ggml-org/parakeet-GGUF/resolve/main/ggml-parakeet-tdt-0.6b-v3-q8_0.bin
```

That alone gets you the subprocess-based fallback engine working. For the faster, partial-streaming-capable in-process engine, also build the shared library:

```bash
cmake -B build-shared -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
    -DWHISPER_BUILD_EXAMPLES=OFF -DWHISPER_BUILD_TESTS=OFF
cmake --build build-shared --target parakeet -j 8
```

## Setup

```bash
uv venv stt-compare-venv
uv pip install --python stt-compare-venv/bin/python -r relays/requirements.txt

cd st_transcribe_app && flutter pub get
```

## Run

```bash
# Relay (auto-restart on crash, logs to relays/logs/)
python3 relays/supervisor.py

# Flutter app, local dev
cd st_transcribe_app && flutter run -d chrome
```

Default backend URL is `ws://localhost:8768`; change it in Settings if needed.

## Deploy (one shareable link)

```bash
cd st_transcribe_app && flutter build web

python3 relays/parakeet_relay.py &
python3 relays/combined_proxy.py --listen-port 5501 --relay-port 8768 &

cloudflared tunnel --url http://localhost:5501
```

The app auto-detects it's being served from a real host (not localhost) and points itself at that same origin -- no per-device Settings configuration needed for anyone opening the shared link.

## Test

```bash
cd relays && ../stt-compare-venv/bin/python -m pytest
cd st_transcribe_app && flutter test
```
