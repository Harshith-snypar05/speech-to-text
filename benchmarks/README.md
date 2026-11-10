# Parakeet benchmark (Phase 1)

Measures the existing relay as-is. **No production code is modified**; this
folder only talks to the relay over its public WebSocket protocol (plus an
optional read-only import of the engine classes for RTF).

Status of what has actually been run:

| Piece | Verified? |
|---|---|
| `wer.py`, `audio_utils.py`, `ws_bench.py` | Yes, via `selftest.py` against a mock relay (known WER, known latency, revisions, N=2 concurrency). Proves the instrument, says nothing about Parakeet. |
| `make_corpus.py` | Written, not yet run on real audio. |
| `engine_rtf.py` | Written, not yet run (needs the model + whisper.cpp build). |
| Any Parakeet number | **None yet.** No model/recordings were on the authoring machine. |

## What you need to supply
1. whisper.cpp fork built + `ggml-parakeet-tdt-0.6b-v3-q8_0.bin` (see `../README.md`), relay running (`python relays/parakeet_relay.py`).
2. **Real recordings** with exact reference text. The corpus is the whole point; the tool cannot invent it. Cover: several speakers, Indian English and other accents, technical vocabulary, long (5-30 min) conversations, slow/normal/fast speech, real background noise (cafe, street, fan, babble). Public sets to consider (check licences): AI4Bharat Svarah (Indian English), LibriSpeech/TED-LIUM (general), your own meetings (best signal).
3. Write references the way Parakeet writes numbers (digits) or keep numbers out of the corpus; see `wer.py` header.

## Run
```
python benchmarks/selftest.py                                  # instrument check, ~40 s, no model needed

python benchmarks/make_corpus.py add --id spk1_tech --wav raw/spk1_tech.wav \
    --ref "exact words spoken" --tag speaker=spk1 --tag accent=indian_english --tag domain=technical
python benchmarks/make_corpus.py variants --id spk1_tech --snr 20 10 5 0 -5 --noise-file raw/cafe.wav

python benchmarks/ws_bench.py --manifest benchmarks/corpus/manifest.json \
    --concurrency 1,2,4,8 --relay-pid <relay pid> --note "M-series Mac, native engine"
python benchmarks/engine_rtf.py --manifest benchmarks/corpus/manifest.json --engine native \
    --lib-dir whisper.cpp/build-shared/bin --model whisper.cpp/models/ggml-parakeet-tdt-0.6b-v3-q8_0.bin
```
Use `--chunk-ms` equal to the frame size the Flutter app really sends, and
pass the relay's real `STT_SILENCE_HANG_SECONDS` as `--hang-s`.
Results land in `benchmarks/results/*.json` (config, per-clip hypotheses,
per-utterance latencies). Commit them with the hardware note.

### Bulk ingest of real recordings (`ingest_corpus.py`)
Drop recordings into a folder with a same-stem `.txt` of the exact reference
(optional `.json` sidecar `{"tags": {...}, "notes": "..."}`, optional `defaults.json`):
```
python benchmarks/ingest_corpus.py raw --out benchmarks/corpus_real --tag device=laptop_mic --dry-run
python benchmarks/ingest_corpus.py raw --out benchmarks/corpus_real --tag device=laptop_mic
```
WAV (8/16/24/32-bit PCM, any rate/channels) is read natively; mp3/m4a/flac/ogg need `ffmpeg` on PATH
(not installed on the authoring machine; convert first or install it). Output is 16 kHz mono int16 with
NO gain normalisation. Each clip records source sha256, peak, clipping %, rough SNR in `meta`.
Rejects: missing/empty reference, near-silent audio, unreadable format. Warns: short/long, clipping,
DC offset, ref/audio length mismatch. Re-running extends the manifest; `--replace` overwrites an id.
The output manifest is read unchanged by `ws_bench.py` and `vad_experiment/` tooling.
Suggested tags: `accent`, `domain`, `speaker`, `level=normal|quiet|loud`, `noise=quiet_room|fan|cafe|street|keyboard`, `device`.

## Metric definitions
- **WER**: micro-average (sum errors / sum reference words) over clips, with a bootstrap 95% CI over clips (shown once there are >=5). Breakdowns for every manifest tag (noise, accent, domain, speed...). Small corpora give wide CIs - read them.
- **TTFW**: first message of an utterance (partial or final) minus the start of speech in the audio.
- **Finalization latency**: final message minus end of speech; also reported minus the 0.6 s silence hang (`after_hang`), which isolates inference + queueing + transport. The hang itself is a fixed floor of the design.
- **Partial revision rate**: the relay only appends partial words, so a word that differs from the final text at the same index counts as revised (the viewer sees it wrong until the final lands). `partial_prefix_stable_rate` = share of utterances whose whole partial text is a prefix of the final.
- **Concurrency**: N parallel speaker sessions; watch p95 latency and error counts as N grows (the engine uses one inference thread + lock, so expect queueing).
- **GPU/CPU**: `nvidia-smi` and psutil sampled once per second during each level (`--relay-pid` for the relay's own CPU/RSS). Apple GPU is not sampled; use `powermetrics` alongside if needed.
- **RTF** (`engine_rtf.py`): median processing time / audio duration, plus the cold first call.

## Mic-to-screen latency - what this does NOT capture
All latencies are "audio captured -> text arrives at this client". Real
microphone-to-visible-text adds OS/mic capture buffering, Flutter's audio
chunking, the Cloudflare tunnel hop and widget render. To measure that:
play a click/beep from a second device next to the phone, record both the
click and the screen at 120+ fps (or loop the click into the mic and log
frame timestamps), and subtract. Do this once per platform, then use the
harness numbers as the server-side share of that total.

## Known limits of the harness
- Latency uses audio-side ground truth from an RMS VAD on the clean file; heavy overlap or music breaks it. Utterances matched to finals by order; clips where counts differ are flagged `segment_mismatch_clips`.
- The 8 s max-utterance cap can split a long monologue mid-sentence and affects WER; that is a real property of the relay, not a harness bug.
- Speed variants are resampled (pitch shifts) - a rate stressor, not natural fast speech.
