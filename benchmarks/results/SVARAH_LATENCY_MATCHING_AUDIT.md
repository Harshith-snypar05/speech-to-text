# Svarah latency matching audit (Phase 3)

Source: `final_times_s`, `expected_detail`, `ttfw_s`, `final_latency_s` in `results/svarah_wer.json` (unchanged). `ws_bench.py` not modified; matching is a separate offline recomputation.

## Problem
`ws_bench.analyse_clip` pairs finals with expected utterances by position. When final count differs, later pairs shift or vanish. Expected utterances come from `simulate_flushes`, a mirror of the VAD, so VAD timing is circular.

## Proposed timestamp matching (implemented offline in `svarah_error_analysis.py`)
Expected flush time `F_k = end_k + 0.6 s` (hang) for non-forced utterances, `end_k` for forced. A final at time `f` goes to the expected utterance with the largest `F_k <= f + 0.2 s`, one-to-one and monotonic. A second final in the same window is `extra`; an expected utterance with no final is `unmatched`. TTFW is recomputed only when the group's first-message time (`ttfw_s[i] + start_i`) is stored (index below expected count), not before expected start, and not after the final (+0.01 s). Unmatched events get no latency.

## The six count-mismatch clips

| clip | expected | received | missing final(s) | extra final(s) | index pairing = timestamp pairing |
|---|---|---|---|---|---|
| assamese_03817_281474976 | 3 | 2 | exp#2 16.2-19.1s | - | False |
| assamese_06152_281474976 | 2 | 1 | exp#1 8.1-10.3s | - | False |
| bengali_01831_2814749768 | 2 | 3 | - | final#1 at 8.993s | False |
| bodo_03621_2814749768938 | 7 | 6 | exp#6 16.3-18.0s | - | False |
| kannada_00197_2814749768 | 2 | 1 | exp#1 8.1-10.2s | - | False |
| kashmiri_03111_281474976 | 2 | 1 | exp#1 8.2-10.8s | - | False |

Pattern (evidence: `expected_detail`, final times, offline decode):
- 5 clips lose the **last expected utterance** (assamese_03817, assamese_06152, kannada_00197, kashmiri_03111 after forced 8 s caps; bodo_03621 a short tail). The missing words are present in the offline full-clip decode and absent from the relay text. Why no final was sent is not instrumented. The relay sends a final only when decoded text is non-empty, which is consistent with this but **unverified** here.
- bengali_01831 has 1 **extra** final: two finals 0.142 s apart (8.851 s, 8.993 s) after the forced cap at 8.1 s, then 13.915 s. Index pairing gave its second group a final latency of -3.807 s (impossible), an artefact.

- Did index pairing shift latencies? In the 5 missing-final clips every received final was paired with its own expected utterance (old pair = timestamp pair), so **no shift**; the lost utterance simply has no entry. Only bengali_01831 shifted (final#1 was paired with expected#1). The `index pairing = timestamp pairing` column is False for all six because the counts differ, not because values moved.
- Deletions: these six clips hold 24 of 44 baseline deletions (54.5%) with 10% of the clips. Offline full-clip decode has D 14 against relay D 44.

## Latency distributions (seconds)
- Old (index-paired) TTFW: n=196, p50 0.891, p95 2.172, max 7.585, mean 1.088
- Corrected TTFW: n=195, p50 0.889, p95 2.174, max 7.585, mean 1.089
- Old final latency (final minus utterance end): n=196, p50 0.909, p95 1.5, max 1.89, mean 0.942
- Corrected final minus utterance end: n=196, p50 0.911, p95 1.5, max 1.89, mean 0.967
- Corrected final minus expected flush time (end + hang if not forced), i.e. relay processing after the VAD fires: n=196, p50 0.413, p95 1.036, max 1.563, mean 0.48
- Mismatch clips only, old TTFW: n=13, p50 0.849, p95 1.377, max 1.667, mean 0.87; corrected: n=12, p50 0.83, p95 1.401, max 1.667, mean 0.869
- Mismatch clips only, old final latency: n=13, p50 0.774, p95 0.946, max 0.961, mean 0.439; corrected after-flush: n=13, p50 0.515, p95 0.856, max 0.936, mean 0.495

Effect: 6 of 60 clips mismatch and hold 13 of 196 events, so the aggregate barely moves (TTFW p50 0.891 to 0.889, p95 2.172 to 2.174). The correction matters per clip: one impossible negative latency removed, 5 unmatched expected utterances and 1 extra final now reported. The TTFW max 7.585 s is a group where no partial arrived before the final, in a **matched** clip (bengali_00427), unrelated to pairing.

Clips where index pairing differs from timestamp pairing: assamese_03817_281474976, assamese_06152_281474976, bengali_01831_2814749768, bodo_03621_2814749768938, kannada_00197_2814749768, kashmiri_03111_281474976.

## Limits
- Clock is audio-position seconds (real-time replay). `F_k` uses the 0.6 s hang and the 8 s cap from the relay config.
- A match is defensible only when one final falls in an expected flush window; no latency is computed for unmatched events.
- Expected utterances still come from the VAD mirror: this fixes pairing, it does not validate segmentation.
- Partial texts/times were not stored: partial-level latency is not recomputable. 6 clips, 6 anomalous events: small sample.
