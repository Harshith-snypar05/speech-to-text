# ScriptLiv Phase 7 — Findings

Scope: **English transcription reliability only** (incl. Indian English accents), existing
architecture and model preserved. Engine: NVIDIA Parakeet TDT 0.6B v3 q8_0 through the existing
whisper.cpp fork. Phase 6B skipped and not reopened. **No production code was changed in
Phase 7** — everything below is either measured observation or a proposal awaiting approval.

Companion documents: `PHASE7_AUDIT_REPORT.md` (defect/observation classification),
`PHASE7_REGRESSION_TEST_REPORT.md` (test evidence), `phase7_baseline.json` (frozen pre-state),
`phase7_results.json` (benchmark run).

---

## A. Missing final transcriptions (empty decode)

**Status: confirmed defect, still present, now pinned by tests. Not fixed (needs approval).**

- The relay drops a pending utterance whose decode returns empty text: no final, no marker, no
  error — the client simply sees nothing. Confirmed end-to-end with the **real model**: buffer
  pending → decode attempted on an open socket → `dropped_empty_text`, `final_constructed=false`,
  zero messages on the wire (`test_phase7_asr.py`, 5/5 cases).
- All five regression fixtures still decode to `""` with no context today:
  `assamese_03817`, `assamese_06152`, `kannada_00197`, `kashmiri_03111`, `bodo_03621`.
- Phase 5's own diagnostics show the empties **cluster**: 18 of 66 decoded flushes (27 %) were
  empty, but they collapse to exactly those 5 buffers (each repeated across runs) — it is not a
  diffuse corpus-wide failure mode.
- The five buffers are 2.8–3.7 s long but contain only **0.4–2.3 s of above-threshold speech**
  (`bodo_03621` has just 0.4 s). All five were flushed on `silence_hang`.
- **Segmentation decides emptiness**: cutting the same slice at an internal pause makes it decode
  to real words (measured), which is why Phase 6's left-context replay fixed 4 of 5. Emptiness is
  a property of the exact buffer, not of the clip.
- Root cause remains **unestablished** (hypothesis H1 in the audit): no single explanation covers
  all five, `kannada_00197` stayed empty even with 2 s of context in Phase 6, and no human has
  listened to this audio. Phase 6B was skipped by instruction.

## B. Audio context across utterance boundaries

**Status: no context exists anywhere today (confirmed); benefit of adding it is a hypothesis with offline support only.**

- `UtteranceBuffer.take()` fully resets; `partial_cycle` reads the same reset buffer. Pinned by
  `test_consecutive_utterances_do_not_share_audio` — utterance 2's PCM contains none of
  utterance 1's marker samples. Nothing duplicates, merges or reorders today.
- Offline (Phase 6): adding left context produced text for 4/5 missing finals — the only
  positive evidence available. It was never wired into the relay.
- Cost if added (from measured RTF ≈ 0.09–0.17): prepending 1.0 s to a typical 3 s utterance
  raises decode work ~30 %, i.e. roughly +0.03–0.10 s on the final path at N=1 — small, but it
  compounds with concurrency because inference is serialized (E).
- Risks: duplicated words at the boundary, shifted timestamps/ordering, repeated finals. All
  three are exactly what the Phase 7 plumbing tests currently assert do *not* happen, so any
  implementation must update those tests deliberately.

## C. Partials

**Status: wire/client reconciliation is correct (confirmed); wording instability is real and measurable (confirmed); cause of instability is a hypothesis.**

- Relay appends only *new* partial words, drops stale cycles after a flush (`generation` guard),
  and resets `words_sent` on every final; the Dart client accumulates partial words and clears
  them on a final, so **final replaces partial, never concatenates** — verified on both sides.
- No duplicate/merge of consecutive finals: `test_consecutive_finals_do_not_duplicate_or_merge_words`.
- Instability: partial words that disagree with the final at the same index —
  **36.1 %** (Phase 3, 60 clips), 41.5 % (Phase 5, 6 clips), 33.1 % (existing-audio pilot, 20 clips);
  prefix-stable only 22.9 % / 23.1 % / 30.2 %. So users can watch text build and then change at
  the final. This is model re-decode variability (relay never retracts a word it already sent),
  not a protocol bug.
- Update cadence: `PARTIAL_CYCLE_SECONDS = 0.5`; each cycle re-decodes the whole growing buffer
  on the same single worker as finals (see E), so cadence, latency and revision rate are coupled.
  Changing any of it is a config/scheduling change → approval required (P3/P5).

## D. English transcription reliability

**Status: benchmark executed (see §D results below and `phase7_results.json`).**

Corpus actually used: `C:\data\corpus_svarah\manifest.json` — **60 clips, 885.6 s total,
10.0–29.3 s each, all tagged `accent=indian_english`, 19 L1 groups (Assamese…Urdu), 16 kHz
PCM16, all files present.** References: **60/60 non-empty, Svarah's own transcripts, independent
of Parakeet** — so WER is permitted. `dataset_existing` (7 recordings, 250.5 min) has **no
verified references** and therefore no WER is calculated or reported for it.

WER is reported in three policies (raw / number-normalized / compound-normalized), never as an
"accuracy score", and never compared across corpora as if comparable.

## E. Concurrency and performance

**Status: architecture facts confirmed from code; cost quantified by the Phase 7 run (below).**

- One model instance per relay process, one `ThreadPoolExecutor(max_workers=1)` plus an
  `asyncio.Lock`: **all inference is serialized across all speakers**. The code itself notes the
  per-session-state API that would allow real concurrency is not implemented.
- Decode speed on this CPU-only build (Phase 5, 66 decodes): RTF p50 **0.091**, p95 0.168,
  mean 0.102; `decode_s` p50 0.343 s, p95 1.013 s, max 1.374 s for buffers up to the 8 s cap.
- `decode_s` includes lock wait (it is timed around `wait_for(transcribe_final)`), so queueing is
  measured by comparing the concurrency-1 and concurrency-2 levels of the same run.
- The RTX 5050 is present but unused: whisper.cpp was built with `GGML_CUDA=OFF`
  (`GGML_VULKAN=OFF`, `GGML_BLAS=OFF`). Biggest latency lever, no model/quantization change —
  but a rebuild + WER-equivalence check, so it needs approval (P4).
- Memory: relay with model ≈ 0.7–1.0 GB working set; this machine has 16.3 GB with ~88 % in use.

---

## Benchmark results (Phase 7 run)

Run: 60 Svarah recordings, **885.6 s** total audio, all `accent=indian_english`, **60/60
independent non-empty references** (Svarah transcripts → WER permitted), 1630 reference words,
1 concurrent speaker session at N=1 / 2 at N=2, unmodified relay on `:8769`, CPU-only, 0
harness errors, wall 1020.5 s (N=1) / 1379.9 s (N=2). Full data: `phase7_results.json`,
`phase7_flush_diag.jsonl`, audit §8.

**WER (N=1, 60 clips):** raw **23.07 %** [17.87–29.53] · number-normalized 17.26 %
[13.75–21.65] · compound-normalized 16.56 % [13.07–20.86]. Normalized values estimate
formatting-related scoring differences only — not improved recognition, and none is an
"accuracy score". **Bit-identical to Phase 3's raw WER on the same 60 clips**
(`0.23067484662576687`) → no regression since Phase 3. No cross-corpus comparison is made.

**WER at N=2:** raw 51.41 % [44.25–58.38] — inflated by 73 abandoned utterances (§E), i.e. a
concurrency-behaviour number, **not** a recognition-quality number.

**Latency (N=1):** first-word p50 **0.885 s** / p95 2.170 s; first-partial p50 0.875 s /
p95 2.143 s; finalization p50 **0.921 s** / p95 1.681 s; final-after-hang p50 **0.369 s** /
p95 1.086 s. **(N=2):** first-word p50 1.291 / p95 7.106 / max 14.980 s; finalization
p50 1.245 / p95 4.258 / max 9.945 s; final-after-hang p50 0.674 / p95 4.218 s.

**Missing / extra finals:** N=1 → **5 missing, 1 extra** (196 matched); the 5 missing are
*exactly* the five named empty-decode cases — the only utterance losses in the whole corpus.
N=2 → **145 missing, 7 extra** (257 matched), dominated by the 73 timeouts.

**Partial stability:** revision **33.8 %** / prefix-stable **24.9 %** at N=1 (34.9 % / 29.4 %
at N=2) — consistent with Phase 3's 36.1 % / 22.9 %; instability is re-decode variability, not
concurrency.

**RTF (relay diagnostics):** N=1 p50 **0.104**, p95 0.177, max 0.360 — fast and stable.
N=2 p50 0.216, p95 3.164 (queue wait inside `decode_s`, not slow inference).

**Concurrency / area E:** at N=2 the completed-decode p50 rises 0.433 s → 1.164 s (**+0.731 s
of pure lock wait**, model work unchanged) and **73 of 404 decodes hit the 10 s
`FINAL_FLUSH_TIMEOUT_SECONDS` and were abandoned** (0 at N=1). Relay CPU 171 % → 351 % of one
core, RSS flat ~730–780 MB, system CPU peaks at 100 %, GPU unused throughout. **Two concurrent
speakers already oversubscribe the single-worker inference path on this CPU-only build.**

---

## Proposed production changes (require approval — none implemented)

| # | Change | Area | Evidence | Risks / must-verify |
|---|---|---|---|---|
| **P1a** | On an empty decode, retry the same buffer once with a bounded left-context tail (≈1.0–1.5 s from the previous utterance), drop only if still empty | A | Phase 6: 4/5 produced text with context; segmentation drives emptiness (measured); defect reproduced 5/5 today | Word duplication across finals (needs suffix de-dup); +1 decode (~0.1–0.3 s) only on the empty path; likely does **not** fix `kannada_00197`; changes relay behaviour |
| **P1b** | Send an explicit "empty final" marker when a pending utterance decodes to nothing | A | 18/66 flushes in Phase 5 were silent drops; client currently cannot tell "heard nothing" from "nothing said" | New wire semantics — Dart parser currently **ignores empty text** and would not clear partials; needs a UI decision (UI changes out of scope unless approved) |
| **P1c** | Keep dropping, diagnostics only (status quo) | A | diagnostics already record every drop | D1 stays a live defect |
| **P2** | Retain ~0.5–1.0 s of previous-audio tail across `take()`, prepend to the next decode, de-duplicate words against the previous final | B | no context exists today (pinned); Phase 6 offline gains | duplicate words, timestamp/ordering shifts, +30 % decode work per utterance, interaction with P1a; needs WER/latency A/B and duplicate/ordering tests first |
| **P3** | Give finals priority over in-flight partial decodes | C/E | single worker + 0.5 s partial cycle ⇒ a flush can wait behind a partial decode (H2; quantified in §D/E results) | changes scheduling; partial cadence becomes burstier; needs A/B on `final_latency_after_hang` and `partial_revision_rate` |
| **P4** | Rebuild whisper.cpp with `GGML_CUDA=ON` | E | dGPU idle while inference is CPU-only; RTF 0.09–0.17 | rebuild/environment only — **no model, quantization, VAD or code change**; must prove WER equivalence before/after |
| **P5** | Not proposed without new evidence: VAD thresholds/hang/cap, `PARTIAL_CYCLE_SECONDS`, parallel inference, second model instance, any model or quantization change | — | explicitly out of scope / unsupported by Phase 7 data | — |

---

## Remaining risks

1. **D1 is still live in production.** English speech that the model decodes as empty disappears
   silently; tests now pin it, but only P1 changes it.
2. **No root cause** for the empty decode; P1a is a mitigation, not a cure, and may miss
   `kannada_00197`.
3. **Single-worker inference caps concurrency** — measured: at 2 concurrent speakers, +0.731 s
   p50 lock wait per decode and **73 utterances abandoned at the 10 s timeout** (audit §8.6).
   Partials share the same queue (P3).
4. **~36 % of partial words disagree with the final** — user-visible instability whose acceptable
   level is a product decision, not a measurement.
5. **CPU-only build** leaves the GPU idle; every latency number here is a CPU number.
6. Benchmark numbers describe **this corpus and this machine only** (Indian-English Svarah clips,
   16.3 GB RAM, ~88 % used, CPU inference) and are not comparable to other corpora' results.
