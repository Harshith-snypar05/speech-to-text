# Svarah compatibility audit

**Recommendation: `READY_WITH_LIMITATIONS`**

Scope: AI4Bharat Svarah only. No production, relay, VAD, Parakeet or app file was touched. Dataset lives outside the repo
(`C:\data\svarah`, read-only use). No transcript or annotation was created. This report holds aggregates only: no clip audio,
no reference text, no per-speaker rows.

Measured on the real data (HF access granted after login). Scripts: `svarah_adapter.py inspect|export`, `audit_loudness.py`.
Raw aggregates: `svarah_measured.json`.

## 1. Measured facts

| Item | Result |
|---|---|
| Rows / split | 6,656 rows, single `test` split, 3 parquet shards |
| Container | 6,656 / 6,656 RIFF WAV, PCM |
| Sample rate / channels / depth | all 16 kHz, mono, 16-bit. No resampling or downmix needed |
| Header duration vs metadata `duration` | 0 mismatches (>0.1 s) |
| Total | 9.614 h; mean 5.2 s; median 4.21 s; max 29.87 s |
| Clips < 3 s | 2,442 (37%) |
| Clips 10-60 s | **810 (12%)**, all between 10 s and 29.87 s. Nothing above 30 s |
| 10-60 s clips per L1 | all 19 L1s present, 16 to 129 each (Nepali 129, Bodo 67 ... Sindhi 16) |
| Empty references | 0 |
| Switchboard-style markers (`[..]`, `{..}`, `<..>`) | 0 found, so marker stripping is a no-op |
| Reference style | mixed-case, 3,119 of 6,656 with punctuation, 769 contain digits, 273 hyphens, 59 other special characters; 10.4 words per row |
| Metadata | 19 L1s, 17 states, 65 districts. State count is 17, resolving the paper's 17/19 inconsistency |
| Licence | CC BY 4.0 (card confirmed after login). Cite Javed et al., Interspeech 2023 |

Level and noise (frame RMS, 20 ms frames, int16 scaled to 1.0):

| | all 6,656 | 10-60 s (810) |
|---|---:|---:|
| 95th-percentile frame RMS, median | 0.144 | 0.140 |
| Noise-floor estimate (10th-pct RMS), median | 0.0030 | 0.0015 |
| Est. SNR dB p5 / median / p95 | 18.6 / 32.0 / 48.3 | 24.8 / 37.7 / 55.4 |
| Peak median | 0.49 | 0.57 |
| Clips with clipping >0.1% of samples | 7 | 0 |
| Clips with p95 RMS < 0.05 (quiet) | 920 (14%) | 113 (14%) |
| Clips with floor >= 0.01 (fixed-VAD threshold) | 957 (14%) | 18 (2%) |
| Leading / trailing quiet, median | 0.08 s / 0.10 s | 0.14 s / 0.22 s |
| Fraction of frames >= 0.01 RMS, median | 0.74 | 0.66 |

Reading: audio is clean (median est. SNR 32-38 dB), phone-level, with a useful quiet tail (14% of clips are quiet) but almost no
real noise (only 2% of the 10-60 s clips have a floor high enough to confuse the fixed 0.01 threshold). Leading and trailing
silence is short (median under 0.25 s), so clips are tight cuts, not recordings with real pauses.

## 2. Speaker key: not recoverable

Filenames follow `<long number>_f<number>_chunk_<n>.wav`. Checked as speaker key: 2,938 distinct leading numbers and 3,232
distinct `f` numbers against about 117 speakers in the paper. Neither is a speaker id. The leading number never spans two L1s,
so it looks like a recording task or session id. Consequence: no speaker-disjoint split is possible. Best available holds out
by the leading recording id (recording-disjoint, not speaker-disjoint) or by whole L1. Any tuning/report split must say which.

Metadata quirk: some metadata strings carry HTML entities (e.g. `&amp;` in `occupation_domain`). Carried through to tags as-is;
normalise before grouping.

## 3. Read vs spontaneous

No column. The paper gives hour totals only (1.4 h read, 6.4 h extempore, 1.7 h use-case). Not inferable per clip without
inventing labels, so none is made. Sliced WER by speech type is therefore unavailable. Longer clips are plausibly extempore, but
that is an assumption, not a measurement.

## 4. Ingest compatibility (`ingest_corpus.py`)

`ingest_corpus.py` does not read parquet. A small isolated adapter is required and exists: `svarah_adapter.py export`.

Real-data test (outside repo): `export --min-dur 10 --max-dur 60 --limit 60 --seed 0` then `ingest_corpus.py`:
60 eligible-clip subset exported (810 eligible), **60 ingested, 0 rejected**, 14.8 min, all 19 L1s covered (3-4 each), no warnings.

| Concern | Result |
|---|---|
| Audio loss | None. Original WAV bytes written unchanged; already 16 kHz mono 16-bit, so ingest resample is identity |
| Metadata | 8 columns mapped to tags via sidecar JSON; original text, shard and row kept in `meta.notes`. Nothing dropped |
| Transcripts | No markers present, so references are verbatim. Numbers: `wer.py` does no number mapping; 769 rows (12%) contain digits, so "12" vs "twelve" will count as errors. Normalise or tag those clips before reading WER |
| Case/punctuation | `wer.py` lowercases and strips non-alphanumerics, fine. Hyphenated words become one token |
| Short clips | Not an issue at the 10 s floor; below 3 s ingest warns |

Conversion script needed: yes, parquet adapter only (done). No audio conversion needed.

## 5. What Svarah supports

| Capability | Verdict | Reason |
|---|---|---|
| ASR WER, Indian English | **Yes** | Clean 16 kHz WAV, human references, 19 L1s, 810 clips at 10-30 s |
| WER by L1, gender, age, qualification | **Yes** | Tags carried through |
| WER by read vs spontaneous | No | No label |
| Speaker-disjoint evaluation | No | No speaker id |
| VAD speech recall | Partial | No in-clip speech labels. Energy-derived labels are circular for an energy VAD |
| False activation | No natively | Clips have <0.25 s median edge silence; no known non-speech spans. Only with constructed scenes |
| Missed flush | No natively | Isolated segments, no natural pauses of 0.6 s+. Only with constructed scenes (known gaps) |
| Quiet speech | Partial | 14% of clips have p95 RMS < 0.05, a natural level range. Gain scaling beyond that is synthetic |
| Background noise | No real noise | Median est. SNR 32-38 dB; mixing must be synthetic |
| First-word latency, partials, concurrency | Yes as input material | Use as replay audio; no label needed |

## 6. Missing conditions (need your own recordings)

1. Continuous 10-60 s speech with natural 0.6-2 s pauses (flush/hang/cap, VAD ground truth).
2. Real noise: cafe, street, fan, keyboard, babble, with and without speech.
3. Laptop/desktop/headset microphones, distant and genuinely quiet speakers (Svarah is phone-only, instructed quiet room).
4. Technical vocabulary and acronyms (Svarah is general domain).
5. Code-switching; numbers spoken the way Parakeet writes them.
6. Multi-speaker, overlap, long (5-30 min) sessions. Max clip here is 29.87 s.
7. Speech start/end annotations.
8. Speaker ids for a speaker-disjoint held-out split.

## 7. Next phase: exact commands

Already done (outside repo, 60-clip subset, seed 0):
```
cd C:\Users\sriha\snypar\stt\speech-to-text\benchmarks
python dataset_audit\svarah_adapter.py export C:\data\svarah\data --out C:\data\svarah_raw --min-dur 10 --max-dur 60 --limit 60 --seed 0
python ingest_corpus.py C:\data\svarah_raw --out C:\data\corpus_svarah --tag corpus=svarah
```
Larger set, all 810 eligible clips (about 3.0 h-class audio, long relay run; do only when ready):
```
python dataset_audit\svarah_adapter.py export C:\data\svarah\data --out C:\data\svarah_raw_all --min-dur 10 --max-dur 60 --limit 0
python ingest_corpus.py C:\data\svarah_raw_all --out C:\data\corpus_svarah_all --tag corpus=svarah
```
WER run on the 60-clip set. Needs the relay running and your go-ahead (live relay test):
```
python ws_bench.py --manifest C:\data\corpus_svarah\manifest.json --out results\svarah_wer.json --note "CPU, Parakeet 0.6b v3, Svarah 60-clip subset"
```
VAD on real clips (not built: `run_experiment.py` is synthetic-only). A real-corpus mode would build scenes from these clips with
known inserted gaps (S 0.3 s must not flush, L 1.2 s must flush) and mixed noise from `make_corpus.py`. Say so to build it.
Split design: fix thresholds on half the recording ids, report on the other half. Not speaker-disjoint; say so.

## 8. Handling rules followed
Dataset outside the repo; reports hold aggregates and scripts only; original files never written to; no reference text or
annotation invented; cite AI4Bharat Svarah (CC BY 4.0) in any published result. HF token not stored in the repo.

## 9. Verdict
`READY_WITH_LIMITATIONS`. Format is clean (all 16 kHz mono 16-bit WAV), ingest loses nothing, and 810 clips at 10-30 s support an
Indian-English ASR WER benchmark now. Not suitable for VAD false-activation, missed-flush or real-noise claims, has no speaker id
or read/spontaneous label, and nothing above 30 s. Items 1-3 and 7 of section 6 still need your own recordings.
