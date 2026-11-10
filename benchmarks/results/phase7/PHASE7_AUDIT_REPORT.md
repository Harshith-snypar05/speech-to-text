# ScriptLiv Phase 7 — Audit Report: English-focused reliability

**Engine:** NVIDIA Parakeet TDT 0.6B v3 q8_0 via the existing whisper.cpp fork
(`ParakeetNativeEngine`). **No production file was modified in Phase 7.**
**Phase 6B: skipped, not reopened.** Scope limited to English transcription (incl. Indian
English accents); no native-language investigation, no model/quantization/VAD/UI change.

Method: read the relay core (`speaker_session`, `audio_processor`, `flush_diagnostics`,
`session_manager`, `config`, `protocol`), both engines, the Dart client parser, the Phase 3/4/5
reports and Phase 6 replay artifacts; then reproduced each suspect behaviour with tests —
mocks for plumbing, the **real model** for every ASR claim. Every number below is measured on
this machine unless marked as a code-reading.

---

## 1. Confirmed defects

### D1 — An empty decode silently loses the pending utterance (Area A) — STILL PRESENT
- **Behaviour:** `speaker_session.flush()` decodes the pending buffer; if `text` is falsy it
  records `dropped_empty_text`, constructs no final, sends nothing, and the audio is gone
  (`buffer.take()` already reset it). The client sees nothing at all — not an empty line, not
  an error.
- **Evidence:**
  - Phase 5 diagnostics (6 pre-selected mismatch clips, 3 runs): of **66 decoded flushes, 48
    sent a final and 18 (27 %) were `dropped_empty_text`** — but those 18 collapse to exactly
    **5 distinct buffers**, i.e. the emptiness is concentrated in specific clips, not spread
    across the corpus. All 5 were `reason=silence_hang` (`phase5_flush_diag.jsonl`, untouched,
    md5 `cc78e3cd…`):

    | case | buffer | classified speech |
    |---|---|---|
    | `assamese_03817` | 3.7 s | 2.3 s |
    | `assamese_06152` | 2.9 s | 1.9 s |
    | `bodo_03621` | 2.9 s | **0.4 s** |
    | `kannada_00197` | 2.8 s | 1.8 s |
    | `kashmiri_03111` | 3.4 s | 2.1 s |
  - Phase 7, real model, no mocks: all **5/5** missing-final buffers decode to `""`
    (`test_phase7_asr.py::test_empty_decode_without_context_is_still_empty`).
  - Phase 7, real model through a real session loop: buffer pending → decode attempted while
    the socket is open → `outcome=dropped_empty_text`, `decode_attempted=true`,
    `final_constructed=false`, `final_send_called=false`, and **zero** final messages on the wire
    (`test_empty_decode_with_pending_utterance_sends_no_final[5]`).
  - The session recovers: the next utterance transcribes normally (no crash, no stuck state).
- **Impact:** user speaks, nothing appears, no indication anything was missed. This is the
  single highest-impact reliability issue for English use.
- **Not fixed in Phase 7** — fixing it changes relay/user-facing behaviour and needs approval (§5, P1).

### D2 — Test-suite parity assertion was wall-clock dependent (test-only, fixed)
`test_diagnostics_on_off_identical_with_partials` compared raw `partial_calls` lists; the
number of 50 ms cycles that fire varies run to run (2 vs 3) although the wire output is
deterministic. Fixed to compare wire messages + final calls exactly.
*Not a production defect.*

---

## 2. Reproducible observations

### O1 — Whether a buffer decodes to empty depends on its exact segmentation (Area A)
The full 3.7 s `assamese_03817` buffer → `""`, but sub-buffers cut at its internal pauses
decode to real text (measured: 1.3 s → 5-char final, 2.1 s → 26-char final). Same audio, same
model, different cut points. Consistent with Phase 6 (left context produced text for 4 of 5)
and with Phase 5's finding that all five misses happened at a `silence_hang` boundary.
*Consequence: any empty-decode fix must control segmentation, and any test that does not will
silently test the wrong thing (see regression report §4.4).*

### O2 — Audio context is not retained anywhere in the pipeline (Area B)
`UtteranceBuffer.take()` snapshots and fully resets (`buffer`, `silence_s`, `speech_s`);
`partial_cycle` decodes `bytes(buffer.buffer)` — the same reset buffer. There is **no**
previous-utterance context today. Pinned by
`test_consecutive_utterances_do_not_share_audio` (utterance 2's PCM contains none of
utterance 1's marker samples). Phase 6's context experiment was offline replay only and was
never wired into the relay.

### O3 — Partials are append-only on the wire; finals correctly replace partials (Area C)
- Relay: `partial_cycle` sends only `words[words_sent:]` (new words), never re-sends or
  retracts; `flush` resets `words_sent=0` and `generation+=1` so an in-flight partial that
  finishes after a flush is detected as stale and dropped.
- Client: `LiveTranscriptParser` accumulates partial words in a list, and on a final clears
  that list and emits the final text — final **replaces** partial, never concatenates.
- Verified both sides: `test_partial_accumulator_resets_across_a_final` (relay) and the
  existing `st_transcribe_app/test/live_transcript_parser_test.dart` (client).
- Duplicate/merge protection across consecutive finals: `test_consecutive_finals_do_not_duplicate_or_merge_words`.

### O4 — Partial words frequently do not match the final (Area C, user-visible)
From existing benchmark runs (same harness, same model, no Phase 7 change):

| run | clips | partial revision rate | partial prefix-stable rate |
|---|---|---|---|
| Phase 3 `svarah_wer.json` | 60 | **36.1 %** | **22.9 %** |
| Phase 5 `phase5_run1.json` | 6 | 41.5 % | 23.1 % |
| `existing_audio_relay_pilot.json` | 20 | 33.1 % | 30.2 % |

"Revision" = a partial word that differs from the word at the same index in the final. So the
user can watch a partial sentence build and then see words change at the final. The relay never
sends contradictory partials *within* one accumulation, but the model re-decodes the growing
buffer each cycle and rewords ~1 in 3 words. **Hypothesis (H2)** below links this to latency.

### O5 — Every decode in the process is serialized on one worker (Area E, code-confirmed)
`ParakeetNativeEngine` = one `ThreadPoolExecutor(max_workers=1)` (deliberate: GGML thread
affinity, see its docstring) **plus** an `asyncio.Lock`. Partials, finals from every speaker,
and concurrent sessions all queue behind it. The code itself notes the proper per-session-state
API (`*_with_state`) is *not* implemented. Concurrency therefore buys overlap of
network/VAD/audio, never of inference.

### O6 — Inference is CPU-only although a dGPU is present (Area E)
`build-shared/CMakeCache.txt`: `GGML_CUDA=BOOL=OFF`, `GGML_VULKAN=BOOL=OFF`, `GGML_BLAS=BOOL=OFF`;
relay log prints `no GPU found`. RTX 5050 exists but is unused. Not a defect — a build choice —
but it is the largest latency lever available without touching the model or quantization.

### O7 — Decode cost is roughly linear in audio length (Area E, measured)
Sample decodes on this CPU build: 1.3 s → 0.117 s · 2.1 s → 0.182 s · 2.2 s → 0.191 s ·
6.2 s → 0.965 s. Phase 5 diagnostics (66 real decodes) give the distribution:

| metric | p50 | p95 | max | mean |
|---|---|---|---|---|
| `decode_s` (model time + any lock wait) | 0.343 s | 1.013 s | 1.374 s | 0.506 s |
| `buffer_s` (audio decoded) | 3.70 s | 8.00 s (cap) | 8.00 s | 4.75 s |
| **RTF = `decode_s` / `buffer_s`** | **0.091** | **0.168** | 0.173 | 0.102 |

Note on the metric: `decode_s` is timed from just *before* `asyncio.wait_for(engine.transcribe_final(...))`
returns, so it **includes** time spent waiting on the engine's lock — `total_s − decode_s` is
therefore only send time (measured 0.000 s at p95/max). Queueing is isolated the other way:
compare `decode_s` between the concurrency-1 and concurrency-2 levels of the same Phase 7 run
(§8), where any increase is lock wait, not model work.

### O8 — A final flushed after the client disconnects can never be delivered (Area A, low impact)
`flush()` awaits `send()`, but once the peer is gone `send()` raises `ConnectionClosed`, which
the disconnect path logs and swallows. Measured: JFK in one session → 3 decodes, only 2 finals
on the wire because the 3rd flushed after `disconnect()`. **Correct in production** (a closed
peer cannot receive text); it matters only for tests, and only explains part of the missing-final
picture — D1 happens while the socket is open.

### O9 — The softest missed fixture sits below the VAD RMS threshold (Area A context)
`bodo_03621_dropped_A.wav`: overall RMS 0.0056 vs `SILENCE_RMS_THRESHOLD` 0.01, only ~0.2 s of
2.9 s above threshold. The relay still counted it as pending (that is why it was decoded), but
it shows how little acoustic evidence some of these buffers carry. *Observation only — no
VAD change is proposed or permitted.*

---

## 3. Suspected causes (hypotheses — NOT established)

| # | Hypothesis | Supporting | Against / missing |
|---|---|---|---|
| H1 | Empty decode = the model emits no tokens for those exact buffers (too little/too fragmented acoustic evidence at a hang boundary), not a relay bug | 5/5 reproduce offline; sub-buffers decode fine (O1); all five missed at `silence_hang` | Phase 6: 4/5 produced text *with* context and `kannada_00197` stayed empty even at 2 s — no single cause covers all five. **No human listened to any of this audio**, so acoustic claims stay unverified. |
| H2 | Partial decoding competes with final decoding for the single worker, adding up to one partial-decode duration to finalization latency | one worker + lock (O5); `PARTIAL_CYCLE_SECONDS=0.5` while a decode of a 5 s buffer costs ~0.75 s ⇒ cycles run back-to-back during speech | not yet quantified — quantified in §8 by comparing `decode_s` between the concurrency-1 and concurrency-2 levels (lock wait shows up there, model work does not change) |
| H3 | The 36 % partial revision rate is model re-decoding variability, not a relay bug | relay only ever appends (O3); client reconciles at the final | no A/B of cycle length was run; changing it would be a config change (needs approval) |

---

## 4. Changes implemented in Phase 7 (no production behaviour change)

| file | what | production impact |
|---|---|---|
| `relays/tests/test_phase7_regressions.py` (new, 12 tests) | Pins current relay behaviour for all 12 required cases; two tests deliberately assert that context overlap / duplicate merging do **not** exist yet | none (tests only) |
| `relays/tests/test_phase7_asr.py` (new, 12 tests) | Real-model regressions: 5 empty-decode reproductions, 5 empty-decode-through-session, JFK direct + through-session | none (tests only) |
| `benchmarks/results/phase7/phase7_baseline.json` (new) | Frozen pre-Phase-7 state: test counts, artifact md5s, corpus inventory, machine/build facts | none |
| `benchmarks/results/phase7/start_phase7_relay.py` (new) | Starts the **unmodified** relay on port 8769 so Phase 7 diagnostics get their own file while Phase 5's relay keeps 8768 + `phase5_flush_diag.jsonl` | none — imports `parakeet_relay` and overrides `LISTEN_PORT` before `main()`; no file edited |
| `benchmarks/results/phase7/PHASE7_REGRESSION_TEST_REPORT.md`, `PHASE7_FINDINGS.md`, this file | Reports | none |

**Untouched and re-verified:** `svarah_wer.json` (md5 `ccb7fbcf1c434de7eaabd70be12ef6c4`),
`svarah_phase4_rescore.json` (md5 `455eb7788707b52778c864fab7dd784e`),
`phase5_flush_diag.jsonl` (md5 `cc78e3cd1f5494bd7fb2e07affe147f7`, 87 lines),
and every Phase 1–6 report. No relay, VAD, buffer, engine, config, protocol or UI file changed.

---

## 5. Changes requiring approval (NOT implemented)

Each item is stated with the evidence behind it and what could go wrong. Nothing below has been
started.

**P1 — Handle empty decodes instead of dropping the utterance (Area A).**
*Options, in ascending invasiveness:*
- **P1a** On empty text, retry the *same* buffer once with a bounded left-context tail
  (e.g. the last 1.0–1.5 s of audio from the previous utterance), then drop only if still empty.
  Evidence: Phase 6 produced text for 4/5 with context; O1 shows segmentation drives emptiness.
  *Risks:* context can repeat words already sent in the previous final (needs suffix-overlap
  trimming), adds one extra decode (~0.1–0.3 s) only on the empty path, still may not fix
  `kannada_00197`, and touches relay + buffering behaviour.
- **P1b** Send an explicit "empty final" marker for a pending-but-undecodable utterance so the
  client/benchmark can tell "heard nothing" from "nothing said".
  *Risks:* new wire semantics — the current Dart parser **ignores empty text** (it returns
  before clearing partials), so this is a client-visible protocol change and needs a UI decision
  (UI changes are out of scope unless approved).
- **P1c** Keep current behaviour (drop) and rely on diagnostics only. *Risk:* D1 stays.
*Recommendation:* P1a first — smallest change that addresses measured evidence; P1b only if you
want the miss to be visible in the product.

**P2 — Retain a small previous-audio context across utterance boundaries (Area B).**
Keep ~0.5–1.0 s of the tail of the previous buffer in `UtteranceBuffer.take()` and prepend it to
the next decode, with word-level de-duplication against the previous final.
*Evidence:* O2 (no context exists today), Phase 6 (4/5 improve with context).
*Risks:* duplicated words between consecutive finals, timestamp/ordering shifts, higher decode
cost per utterance (≈ +30–70 % audio per decode → measurable on CPU-only), and it interacts with
P1a. Requires: duplicate-word prevention tests, ordering tests, and a WER/latency A/B before
adoption. **Do not assume it fixes every missing final.**

**P3 — Let finals preempt partials (Area C/E, inference scheduling).**
Currently a flush waits for an in-flight partial decode (H2). Priority for finals would cut
finalization latency without changing accuracy.
*Evidence:* §8 queue-wait figures.
*Risks:* changes scheduling; partial cadence becomes burstier; needs an A/B on
`final_latency_after_hang` and `partial_revision_rate` before adoption.

**P4 — Build whisper.cpp with `GGML_CUDA=ON` (Area E, performance only).**
*Evidence:* O6 (dGPU idle, CPU-only build), O7 (RTF 0.13–0.16 CPU).
*Risks:* rebuild/environment change only — **no model, quantization, VAD or code change**;
must be validated for identical WER before/after (the q8_0 file is unchanged, but backend
numerics can differ slightly). Would need its own approval + a WER equivalence check.

**P5 — Not recommended without new evidence:** changing `PARTIAL_CYCLE_SECONDS` (0.5 s),
`SILENCE_HANG_SECONDS` (0.6 s), `MAX_UTTERANCE_SECONDS` (8 s), `SILENCE_RMS_THRESHOLD` (0.01),
or adding a second model instance / parallel inference. Each is explicitly out of scope or
unsupported by Phase 7 data.

---

## 6. Unresolved issues

1. **Root cause of the empty decode is still not established** — no single explanation covers
   all five (H1). Phase 6B was skipped by instruction and is not reopened. Resolving it would
   require listening to the five buffers (no human has) or controlled acoustic experiments.
2. **`kannada_00197` stayed empty even with 2 s of context** in Phase 6 — P1a may not fix it.
3. **Whether context overlap is net-positive in production** (accuracy vs duplicate-word risk)
   is untested in the live path; only offline replay exists.
4. **Whether the 36 % partial revision rate is acceptable UX** is a product judgement, not a
   measured defect.
5. **Single-instance inference ceiling** (O5): with N concurrent speakers, all inference is
   serial; §8 quantifies what that costs at N=2 on this machine.

---

## 7. Test results

- relays: **106 passed, 1 skipped** (was 82 + 1 before Phase 7; +24 new), run twice, no flakes.
- benchmarks: **34 passed** (unchanged).
- The single skip is pre-existing (subprocess `parakeet-cli` fallback not built).
- Details, per required case: `PHASE7_REGRESSION_TEST_REPORT.md`.

## 8. Benchmark results (Phase 7 run)

Full data: `phase7_results.json` (harness output) + `phase7_flush_diag.jsonl` (relay-side
diagnostics, summarised by `summarize_phase7.py`). Raw stdout: `phase7_bench_stdout.log`.

**Run context.** 60 recordings, 885.6 s total audio (10.0–29.3 s each), 16 kHz PCM16, all
`accent=indian_english`, 1630 reference words. **Reference availability: 60/60 non-empty**,
Svarah's own transcripts, independent of Parakeet → WER permitted. Speakers: 1 concurrent
session at N=1, 2 concurrent sessions at N=2 (levels run sequentially). Unmodified relay on
`:8769` (launcher `start_phase7_relay.py`), Parakeet TDT 0.6B v3 q8_0, CPU-only, 0 harness
errors at either level. Wall time: 1020.5 s (N=1), 1379.9 s (N=2).

### 8.1 WER (three policies, N=1 — 60 clips, 1630 ref words)

| policy | WER | bootstrap 95 % CI |
|---|---|---|
| **raw** (baseline) | **23.07 %** | [17.87, 29.53] |
| number-normalized | 17.26 % | [13.75, 21.65] |
| compound-normalized | 16.56 % | [13.07, 20.86] |

Normalized values are a *diagnostic estimate of formatting-related scoring differences*, not
better recognition — the transcripts are unchanged. None of these is an "accuracy score".
WER reflects both model errors and natural variation against a single reference transcription
of spontaneous speech.

**Same-corpus reproducibility check (valid: identical corpus, harness, model):** Phase 3's
`svarah_wer.json` raw WER on these same 60 clips is `0.23067484662576687` — **bit-identical**
to this run. Nothing regressed between Phase 3 and Phase 7. (Cross-corpus numbers are *not*
compared anywhere in this phase.)

### 8.2 WER at N=2 — NOT a recognition-quality number

raw 51.41 % [44.25, 58.38] (120 clip-runs, 3260 ref words), number 48.34 %, compound 48.03 %.
**Do not read this as the model getting worse under load.** At N=2 the relay abandoned 73
utterances at the 10 s final-flush timeout (§8.4), so whole phrases are absent from the
hypothesis — the inflation is dominated by *dropped utterances*, i.e. it measures system
behaviour under concurrency, not recognition accuracy. Reported for completeness with that
caveat attached.

### 8.3 Latency (audio captured → text received; excludes mic/UI/tunnel)

| metric | N=1 p50 / p95 / max (n) | N=2 p50 / p95 / max (n) |
|---|---|---|
| first-word latency (ttfw) | 0.885 / 2.170 / 7.594 s (196) | 1.291 / 7.106 / 14.980 s (252) |
| first-partial latency | 0.875 / 2.143 / 4.918 s (189) | 0.969 / 2.484 / 4.057 s (189) |
| finalization latency | 0.921 / 1.681 / 2.690 s (196) | 1.245 / 4.258 / 9.945 s (257) |
| finalization after hang | 0.369 / 1.086 / 1.689 s (159) | 0.674 / 4.218 / 9.345 s (219) |
| final after flush start | 0.461 / 1.144 / 2.690 s (196) | 0.743 / 3.660 / 9.345 s (256) |

N=1 is healthy: a final lands ~0.37 s after the speaker stops. N=2 p95s are dominated by lock
queueing and the 10 s abandonment ceiling (max 9.945 s ≈ just under the timeout).

### 8.4 Missing / extra finals (timestamp matching, one-to-one monotonic)

| | matched | **missing finals** | **extra finals** | clips affected |
|---|---|---|---|---|
| N=1 | 196 | **5** | **1** | 6 |
| N=2 | 257 | **145** | **7** | 62 |

At N=1 the 5 missing finals are **exactly the five named empty-decode cases**
(`assamese_03817`, `assamese_06152`, `bodo_03621`, `kannada_00197`, `kashmiri_03111`) — the
only utterance losses in the entire 60-clip corpus, and the same 5 the diagnostics show as the
only `dropped_empty_text` buffers. The 1 extra final is on `bengali_01831`. At N=2 the 145
missing are dominated by the 73 timeouts plus their knock-on effects.

### 8.5 Partial stability

| | partial revision rate | prefix-stable rate |
|---|---|---|
| N=1 | **33.8 %** | 24.9 % |
| N=2 | 34.9 % | 29.4 % |

Consistent with the earlier same-harness runs (Phase 3: 36.1 % / 22.9 %). Wording instability
is stable across runs and load levels — it is a property of re-decoding the growing buffer,
not of concurrency.

### 8.6 Relay-side diagnostics (flush level) and RTF

789 flush records total (`conn_id` 1..181).

| | N=1 segment | N=2 segment |
|---|---|---|
| flushes / decodes | 266 / 205 | 523 / 404 |
| finals sent | 200 | 322 |
| `dropped_empty_text` | 5 (**5 distinct buffers** = the named cases) | 9 (same 5 buffers) |
| **`dropped_timeout` (10 s)** | **0** | **73** |
| `dropped_not_pending` | 61 | 119 |
| decode p50 / p95 (completed only) | **0.433 / 1.122 s** | 1.164 / 8.879 s |
| decode max (completed) | 2.881 s | 9.967 s |
| **RTF p50 / p95 / max** | **0.104 / 0.177 / 0.360** | 0.216 / 3.164 / 8.915 |
| buffer p50 | 3.8 s | 3.4 s |

- **Queue wait (H2, now quantified):** completed-decode p50 rises 0.433 s → 1.164 s
  (**+0.731 s**) at N=2. Model work is identical between levels, so that delta is lock wait —
  partial cycles (0.5 s cadence, both speakers) plus finals saturate the single worker.
- **The N=2 p95/max RTF ≫ 1 is queue wait inside `decode_s`**, not slow model inference
  (`decode_s` is timed around `wait_for(transcribe_final)` and therefore includes lock wait).
- **73 utterances were abandoned at `FINAL_FLUSH_TIMEOUT_SECONDS=10`** (all at N=2, none at
  N=1) — each is a silent loss for that speaker. This is the headline area-E finding.

### 8.7 CPU and memory

| | N=1 | N=2 |
|---|---|---|
| relay CPU (mean / max, % of one core) | 171 / 404 | 351 / 411 |
| relay RSS (mean / max) | 738 / 784 MB | 728 / 755 MB |
| system CPU (mean / max) | 13.8 / 55.5 % | 39.1 / 100.0 % |
| GPU utilisation | ~0 % (unused, `GGML_CUDA=OFF`) | ~0 % |

Memory is flat across load (the model dominates: ~0.7–0.8 GB working set). CPU roughly
doubles from N=1 to N=2 and the system saturates at 100 % at peak — inference itself is
serialized, the extra CPU is decode threads + audio/VAD work of two sessions.

### 8.8 Concurrency summary

N=1: healthy — 0 timeouts, 5 missing finals (all the known defect), RTF 0.104, finals 0.37 s
after hang. N=2: **not production-safe at parity** — 73 abandoned utterances, finalization p95
4.2 s, ttfw p95 7.1 s, WER inflated by the drops. Two concurrent speakers already oversubscribe
the single-worker inference path on this CPU-only build.

## 9. Files touched by Phase 7

New only — no existing file modified:

```
relays/tests/test_phase7_regressions.py          (new, 12 tests)
relays/tests/test_phase7_asr.py                  (new, 12 tests, real model)
benchmarks/results/phase7/phase7_baseline.json
benchmarks/results/phase7/PHASE7_AUDIT_REPORT.md        (this file)
benchmarks/results/phase7/PHASE7_FINDINGS.md
benchmarks/results/phase7/PHASE7_REGRESSION_TEST_REPORT.md
benchmarks/results/phase7/start_phase7_relay.py
benchmarks/results/phase7/phase7_relay.log               (relay stdout/stderr, :8769)
benchmarks/results/phase7/phase7_flush_diag.jsonl        (Phase 7 diagnostics only)
benchmarks/results/phase7/phase7_bench_stdout.log
benchmarks/results/phase7/phase7_results.json            (benchmark run)
```
