# Adaptive noise floor A/B report

Date: 2026-11-06. Scope: segmentation + latency of `UtteranceBuffer` with `STT_ADAPTIVE_NOISE_FLOOR` 0 vs 1, on the JFK smoke corpus (1 clip, 3 synthetic white-noise copies). **Small synthetic-noise smoke corpus. This does not demonstrate production-level noise robustness, in either direction.** No production file was modified.

## 1. Implementation findings

Source: `relays/core/audio_processor.py` (`UtteranceBuffer`), `relays/core/config.py:30-31`, wired in `relays/parakeet_relay.py:_new_buffer` (`adaptive_noise_floor=ADAPTIVE_NOISE_FLOOR`). The env var **is** read and **does** take effect: the live ON run produced the 4-utterance clean segmentation that the offline model of the real class predicted, and OFF produced 3.

- Read: `ADAPTIVE_NOISE_FLOOR = os.environ.get("STT_ADAPTIVE_NOISE_FLOOR","0") == "1"` (only the literal `"1"` enables it). Multiplier `STT_NOISE_FLOOR_MULTIPLIER`, default 2.5.
- Init: `_noise_floor = silence_rms_threshold` (0.01), so the **initial effective threshold is already 0.025, 2.5x the fixed one**, before anything is learned.
- Threshold: `max(silence_rms_threshold, _noise_floor * multiplier)`. **Lower bound** 0.01. **No upper bound.**
- Update: EMA (alpha 0.1) of chunk RMS, applied **only to chunks already classified as silence** (`rms < effective threshold`).
- Consequence 1 (design limit): noise whose RMS is above the current threshold is never classed as silence, so the floor never sees it and **cannot climb to meet it**. Stationary noise louder than ~0.025 RMS is therefore invisible to the adaptive logic, which then behaves exactly like the fixed threshold.
- Consequence 2: speech does not feed the estimate directly (speech chunks are excluded), but the 2.5x multiplier makes soft speech and inter-word dips (RMS 0.01-0.025) count as silence, and those *are* fed into the floor. The floor persists across utterances (`take()` does not reset it).
- Harness fidelity: `audio_utils.simulate_flushes` previously modelled only the fixed rule. I added an `adaptive` mode (same init, same max(), same EMA, same persistence) plus `--adaptive/--noise-mult` flags. Validation: replayed all 4 corpus clips x {OFF, ON} through the **real** `UtteranceBuffer` and compared flush times to the simulation: identical in all 8 cases. This harness change is benchmark-side only.

## 2. Commands and environment

Windows 11, Ryzen 9 8940HX, CPU-only, AVX512 `parakeet.dll` build, `ggml-parakeet-tdt-0.6b-v3-q8_0.bin`, native engine. Same binary, model, wavs, references, 16 kHz, 100 ms chunks, 1.5 s tail silence, concurrency 1 then 2, default stagger/warmup. Fresh relay process per config; the previous relay was killed first.

```
# A
cd relays; STT_ADAPTIVE_NOISE_FLOOR=0 python parakeet_relay.py
python benchmarks/ws_bench.py --manifest benchmarks/corpus_smoke/manifest.json --concurrency 1,2 --relay-pid <pid> --out benchmarks/results/adaptive_off.json --note "A: STT_ADAPTIVE_NOISE_FLOOR=0"
# B
cd relays; STT_ADAPTIVE_NOISE_FLOOR=1 python parakeet_relay.py      # multiplier default 2.5
python benchmarks/ws_bench.py --adaptive --manifest benchmarks/corpus_smoke/manifest.json --concurrency 1,2 --relay-pid <pid> --out benchmarks/results/adaptive_on.json --note "B: STT_ADAPTIVE_NOISE_FLOOR=1 mult=2.5"
# offline probes (real UtteranceBuffer, no relay/model)
python benchmarks/adaptive_probe.py        # -> results/adaptive_probe.json
python benchmarks/selftest.py              # 8/8 PASS after the harness change
```
Relay logs: `relay_adaptive_off.log`, `relay_adaptive_on.log`. Raw results: `results/adaptive_off.json`, `results/adaptive_on.json`. Both runs: 0 stream errors, 0 segment mismatches (finals received == simulated flushes for every clip).

Caveats: single run per config, so run-to-run noise is of the order of the latency differences seen (identical segmentation still moves N=2 p95 by 0.2-0.4 s). Back-to-back on a laptop. WER is over 22 words per clip: one error = 4.5 points. "Cap events" are the simulated forced flushes, corroborated live: the first final of each noisy clip arrives ~8.7 s into the stream, right after the 8.0 s cap.

**Latency caveat for cap-flushed utterances:** final latency is measured from the flush point (cap, ~8.1 s), not from the start of speech. In noisy clips the first words appear ~8 s after they were spoken; the per-clip latency of 0.6-0.9 s hides that wait. It is identical in A and B.

## 3. Segmentation per recording (N=1; N=2 segmentation identical)

Seconds of audio. Expected = simulated flush of the real rule; every live run matched it exactly.

| Recording | Adaptive | Utterances (start-end) | Cap hit | Notes |
|---|---|---|---|---|
| clean | OFF | 0.3-2.3, 3.2-4.5, 5.1-11.0 | no | Split on the two real pauses; flushed ~0.6 s + inference after each end. |
| clean | ON | 0.3-2.2, 3.2-4.3, 5.4-7.5, 8.2-10.2 | no | **Extra split inside the last sentence** (~7.5 s). Segments end slightly early (2.2 vs 2.3, 4.3 vs 4.5). Words per final 5/2/7/8 vs 5/2/15. No WER change. |
| 10 dB | OFF and ON | 0-8.1 (forced), 8.1-11.0 | **yes** | Noise (RMS ~0.06) never below threshold: no silence detected in the whole file. |
| 0 dB | OFF and ON | same | **yes** | Noise RMS ~0.13. |
| -5 dB | OFF and ON | same | **yes** | Noise RMS ~0.17. |

- Flushed after expected silence: clean yes in both modes; noisy never (cap in both).
- Noise prevented silence detection: yes in all three noisy recordings, both modes. Adaptive did **not** change this: noise RMS 0.06-0.17 is far above the 0.025 starting threshold, so by Consequence 1 the floor is never updated.
- Premature cutoff: ON clean has two segments ending 0.1-0.2 s earlier and one mid-sentence split. The 8 s cap also cuts noisy files mid-speech (14 + 8 words), identical in A and B.
- Leading/trailing silence: not separable from noise in the noisy files; in the clean file the only trailing silence is the 0.6 s hang in both modes.

## 4. Side-by-side performance

## 5. Aggregate and per-condition tables

N=1 and N=2 shown separately; read aggregates only together with the per-condition rows.

### N=1 sessions

| Metric | Adaptive OFF | Adaptive ON |
|---|---:|---:|
| WER | 9.09% | 9.09% |
| p50 first-word s | 0.80 | 0.79 |
| p95 first-word s | 1.09 | 1.11 |
| p50 final s | 0.85 | 0.86 |
| p95 final s | 1.08 | 0.98 |
| min final latency s (must be >=0) | 0.57 | 0.60 |
| finals / clips | 9/4 | 10/4 |
| 8 s cap events | 3 | 3 |
| partial revision rate | 0.230 | 0.219 |
| Mean relay CPU % | 175 | 167 |
| Max relay CPU % | 380 | 384 |

Per condition (N=1):

| Condition | Metric | OFF | ON |
|---|---|---:|---:|
| clean | WER | 0.00% | 0.00% |
| clean | p50 first word s | 0.80 | 0.79 |
| clean | p50 final s | 0.85 | 0.86 |
| clean | p95 final s | 1.12 | 1.00 |
| clean | finals/clips | 3/1 | 4/1 |
| clean | cap events | 0 | 0 |
| clean | revision rate | 0.182 | 0.143 |
| 10 dB | WER | 0.00% | 0.00% |
| 10 dB | p50 first word s | 0.79 | 0.78 |
| 10 dB | p50 final s | 0.76 | 0.76 |
| 10 dB | p95 final s | 0.89 | 0.90 |
| 10 dB | finals/clips | 2/1 | 2/1 |
| 10 dB | cap events | 1 | 1 |
| 10 dB | revision rate | 0.111 | 0.111 |
| 0 dB | WER | 9.09% | 9.09% |
| 0 dB | p50 first word s | 0.79 | 0.83 |
| 0 dB | p50 final s | 0.77 | 0.78 |
| 0 dB | p95 final s | 0.94 | 0.90 |
| 0 dB | finals/clips | 2/1 | 2/1 |
| 0 dB | cap events | 1 | 1 |
| 0 dB | revision rate | 0.222 | 0.222 |
| -5 dB | WER | 27.27% | 27.27% |
| -5 dB | p50 first word s | 0.84 | 0.84 |
| -5 dB | p50 final s | 0.80 | 0.79 |
| -5 dB | p95 final s | 0.91 | 0.91 |
| -5 dB | finals/clips | 2/1 | 2/1 |
| -5 dB | cap events | 1 | 1 |
| -5 dB | revision rate | 0.438 | 0.438 |

### N=2 sessions

| Metric | Adaptive OFF | Adaptive ON |
|---|---:|---:|
| WER | 9.09% | 9.09% |
| p50 first-word s | 0.87 | 0.93 |
| p95 first-word s | 2.33 | 2.52 |
| p50 final s | 1.18 | 1.10 |
| p95 final s | 1.83 | 2.05 |
| min final latency s (must be >=0) | 0.82 | 0.72 |
| finals / clips | 18/8 | 20/8 |
| 8 s cap events | 6 | 6 |
| partial revision rate | 0.199 | 0.230 |
| Mean relay CPU % | 297 | 293 |
| Max relay CPU % | 408 | 407 |

Per condition (N=2):

| Condition | Metric | OFF | ON |
|---|---|---:|---:|
| clean | WER | 0.00% | 0.00% |
| clean | p50 first word s | 0.87 | 0.93 |
| clean | p50 final s | 1.02 | 1.00 |
| clean | p95 final s | 1.94 | 2.03 |
| clean | finals/clips | 6/2 | 8/2 |
| clean | cap events | 0 | 0 |
| clean | revision rate | 0.093 | 0.132 |
| 10 dB | WER | 0.00% | 0.00% |
| 10 dB | p50 first word s | 1.22 | 1.00 |
| 10 dB | p50 final s | 1.48 | 1.23 |
| 10 dB | p95 final s | 1.75 | 1.95 |
| 10 dB | finals/clips | 4/2 | 4/2 |
| 10 dB | cap events | 2 | 2 |
| 10 dB | revision rate | 0.158 | 0.211 |
| 0 dB | WER | 9.09% | 9.09% |
| 0 dB | p50 first word s | 1.33 | 1.40 |
| 0 dB | p50 final s | 1.14 | 1.25 |
| 0 dB | p95 final s | 1.48 | 1.88 |
| 0 dB | finals/clips | 4/2 | 4/2 |
| 0 dB | cap events | 2 | 2 |
| 0 dB | revision rate | 0.250 | 0.237 |
| -5 dB | WER | 27.27% | 27.27% |
| -5 dB | p50 first word s | 1.06 | 1.07 |
| -5 dB | p50 final s | 1.14 | 1.02 |
| -5 dB | p95 final s | 1.51 | 1.16 |
| -5 dB | finals/clips | 4/2 | 4/2 |
| -5 dB | cap events | 2 | 2 |
| -5 dB | revision rate | 0.324 | 0.353 |

## 6. Per-noise-level WER and latency
In the per-condition tables above. WER is identical in every condition (clean 0%, 10 dB 0%, 0 dB 9.09%, -5 dB 27.27%). Latency differences are within run-to-run noise (single runs; segmentation identical in all noisy conditions yet N=2 p95 moves 0.2-0.4 s).

## 7. Clean-audio regression analysis
- WER: no change (0%).
- Latency: p50 first-word/final within 0.01-0.06 s at N=1; N=2 within noise.
- **Segmentation regression: yes.** ON splits the clean 11 s sentence into 4 utterances instead of 3, including a mid-sentence split at ~7.5 s. Cause: initial threshold 0.025 plus multiplier classes quiet frames inside speech as silence. Offline probe (clean JFK, gain 1.0): fraction of chunks classed as speech **0.72 OFF vs 0.53 ON**. No WER effect on this clip, but mid-sentence splits remove decoder context and add finals (10 vs 9 across the N=1 run); the effect beyond WER was not measured.
- Quiet speech (offline, scaled JFK): at gain 0.1 ON flushes the first segment at 2.1 s vs 2.6 s (earlier, cutting softer words); at gains 0.25-0.15 both modes behave alike (fixed 0.01 floor dominates). Speech was not dropped entirely in any case tested.

## 8. CPU utilization
Mean relay CPU 175% vs 167% (N=1), 297% vs 293% (N=2); max 380 vs 384 and 408 vs 407. Differences are noise. GPU unused (CPU-only build).

## 9. Unexpected behavior
1. **Adaptive mode is inert on loud stationary noise.** All three SNR recordings: identical segmentation and cap hit as OFF. The floor is only updated by chunks already below the adaptive threshold, so noise louder than the starting 0.025 can never be learned. The case the feature targets (continuous noise above the fixed threshold) is not helped by this design.
2. **The initial threshold is 2.5x the configured one** from chunk one, even in a quiet room.
3. Offline probe 3 (real class; 3 s noise-only lead-in, then JFK + Gaussian noise): for noise RMS **0.005-0.02** ON avoids the 8 s cap (flushes at ~5.6-5.8, 7.9, 11.1, 13.8 vs OFF forced 8.0, 14.6) because that noise sits in the band the floor can reach; for RMS >= 0.03 ON is identical to OFF. A narrow band where it helps, but the speech there is also split 4 ways. Segmentation simulation only; nothing was transcribed.
4. Noise-only audio (probe 1): both modes issue forced flushes every 8 s (`total_s >= max`) even with zero speech chunks. `speaker_session` discards them (`has_pending_utterance()` false -> `take()`, lines 73-74), so no engine call or text. At noise RMS 0.015 OFF counts 100% of chunks as speech and ON 0% (the one place ON is clearly more correct); at 0.03+ both 100%.
5. Harness: timing ground truth for SNR variants was previously taken from the clean source; that was wrong once the relay's behavior under noise was understood (fixed earlier this session). All ground truth is now simulated on the audio actually streamed. All final latencies in this report are >= 0.57 s.

## 10. Validity checks
- selftest.py: 8/8 PASS after the harness change.
- Timestamps: all latencies non-negative (min 0.57 s OFF N=1, 0.60 s ON N=1).
- 8 s cap respected: first final of every noisy clip arrives ~8.7-10.1 s stream time (cap at 8.0 + inference + pacing), consistent with the model.
- Noise-only false triggers: none produced text (probe 1). Speech absorbed into the noise estimate: not directly; see section 7 for the dips-as-silence mechanism.
- Not tested: real recorded noise (babble, fans, music), non-stationary noise, other speakers, other multipliers, a noise lead-in in the live relay. Multiplier 2.5 only.

## 11. Recommendation

On this corpus adaptive ON gave **no measurable benefit** in the noise conditions (identical segmentation, same cap events, same WER, latency within noise) and **one segmentation regression on clean audio** (extra mid-sentence split, earlier segment ends). The offline simulation shows a narrow band (stationary noise RMS ~0.005-0.02 with a noise-only lead-in) where it would avoid the 8 s cap, but that band is not in the live corpus and was not transcribed. The limits (floor cannot learn noise above the starting threshold; initial threshold already 2.5x) are structural, not a tuning accident.

**Decision: KEEP DISABLED.**

Follow-ups (not done; each is a production code change needing your go-ahead): initialise the floor from the first ~0.5-1 s of audio instead of from the fixed threshold; let the floor rise (e.g. low percentile of recent RMS over a window, not only chunks already below threshold); apply the multiplier to the estimated noise only, keeping the configured threshold as lower bound. Then rerun with recorded noise at RMS 0.01-0.05 and real speakers. Until then the 8 s cap is the effective fallback in noise, with ~8 s delay for the first words.
