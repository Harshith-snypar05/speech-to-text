# speech-to-text

Live STT engine comparison: one microphone, multiple engines, side-by-side transcription in a browser.

## Structure

- `relays/compare.html` — single page, captures mic audio, streams it to each engine's websocket in parallel, renders live transcripts.
- `relays/whispercpp_relay.py` — websocket relay wrapping `whisper-cli` (whisper.cpp), chunked re-transcription.
- `relays/openai_whisper_relay.py` — websocket relay wrapping the `whisper` Python package, VAD-pause-triggered transcription (low latency, full-context accuracy per utterance).
- `relays/test_all.py` — smoke test, streams a sample clip through all engines and prints results.
- `engine_comparison.html` / `.pdf` — mobile-integration comparison writeup.

## Companion repos

The actual ASR engines are forked separately rather than vendored into this repo (large binaries, unrelated git history):

- [whisper.cpp](https://github.com/Harshith-snypar05/whisper.cpp) — clone and build per its own README; download `ggml-base.en.bin` via `models/download-ggml-model.sh base.en`.
- [whisper](https://github.com/Harshith-snypar05/whisper) (openai/whisper) — `pip install -e .` or installed as a dependency below.

## Setup

```bash
uv venv stt-compare-venv
uv pip install --python stt-compare-venv/bin/python -r relays/requirements.txt
```

Clone the two companion repos above as siblings of this directory (`whisper.cpp/`, `openai-whisper/`) before running the relays — `whispercpp_relay.py` expects `../whisper.cpp/build/bin/whisper-cli` and `../whisper.cpp/models/ggml-base.en.bin`.

## Run

```bash
./stt-compare-venv/bin/python relays/whispercpp_relay.py &
./stt-compare-venv/bin/python relays/openai_whisper_relay.py &
cd relays && python3 -m http.server 9000 --bind 127.0.0.1
```

Open `http://localhost:9000/compare.html`.
