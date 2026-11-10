# Svarah WER normalization comparison (Phase 3)

Policies are applied to **copies** of reference and hypothesis tokens inside the analysis script. Original references, transcripts and `results/svarah_wer.json` are unchanged. Micro-averaged corpus WER with the same bootstrap method as `wer.corpus_wer` (60 clips). Normalized WER is a **diagnostic of formatting vs content**, not an accuracy improvement, and must not be quoted as the system's WER.

## Policies (explicit; code in `svarah_error_analysis.py`)
- **A** baseline raw: `wer.normalize` (lowercase, curly apostrophe to `'`, hyphen to space, strip chars outside `[a-z0-9' ]`, no number handling).
- **B** case + punctuation: identical to A by construction (A already lowercases and strips punctuation). Same numbers.
- **C** number format, both sides: `1,000` to `1000`; `3.5` to `3 point 5`; `%` to `percent`; runs of 2+ single digits or digit words become one digit string; runs of number words (units, teens, tens, hundred, thousand, lakh, crore, million; `and` only between number words) become an integer string.
- **D** compound: C plus symmetric join of adjacent tokens `x y` to `xy` when `xy` (length 4+, not digits) occurs as a token on the other side (data-driven; touches only pairs where the other side holds the joined form).
- **E** supplementary, not requested, non-standard: D plus removal of filler tokens {uh um umm uhh uhm hmm hm mm mmm ah er erm eh huh} on both sides.

## Results

| policy | name | ref words | S | D | I | errors | WER | CI95 (%) |
|---|---|---|---|---|---|---|---|---|
| A | raw baseline | 1630 | 134 | 44 | 198 | 376 | 23.07% | 17.9-29.5 |
| B | case+punctuation | 1630 | 134 | 44 | 198 | 376 | 23.07% | 17.9-29.5 |
| C | number format | 1628 | 119 | 47 | 115 | 281 | 17.26% | 13.7-21.7 |
| D | compound | 1624 | 113 | 43 | 113 | 269 | 16.56% | 13.1-20.9 |
| E | D + filler removal (suppl.) | 1624 | 110 | 45 | 55 | 210 | 12.93% | 9.9-16.7 |
| offline_fullclip_policy_A | offline full-clip, policy A (suppl., no VAD) | 1630 | 104 | 14 | 167 | 285 | 17.48% | 12.8-23.7 |

Reference word counts differ across C/D/E because number groups and joins change token counts on both sides.

## What changed
- A to C: 95 fewer errors (376 to 281); insertions 198 to 115. Digit-word expansion vs digit-string references: formatting-related.
- C to D: 12 fewer errors (compound/hyphenation: small).
- Formatting-related total (A to D): 107 of 376 errors (28.5%). Treat as approximate: a digit string that still differs after C collapses to 1 substitution, so real digit errors are partly hidden rather than removed.
- D to E: 59 fewer errors from dropping fillers (insertions 113 to 55). Convention-dependent: references omit most `uh`/`um`; whether they were spoken is unverified. Not counted as formatting in the headline.
- Residual under D: 269 errors (71.5% of baseline). These are not explained by the formatting policies. They contain real recognition differences but also unnormalised reference conventions (`Rs.`/rupees, names, spellings). This is **not** a measured genuine-error count.
- CIs overlap heavily across policies; differences between C, D and E are suggestive, not tested.

## Formatting vs genuine (summary)

| kind | evidence | errors |
|---|---|---|
| formatting (number) | A to C | 95 |
| formatting (compound) | C to D | 12 |
| disfluency convention (uncertain) | D to E | 59 |
| not explained by these policies | residual after E | 210 |

## Limitations
- C can hide digit errors by converting many token errors into one substitution.
- D uses the other side to decide joins, so it can only lower errors: optimistic.
- Names and entities (Vahida/Wahida, Ghanim, bagyals) and non-Latin output are not normalised.
