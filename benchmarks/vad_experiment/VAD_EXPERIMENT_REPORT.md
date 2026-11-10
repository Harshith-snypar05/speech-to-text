# Adaptive VAD experiment: report

**Recommendation: `NEEDS_REAL_CORPUS`**

Scope: isolated, offline, synthetic only. No production file, default or relay was touched. The production
`UtteranceBuffer` is imported unmodified and subclassed in `vad_experimental.py`. The earlier A/B baseline
(`ADAPTIVE_NOISE_FLOOR_REPORT.md`, `results/adaptive_{off,on,probe}.json`) is preserved as-is.
**No accuracy (WER) claim is made. This measures segmentation only, on synthetic audio.**

## 1. What was built

`AdaptiveVadBuffer` (`vad_experimental.py`), flush rule (0.6 s hang, 0.3 s min, 8 s cap) inherited unchanged.
Only speech/silence classification differs:

1. **First-second init**: floor seeded at 1 s as the 20th percentile of a 4 s window. Before that, plain `lo`=0.01.
2. **Floor tracking** by low percentile of recent RMS (not an EMA fed only by already-silent chunks). Falls immediately; rises limited to 1.15x/s.
3. **Threshold** = clamp(3 x floor, lo=0.01, 0.4 x median recent speech RMS).
4. **Quiet-speech guard**: the 0.4 x speech-level cap, so a quiet speaker is not absorbed into the noise estimate.
5. **Hysteresis**: once in speech, stays speech down to 0.5 x threshold.

### v1 -> v2 change (disclosure)
v1 counted noise seen during init as "speech", which pinned the speech-level cap and the threshold at `lo` (it behaved
like the fixed VAD in noise). v2 (`gate_speech=True`) only lets chunks >= 3 x floor feed the speech-level history.
**v2 was designed after seeing v1 fail on this same synthetic grid, so its numbers are optimistic.** v1 results are kept
(`exp_v1`, `exp_lowlo_v1`). The sweep variants (`exp_mult=2` etc.) are post-hoc exploration, not tuned results.

## 2. Setup

544 synthetic scenes per VAD (`run_experiment.py`): JFK cut into 3 pieces, gaps S=0.3 s (must not flush) / L=1.2 s
(must flush) in 4 patterns, speech gains 1/0.5/0.25/0.12, lead-in 0.3/2.0 s, noise none or {0.003, 0.01, 0.03, 0.08} rms
x {fan, cafe, street, keyboard}, always-on room tone 0.002. Ground truth from the clean composition, independent of
gain/noise. Fixed buffer verified against `simulate_flushes` (sanity check in `main`). Compared VADs: `fixed`
(production default), `prod_adaptive` (production adaptive mode, multiplier 2.5), `exp`, `exp_lowlo` (lo lower than 0.01), v1 variants.

Metrics: speech recall, false activation (non-speech chunks > 0.3 s from speech classed as speech), false flushes and
missed flushes per scene, cap (8 s forced) flushes per scene, extra latency over the 0.6 s hang.

## 3. Results (full tables: `results/vad_experiment_tables.md`)

### Overall (544 scenes)
| VAD | recall | false activation | false flushes/scene | missed flushes | cap flushes/scene |
|---|---:|---:|---:|---:|---:|
| fixed (baseline) | 90.7% | 51.0% | 1.20 | 69.1% | 0.73 |
| prod_adaptive | 65.6% | 28.7% | 1.99 | 66.5% | 0.45 |
| exp_v1 | 91.0% | 51.7% | 1.17 | 64.3% | 0.70 |
| **exp (v2)** | 70.2% | 23.8% | 1.80 | 56.2% | 0.49 |
| exp_mult=2 (post-hoc) | 83.7% | 35.8% | 1.35 | 53.0% | 0.57 |

Caveat: fixed recall is inflated in loud noise (noise counts as speech, so everything is "recalled"). Read recall with
false activation. Overall, v2 trades about 20 points of recall for about 27 points less false activation and fewer
missed flushes; that is not a clear win.

### Where it helps: clean and stationary-noise conditions (SNR >= 20 dB, 152 scenes)
| VAD | recall | false act. | false flushes | missed flushes | cap flushes |
|---|---:|---:|---:|---:|---:|
| fixed | 87.9% | 9.3% | 1.39 | 29.6% | 0.22 |
| prod_adaptive | 71.9% | 0.2% | 2.62 | 44.4% | 0.00 |
| exp (v2) | 87.6% | 2.9% | 1.22 | 20.4% | 0.12 |

Recall equal to baseline, false activation and missed/cap flushes lower. Production adaptive loses 16 points of recall here.

### Quiet-speech guard (gain <= 0.25 and SNR >= 10 dB, separable cases)
| gain 0.25 (72 scenes) | recall | false act. | missed flushes |
|---|---:|---:|---:|
| fixed | 79.0% | 19.7% | 62.5% |
| prod_adaptive | 55.0% | 0.8% | 48.6% |
| exp (v2) | 78.4% | 7.0% | 42.4% |

| gain 0.12 (40 scenes) | recall | false act. | missed flushes |
|---|---:|---:|---:|
| fixed | 57.3% | 0.0% | 50.0% |
| prod_adaptive | 48.5% | 0.0% | 50.0% |
| exp (v2) | 68.2% | 0.0% | 50.0% |
| exp_lowlo (v2) | 72.4% | 3.4% | 48.8% |

Production adaptive fails the guard (recall -24 points at gain 0.25). v2 matches the baseline at 0.25 and beats it at 0.12.
Clean quiet speech probe (gain 0.1): all VADs find the same 4 flush boundaries; speech-chunk fraction is 0.37 fixed, 0.30 prod_adaptive, 0.42 exp, 0.55 exp_lowlo. Extra chunks are soft syllables retained, not new flushes, so this shows the guard direction but not a segmentation difference.

**Guard NOT cleanly met.** Per-scene check, recall drop > 5 points vs fixed: `exp` is worse in 279 scenes, 108 of them at
SNR >= 10 dB (better in 109). Most of the SNR >= 10 loss is at SNR 10-20 dB, where recall falls 83.8% -> 75.9% and false
flushes rise 1.55 -> 2.62 per scene. At gain 0.5, v2 recall is 75.5% vs 93.5% for fixed overall (mostly noisy scenes,
where fixed recall is the inflated kind, but not exclusively). v1 was safer for recall (worse in 56 scenes at SNR >= 10) but
gives up the false-activation gain, since in loud noise it degrades to the fixed VAD.

### Probes (`adaptive_probe.py` inputs and seed, `results/vad_probe_experimental.txt`)
- Noise-only white 20 s: `fixed` and `exp_v1` flag it as speech from 0.015 up; `exp` never marks more than 5.5% of chunks (init second)
  but still emits a spurious flush at about 1.7 s. Production adaptive classes it as silence only up to about 0.015.
- Quiet clean JFK (gains 1.0-0.1): all VADs give 3-4 flushes with no cap flushes; exp and exp_lowlo keep more soft-speech chunks than fixed, production adaptive keeps fewer.
- Lead-in noise then speech: for noise 0.012-0.05 `exp` produces 5 sensible flushes with no 8 s cap flush where fixed has
  cap flushes; the extra flush at 1.7 s is the init-second artifact (below).

### Latency
Median extra latency over the 0.6 s hang is about 0 for every VAD (chunk quantization 0.1 s); p90 0.4 s for exp vs 0.5 s fixed
overall. No latency regression measured. Latency is only measured on flushes that matched a truth group, so it is not comparable
across VADs with very different match counts (n=336 vs 476).

## 4. Failure cases (not hidden)
1. **Init-second false activation**: the first second is classified with plain `lo`, so sustained noise > 0.01 triggers a
   speech run, then a spurious noise-only flush (about 1.7 s) before the floor is seeded. Visible in every noisy probe.
   Mitigation untested: hold the classification (no speech) during init, at the cost of a 1 s blind spot.
2. **v2 recall loss at moderate SNR (10-20 dB)** from gating speech history and a floor that follows noise upward.
3. **Cap flushes persist at SNR <= 10 dB** (noise or speech indistinguishable by RMS); speechless caps are discarded by
   `speaker_session`, so these cost latency/compute, not bad text.
4. **SNR < 0 dB is unseparable** for every energy VAD tested.
5. **White noise at 0.05** still fails partially (probe lead_noise_0.05).
6. `exp_mult=2` looks better on several slices (SNR >= 20: missed flushes 3.3%, recall 92.8%) but it was found by looking at this
   grid, so it is exploratory only.

## 5. Caveats on the evidence
- Single speech source (one JFK clip, American, 11 s, read speech), 3 pieces per scene. No Indian English, no technical
  vocabulary, no real conversation dynamics.
- Noises are crude statistical stand-ins, not recordings. Real cafe babble, keyboards and rooms have different spectra and
  temporal structure; RMS is blind to that anyway.
- Scenes of one speaker/noise family are correlated, so the scene counts overstate independence. No confidence intervals.
- v2 and the sweep variants were chosen after seeing the same grid. A held-out real corpus is required before any claim.
- Segmentation metrics are not WER. The ASR benefit of better flush points was not measured (no relay run, by design).
- Latency has 0.1 s resolution.

## 6. Verdict
`NEEDS_REAL_CORPUS`. Synthetic evidence shows a real structural advantage over production adaptive mode (it can learn noise
above 0.025 and does not discard soft speech) and fewer false activations and missed flushes in clean/stationary conditions at
equal recall. It does not show a clean win over the fixed VAD: recall drops in moderate-SNR scenes, the quiet-speech guard is not
met per-scene, and an init-second artifact adds a spurious flush. It is not `NO_MEASURED_BENEFIT` (clean-condition gains are
real), and not `PROMISING` (the guard is the stated gate and it is not passed). Keep production defaults unchanged.

Suggested next steps once recordings exist: run `ingest_corpus.py`, replay the real clips (and noise-mixed variants from
`make_corpus.py`) through `run_vad`, fix the design and thresholds on one half and report on the other, and test the
init-hold mitigation. Only then consider a flagged relay trial.

## Files
`vad_experimental.py`, `synth.py`, `run_experiment.py`, `probe_experimental.py`;
`../results/vad_experiment.json`, `vad_experiment_tables.md`, `vad_experiment_v1_*`, `vad_probe_experimental.{json,txt}`.
Reproduce: `python benchmarks/vad_experiment/run_experiment.py [--quick] [--sweep]`.
