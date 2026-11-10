# Corpus preparation report (existing 7 recordings)

Scripts: `inventory_existing.py` (decode + working copies), `segment_existing.py` (segments + manifest), `make_pilot_existing.py` (pilot subset + annotation sheet), `analyze_pilot.py` (drafts + aggregates). All in `benchmarks/`. No production, relay, VAD, Parakeet, Flutter, web or schema file was modified. No dataset was downloaded or generated.

## 1. Originals
- Source: `C:\Users\sriha\snypar\stt\data` (7 files, 200 MB). Opened read-only; never written to. SHA-256 per file in `dataset_existing/manifest.json` -> `sources`. MEASURED.

## 2. Working copies
- Decoder: PyAV (bundled ffmpeg libs; no system ffmpeg installed). Pipeline: decode -> mean downmix -> resample 16 kHz -> PCM16 WAV. No gain, filter, trim or normalisation.
- Output: `dataset_existing/audio_full/rec01..rec07.wav` (250.5 min total). Every manifest entry carries a `processing` list.
- rec01-rec04 are Opus in a `.mp3` name; rec05-rec07 are MP3 (44.1 kHz). All converted. MEASURED.

## 3. Segments (configurable 10/20/30/60 s)
Cut rule: middle of the longest silent run in [0.8L, 1.15L] after the segment start; widen to [0.6L, 1.4L]; else the lowest-energy frame, flagged `cut_in_speech_likely`. Silence threshold per recording (cut placement only, not VAD ground truth). Re-run with `python segment_existing.py --lengths 10,20,30,60 --materialize 30`.

| target | entries | pause_cut | cut_in_speech_likely | end_of_recording | duration min / median / max s |
|---|---|---|---|---|---|
| 10 s | 1535 | 1387 | 141 | 7 | 0.02 / 9.76 / 13.96 |
| 20 s | 770 | 718 | 45 | 7 | 3.76 / 19.32 / 27.84 |
| 30 s | 515 | 485 | 23 | 7 | 0.08 / 29.34 / 41.78 |
| 60 s | 261 | 246 | 8 | 7 | 13.28 / 57.26 / 81.64 |

- Total manifest entries 3,081; only the 30 s set (515 WAVs, `dataset_existing/clips/L30/`) is written. MEASURED.
- "Don't cut words" is best-effort. A pause cut falls in an energy gap; it is not word-aligned. `cut_in_speech_likely` clips (rec05 mostly: it has no gaps) may split a word. Final tail clips of a recording can be tiny (e.g. 0.02 s); filter by `duration` before use.
- Segments are NOT independent: same speaker(s), room and microphone within a recording; lengths overlap in time. Use `independence_group` (= recording_id) for any split.

## 4. Manifest
`dataset_existing/manifest.json`. Every clip has: recording_id, source_filename, clip_id, start_time, end_time, duration, sample_rate, channels, speaker_id, language, accent, recording_condition, transcript_path, audio_path (+ boundary_quality, independence_group, transcript_status, processing).

| field | value | status |
|---|---|---|
| speaker_id | null (`speaker_status: unknown`) | UNKNOWN. Not inferred. |
| language | `en` | user-stated, unverified |
| accent | `indian_english` | user-stated, unverified |
| recording_condition | `unknown` | not determined |
| transcript_path / status | null / `transcript_missing` | all 3,081 clips |

Language, accent and recording condition are separate fields.

## 5. Pilot subset
`dataset_existing/pilot/manifest.json` (ws_bench format, `reference: ""`): 20 clips, 3 per recording at 20/50/80% (rec05: 2), pause_cut preferred, 10.1 min of the 30 s set. `dataset_existing/pilot/annotation_sheet.csv` lists each clip for human transcription (`needs_human_transcription`).

## 6. Transcripts
- Verified references: **none exist**. None were supplied with the audio, so there was nothing to verify, preserve or flag.
- Unverified drafts: `dataset_existing/pilot/drafts/<clip>.draft.txt` (20 files), each headed `[UNVERIFIED DRAFT ...]`, taken from Parakeet relay output. They must be corrected by a human before use and are NOT ground truth.
- Human transcripts go in `dataset_existing/transcripts_verified/<clip>.txt` (directory not yet created; nothing written there).
- Normalisation policy once references exist: score with `wer.py` as is (lowercase; strip non-alphanumerics; apostrophes kept; hyphen splits; **no number mapping**). Keep the raw reference and a normalised reference as separate files; report raw and normalised WER with substitutions/deletions/insertions; decide spoken-vs-digit numbers, contractions and disfluencies in the annotation guide before transcribing and apply uniformly.

## 7. Problems
1. No transcripts -> no WER, no per-condition WER.
2. No speaker labels -> no per-speaker metrics, no speaker-disjoint split; recording-level split only.
3. Mislabelled extensions (Opus in `.mp3`) -- handled by the decoder, but downstream tools that trust the extension may fail.
4. Working copies and L30 clips total about 920 MB under `dataset_existing/` (outside source control; not a git repo).
5. 30 s clips run 24-42 s because cuts follow pauses, not the target length.
