# Svarah 60-clip benchmark readiness (NOT executed; awaiting authorization)

Only read-only checks were done: file existence, manifest parsing, port listing, source/log reading. No audio was streamed, no inference run, no file written outside `results/` docs.

## Checks
| item | result |
|---|---|
| Manifest `C:\data\corpus_svarah\manifest.json` | exists; 60 clips; 60 unique ids; ws_bench format (`id`, `wav`, `reference`, `tags`, `meta`) |
| Audio | all 60 `wav/` files exist (relative to manifest dir); total 14.76 min; duration min 10.0 s, median 13.3 s, max 29.3 s; 16 kHz mono PCM16 per `meta` |
| Reference transcripts | 60 of 60 non-empty. Source: Svarah's own transcripts (original text kept in `meta.notes.svarah_text_original`). Independent of Parakeet. They have not been replaced by or compared with Parakeet output. |
| Relay connectivity | `127.0.0.1:8768` LISTENING, PID 21800 (netstat). Same process started earlier with default config. A WebSocket handshake was not attempted. |
| Model config | `relays/parakeet_relay.py` `MODEL = whisper.cpp/models/ggml-parakeet-tdt-0.6b-v3-q8_0.bin`, `ParakeetNativeEngine`; relay log shows that path loaded and "no GPU found" (CPU). Matches the permitted model. Parakeet is the only engine involved. |
| Output path | `results\svarah_wer.json` does **not** exist; no `svarah*` file in `results/`. Using that path overwrites nothing. Existing Svarah audit files (`dataset_audit/svarah_measured.json` etc.) are in a different directory and are not touched. |
| Slice composition | many L1 groups (Assamese, Bengali, Bodo, Dogri, Gujarati, Hindi, Kannada, Kashmiri ... 3-4 clips each); 4 clips with est. SNR < 20 dB |

## Readiness verdict
READY pending your authorization. No blocker found.

## Caveats to state with results
1. Normalization: `wer.normalize` lowercases, strips punctuation, keeps apostrophes, maps hyphen to space, **no number mapping**. Svarah references with digits vs Parakeet spoken numbers (or the reverse) will count as errors. Report raw WER, and treat any number-normalised WER as a separate, declared policy.
2. 60 clips, 1 speaker each: WER confidence interval will be wide; per-L1 groups of 3-4 clips are not statistically meaningful. `ws_bench` bootstraps a CI.
3. Svarah clips (10-29 s) are shorter than pilot clips and mostly below the 8 s cap per utterance only if there are pauses; forced-cap flushes may appear. The relay path (VAD split) is what is measured, not offline decode quality.
4. Index-pairing issue in `ws_bench` latency (see `RELAY_PILOT_INVESTIGATION.md` section 2) also applies. WER is computed on concatenated finals and is not affected by pairing, but latency numbers are.
5. Empty-text flushes drop speech silently (no final), so deletions from VAD/short snapshots will appear as WER deletions. These are relay-path behaviours, not model-only quality.
6. Real-time replay: 14.76 min of audio plus 1.5 s tail per clip plus warmup is about 17 to 18 minutes wall time at concurrency 1. CPU load on this machine.

## Command (do not run until authorized)
```
cd C:\Users\sriha\snypar\stt\speech-to-text\benchmarks
python ws_bench.py --manifest C:\data\corpus_svarah\manifest.json --out results\svarah_wer.json --concurrency 1 --warmup 1 --relay-pid 21800 --note "Svarah 60-clip Parakeet 0.6B v3 q8_0, relay default config"
```
(Add `--url ws://127.0.0.1:8768` only if the default differs; defaults match the pilot settings.) Run after confirming `results\svarah_wer.json` is still absent.

## What this will and will not give
- Will: WER (substitutions, deletions, insertions against Svarah references), latency, partial revision, resource use for the relay path on 60 clips.
- Will not: speaker-level or accent-level claims with confidence; end-to-end app latency; any comparison against another engine (none permitted).
