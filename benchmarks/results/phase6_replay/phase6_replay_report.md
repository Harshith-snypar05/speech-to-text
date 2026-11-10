# ScriptLiv Phase 6: Parakeet empty-buffer replay

Read-only diagnostic. No fix. Engine: production `ParakeetNativeEngine` class, Parakeet TDT 0.6B v3 q8_0, default parameters, imported read-only (no relay, no VAD, no WebSocket). No relay, VAD, buffering, decoding or UI change. Inputs untouched: `svarah_wer.json` md5 `CCB7FBCF1C434DE7EAABD70BE12EF6C4` (unchanged), `phase5_flush_diag.jsonl` still 87 lines, original WAVs read-only. All outputs are in `results/phase6_replay/`:
- `phase6_replay_results.json`: every sample boundary, sample count, duration, text, empty flag and decode time, per condition and repetition.
- `audio/`: every extracted slice and context variant, plus control slices. File names give clip and condition, and the JSON maps each to the clip and exact sample range.
- Script: `benchmarks/phase6_replay.py`.

## Method and verification
- Exact reconstruction, no estimation. The bench streams `to_pcm16(wav)` plus 1.5 s zero tail in 1600-sample chunks. The relay buffer resets at each flush, so a flush covers `[end - buffer_samples, end)`, with `end = round(audio_received_s * 16000)`.
- Flush boundaries were identical across the three Phase 5 runs.
- For each of the five dropped slices, all of these checks passed:

| check | all five |
|---|---|
| sample count equals recorded `buffer_samples` | yes |
| duration equals recorded `buffer_s` | yes |
| sample rate | 16000 |
| end is a multiple of the 1600-sample chunk | yes |
| start equals the previous flush's end | yes |
| relay RMS rule replayed over the slice gives the recorded speech_s and silence_s | yes |

- Boundary caveat: the trailing disconnect flushes carry ±8 sample rounding from the 3-decimal `audio_received_s` and fail the chunk-multiple check. They are not part of any dropped slice and are not used.
- Replay fidelity controls: 15 control slices (every earlier `final_sent` flush of the same five connections, condition A, x3 each). All 45 replay decodes had the same text length as the relay's recorded `text_len`. So the replay reproduces the relay's engine behaviour, and the empty result of condition A is the relay's empty result.

| clip | dropped slice (samples) | duration | speech_s |
|---|---|---|---|
| assamese_03817 (seq 3) | 256000-315200 | 3.7 s | 2.3 |
| assamese_06152 (seq 2) | 128000-174400 | 2.9 s | 1.9 |
| kannada_00197 (seq 2) | 128000-172800 | 2.8 s | 1.8 |
| kashmiri_03111 (seq 2) | 128000-182400 | 3.4 s | 2.1 |
| bodo_03621 (seq 7) | 251200-297600 | 2.9 s | 0.4 |

## Results (3 repetitions each; the three repetitions were identical in every cell)

| clip | A exact | B +0.5 s | C +1 s | D +2 s |
|---|---|---|---|---|
| assamese_03817 | empty | 8 words | **empty** | 13 words |
| assamese_06152 | empty | 7 words | 7 words | 9 words |
| kannada_00197 | empty | empty | empty | empty |
| kashmiri_03111 | empty | 10 words | 12 words | 14 words |
| bodo_03621 | empty | empty | 4 words | 6 words |

Non-empty texts (B/C/D) for orientation. They are diagnostic, not ground truth, and the context variants include audio that the relay had already finalised in the previous utterance, so some recovered words may repeat the previous final:
- assamese_06152, B: "sixty thousand instead on your no SPI?"; D: "And sent Rs sixty thousand instead on Yono SPI?". The Phase 3 full clip ends "...send Rs sixty thousand instead on Yono SBI?".
- kashmiri_03111, B: "Basin Ladu as their current quantities are out of stock."; D: "Rust cake and Lal Basin Ladu as their current quantities are out of stock." The Phase 3 full clip ends "...Point Rust Cake and Lal Basin Ladu as their current quantities are out of stock."
- assamese_03817, B: "through thick and thin, spill the beans, etc."; D: "Once in a blue moon, through thick and thin, spill the winds, etc." The Phase 3 full clip ends "...Once in a Blue Moon, True Thick and Thin, Spill the Bins, etcetera".
- bodo_03621, C: "access through it and"; D: "people can easily access through it." The Phase 3 full clip ends "...like people can easily access through it and".

## Analysis questions
1. **Exact slice empty consistently?** Yes. 5 of 5 clips, 3 of 3 repetitions, and it matches the Phase 5 relay result.
2. **Left context gives non-empty text?** For 4 of 5 clips, yes. Kannada stayed empty at every context length up to 2 s.
3. **More context improves the result?** Not consistently. For assamese_06152, kashmiri_03111 and bodo_03621 it is monotonic (once non-empty, longer context gives more words). assamese_03817 is non-monotonic: 0.5 s works, 1 s is empty, 2 s works. Kannada never works. So there is a relationship in three clips and not a reliable one overall.
4. **Bodo different?** Yes, in two ways. It needs 1 s of context (0.5 s is still empty), and its slice is weak audio. Peak amplitude is 0.044 (the others are 0.14-0.55), the first 0.5 s is digital zero, and the speech portion is only 0.4 s. It is the only one of the five whose speech is short and weak. The Phase 3 full clip shows the words "access through it and" at this position, so speech is present in the slice, but it is quiet. At 1 s context only those words are recovered.
5. **Reproducible?** Yes. Text and empty/non-empty status were identical across all three repetitions in all 20 conditions. Decode times were stable (A about 0.25-0.33 s, D about 0.41-0.51 s).
6. **What does the evidence point to?**
   - Insufficient left context is supported as a contributing factor for assamese_03817, assamese_06152, kashmiri_03111 (and bodo at 1 s). Adding real audio before an otherwise identical endpoint turns the empty decode into text.
   - Short or weak speech is supported for bodo only (0.4 s speech, peak 0.044).
   - An unresolved engine/audio interaction remains for kannada (loud speech, peak 0.552, 1.8 s speech, empty in all four conditions) and for the non-monotonic assamese_03817 C case. Neither is explained by context or by speech level.

## Conclusion
The empty decode is a property of the exact slice given to Parakeet, not of the relay (timing, pending check and send path were already cleared in Phase 5, and 45 control replays reproduce recorded lengths). Mid-utterance slices that begin right after a forced-cap cut often decode empty with no left context, and real left context recovers text in 4 of 5 clips. But the effect is not a clean "more context is better": one clip is non-monotonic and one never recovers. No single cause is established. Context length alone is not sufficient to explain the data, and I do not claim it as the cause.

Limits: no human listened to any audio. Recovered text was not compared against the previous finals (not logged), so overlap with already-emitted words is unquantified. Five slices only. Phase 3 transcripts used as reference only.

## Recommended next diagnostic step (no fix authorised)
Separate "real context content" from "input length / frame effects", using only the same engine and read-only audio:
1. Replace real left context with synthetic left padding of the same lengths (0.5 / 1 / 2 s of zeros) on the exact slice, to test whether any extra length helps or only real audio does.
2. Shift the slice start by small offsets (for example ±50 / 100 / 200 ms) with no added context, to test sensitivity to where the cut falls. This addresses assamese_03817's non-monotonic result.
3. Inspect kannada_00197 separately: length-sweep the slice and check the parakeet decoder parameters used (`parakeet_full_default_params`) for any minimum-length or chunking behaviour.
4. Quantify overlap of B/C/D text with the previous final, which needs the previous finals' text (re-derivable from the same replay of earlier slices).
Only after these should a narrow remedy (for example overlap context across a forced cap, or not silently dropping empty remainders) be proposed, and each would change buffering or emission behaviour and need explicit approval.
