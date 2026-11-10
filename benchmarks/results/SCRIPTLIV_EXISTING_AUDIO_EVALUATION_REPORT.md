# ScriptLiv: existing-audio audit and Parakeet evaluation

Labels: **MEASURED** = computed from data/run. **OBSERVED** = seen in numbers, cause unverified. **NOT MEASURED** = could have been measured, was not. **NOT SUPPORTED BY CURRENT DATA** = needs ground truth that does not exist.

Scope guard: no production relay, Parakeet, VAD, Flutter/web, schema or model-parameter change. Originals untouched. No dataset downloaded or generated. Relay was started with its existing configuration (`cd relays; python parakeet_relay.py`, log `results/relay_existing_audio.log`) and is still running (PID 21800).

## 1. Executive summary
- 7 files, 250.5 min (4.17 h) decoded and standardised. MEASURED.
- **No reference transcripts and no speaker labels exist.** So WER, per-speaker metrics and VAD accuracy are NOT SUPPORTED BY CURRENT DATA. Parakeet output was not used as ground truth.
- Relay pilot (20 clips, 10.1 min, real time, CPU, concurrency 1) completed with 0 errors: latency, partial-revision and resource numbers are valid but caveated (section 8).
- Offline engine RTF about 0.093 (about 10.7x real time) on CPU. MEASURED.
- The set is useful for latency/stability replay and for building a transcription set. It cannot yet answer accuracy questions.

## 2. Seven-file inventory (MEASURED; full detail `existing_audio_inventory.md`)
| id | min | native | peak dBFS | est. SNR dB | frames >= 0.01 | pauses >= 0.6 s (fixed / rel) | longest pause s (fixed) |
|---|---|---|---|---|---|---|---|
| rec01 | 46.6 | Opus 48k st | -7.8 | 44.7 | 21% | 885 / 409 | 34.2 |
| rec02 | 50.8 | Opus 48k st | -2.0 | 34.5 | 63% | 487 / 25 | 2.94 |
| rec03 | 57.5 | Opus 48k st | 0.0 | 43.3 | 56% | 755 / 497 | 7.2 |
| rec04 | 56.8 | Opus 48k st | -0.4 | 29.9 | 71% | 341 / 3 | 6.76 |
| rec05 | 8.8 | MP3 44.1k st | about 0 | 21.1 | 96% | 0 / 0 | 0.5 |
| rec06 | 13.9 | MP3 44.1k st | about 0 | 34.0 | 73% | 86 / 21 | 3.46 |
| rec07 | 16.1 | MP3 44.1k st | 0.0 | 32.7 | 81% | 57 / 18 | 1.8 |

rec01-04 are Opus inside `.mp3`. All lossy; bit depth n/a.

## 3. Total duration and statistics
- Total 250.5 min; 200 MB native. All usable as audio (decode clean). MEASURED.
- Clipping: only rec07 notable (546 samples >= 0.999, 0.0035%). MEASURED. Whether it is audible distortion: NOT MEASURED.
- Quiet speech: rec01 (75% of voiced frames in the 0.01-0.03 band). MEASURED.
- Noise floors: rec05 floor above the production 0.01 threshold; rec04 0.0059. MEASURED. Noise type: NOT MEASURED.

## 4. Speaker information and limits
- Speaker count: **UNKNOWN** for all files. No diarization or labels. 7 files is not 7 speakers. No IDs invented. Filename/tag hints (rec01-03 lecture-style, rec05 interview-style so probably several, rec06/07 single-creator) are unverified OBSERVED hints only.
- Consequences: per-speaker WER and speaker-disjoint split NOT SUPPORTED BY CURRENT DATA. Split by recording (`independence_group`).
- Language/accent: Indian English is user-stated, not verified per file.

## 5. Transcript availability
- Verified references: none (0 of 7 files, 0 of 3,081 clips). All clips `transcript_missing`.
- 20 UNVERIFIED relay drafts in `dataset_existing/pilot/drafts/` for human correction. `annotation_sheet.csv` ready.

## 6. Corpus preparation results
See `corpus_preparation_report.md`. Working copies 16 kHz mono PCM16 (250.5 min); manifest of 3,081 segment entries (10/20/30/60 s); 515 30 s WAVs written; 20-clip pilot. Cuts follow energy pauses (about 94% of 30 s cuts are pause_cut); not word-aligned. MEASURED.

## 7. WER results
**None. NOT SUPPORTED BY CURRENT DATA.** `ref_words` is 0 for every clip, so WER, substitutions, deletions and insertions are undefined. The `ins` counts in the raw JSON are an artifact of empty references and must be ignored. No raw/normalised comparison is possible yet.

## 8. Latency and RTF
Three layers kept separate.

**A. Offline engine (no WebSocket, no VAD), `engine_rtf.py`, ParakeetNativeEngine q8_0, CPU.** MEASURED, 20 clips (24-42 s):
- RTF p50 0.093, p95 0.097; about 2.3-3.8 s per clip; cold first call 2.43 s.
- `results/existing_audio_engine_rtf.json`.

**B. WebSocket relay, real-time replay (`ws_bench.py`, 100 ms chunks, 1.5 s tail), 20 clips, concurrency 1, 1 warmup.** MEASURED, 110 expected utterances sampled:
| metric | p50 | p95 | max |
|---|---|---|---|
| time to first word s | 1.01 | 5.31 | 10.30 |
| first partial s | 0.95 | 5.13 | 10.30 |
| finalization latency s | 0.93 | 3.21 | 9.74 |
| finalization after 0.6 s hang s | 0.33 | 2.61 | 9.14 |

- Relay process: CPU mean 162% (max 404%; multi-core percent), RSS 745 MB mean / 779 MB max. System CPU mean 9.9%. Wall 676.5 s for 606 s audio (real-time). GPU: backend is CPU ("no GPU found" in relay log); the sampled GPU figures (about 0% util) are the idle card, not Parakeet.
- Per recording p50 TTFW: rec01 1.23, rec02 0.77, rec03 1.41, rec04 0.90, rec05 1.00, rec06 0.92, rec07 2.64 s. rec03 and rec07 show p95 TTFW 8.3 and 8.8 s. Cause unverified (OBSERVED). `results/existing_audio_pilot_by_recording.json`.
- **Caveat (important):** utterance boundaries come from `simulate_flushes`, a mirror of the relay's energy VAD, so latencies are measured against energy-derived boundaries, not true speech starts. Circular for VAD; fine for relative latency. Excludes microphone, UI and tunnel, so **end-to-end app latency is NOT MEASURED.** Measured on one machine, one concurrency level.

**C. End-to-end app latency:** NOT MEASURED. Concurrency > 1 and CUDA: NOT MEASURED (CUDA unavailable in this build).

## 9. Partial observations (OBSERVED; no ground truth)
- Partial revision rate 0.331 (share of partial words that differ from the final word at the same index); prefix-stable rate 0.302. By recording 0.22 (rec07) to 0.48 (rec06, rec01). MEASURED as defined, but comparison to the final is not accuracy.
- Finals received 110 vs 115 expected utterances; 5 clips with a count mismatch (rec02 1, rec03 1, rec05 1, rec07 2). OBSERVED. Possible causes (merged/dropped utterance, tail handling) unverified.
- Missing words, repeated words, incorrect finalization: NOT SUPPORTED BY CURRENT DATA (need references). Visual check of drafts not done.
- Example draft shows a probable mis-hearing ("reshores") but without a reference this is not a counted error.

## 10. VAD observations (OBSERVED only; production VAD untouched)
- Energy-gap pause distributions per file (inventory section 4): natural gaps in rec01-04, 06, 07; effectively none in rec05.
- Under the fixed 0.01 threshold rec05's floor sits above the threshold, so silence flush is unlikely; 8 of 10 expected utterances in the rec05 pilot clips were forced 8 s cap flushes. rec06 and rec07: 8 of 15 and 8 of 16 forced; rec04 5 of 16. OBSERVED, from `simulate_flushes`.
- rec01 is quiet (21% of frames above 0.01): potential under-trigger exposure. Not confirmed: needs speech labels.
- Split utterances, boundary speech loss, missed flushes: possible at forced caps and `cut_in_speech_likely` clips; not quantified.
- **Speech recall, false activation and missed-flush rate: NOT SUPPORTED BY CURRENT DATA** (no annotations).

## 11. Issues found
1. No transcripts or speaker labels (blocks WER, per-speaker, VAD accuracy).
2. `.mp3` names hide Opus; extension-trusting tools can fail.
3. `engine_rtf.py` needs absolute `--lib-dir`/`--model` paths (relative path raises `WinError 87` in the production engine loader; I did not modify it).
4. Benchmark latency is anchored to energy boundaries.
5. rec05 (96% voiced) will mostly flush by cap, a different regime from pause-driven flushes.
6. Wide TTFW tail (p95 5.3 s, max 10.3 s) and 5/115 unmatched utterances need a closer look with references.
7. Relay still running on port 8768 with default config (PID 21800).

## 12. Global evaluation readiness
- Manifest keeps `language`, `accent`, `recording_condition`, `speaker_id` as separate fields, each with a status field; ws_bench aggregates WER by any tag. To add American, British, Australian, Canadian or other-accent English, or other Parakeet-supported languages: provide audio + verified transcript + those fields per recording, run `ingest_corpus.py` / `segment_existing.py`, and report per tag. Nothing is pre-filled for other accents/languages.
- Only Indian English (user-stated) has any audio here. Other accents/languages: **NOT SUPPORTED BY CURRENT DATA**. Parakeet's claimed language coverage has not been evaluated by this work.
- Per-language normalisation (numbers, scripts, punctuation) must be defined before scoring non-English; `wer.py` is lowercase ASCII-oriented and not validated for non-Latin scripts.
- No additional dataset downloaded.

## 13. Recommendations (need your approval where marked)
1. Human-transcribe the 20 pilot clips (10.1 min) from the drafts, to `dataset_existing/transcripts_verified/`; rerun `ws_bench.py` for the first real WER (with substitutions/deletions/insertions) per recording.
2. Mark speaker turns for rec05 and sample others (annotators note count), to enable speaker-aware reporting.
3. Add speech start/end annotation on a few clips to evaluate VAD recall/false activation honestly.
4. Re-measure at concurrency 2/4 on this corpus (standing priority 5) once references exist.
5. Needs approval: any more data collection, production VAD/relay changes, or leaving/stopping the relay.

## Artifacts
`results/existing_audio_inventory.md` / `.json`; `results/corpus_preparation_report.md`; `results/existing_audio_relay_pilot.json` / `.stdout.txt`; `results/existing_audio_pilot_by_recording.json`; `results/existing_audio_engine_rtf.json`; `results/relay_existing_audio.log`; `dataset_existing/manifest.json`; `dataset_existing/pilot/{manifest.json,annotation_sheet.csv,drafts/}`.
