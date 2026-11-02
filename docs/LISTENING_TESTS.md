# Listening tests

Protocol: docs/TEST_PLAN.md section 6. A release is blocked when any criterion averages under 4.
Scores are given by a human listener (the parent author for the flagship use case). The agent
that builds the project records automated pre-checks only and never fills in human scores.

## Round 1: v1.0.0 candidate (2026-11-02)

### Status

**Human scoring: pending (owner).** The v1.0.0 release gate stays open until the table below is
filled in by the listener. Automated pre-checks are complete.

### Materials

| # | Letter | Language | Profile | Backend and voice | File |
|---|---|---|---|---|---|
| 1 | The Calm Eye of the Storm (letter-calm-in-the-chaos) | en | kid-5 | Kokoro `am_michael` (CPU) | `out/perf/letter-calm-in-the-chaos/letter-calm-in-the-chaos.mp3` |
| 2 | Second letter from the index (owner picks) | en | kid-5 | Maya 2, cloned voice `dad` | render with `mr-audio-smith run <url> --voice dad` on the GPU host |
| 3 | Third letter from the index (owner picks) | en | kid-5 | Maya 2, cloned voice `dad` | as above |
| 4 | Letter 1 | hi | kid-5 | Maya 2, cloned voice `dad`, cross-lingual | `mr-audio-smith run <url> --voice dad --lang en,hi` |

Rows 2 to 4 need the Maya 2 server on an NVIDIA GPU and the owner's registered voice with a
consent record, so they cannot be produced by the build agent.

### Automated pre-checks (letter 1, Kokoro)

| Check | Target | Measured | Result |
|---|---|---|---|
| Integrated loudness | -16 LUFS plus or minus 1 | -16.7 LUFS | Pass |
| True peak | at or below -1.5 dBTP | -1.5 dBFS sample peak (ebur128) | Pass |
| Duration | about 5 minutes (kid-5 target) | 4 min 33 s | Pass |
| Script length | 468 to 702 words | 622 words in 28 chunks | Pass |
| Signature verbatim | exact | "Your calm spot in every storm, Dad" | Pass |
| Emoji, list numbers, navigation read aloud | none | none in the script or captions | Pass |
| Captions | one cue per sentence, within 150 ms | verified by `test_vtt_cues_align_within_150ms` | Pass |

### Scoring sheet (to be filled in by the listener)

Scale 1 (poor) to 5 (excellent). Listen once through on the device your child uses.

| Criterion | Letter 1 | Letter 2 | Letter 3 | Letter 4 (hi) | Average |
|---|---|---|---|---|---|
| Warmth | | | | | |
| Clarity | | | | | |
| Pacing | | | | | |
| Pronunciation (names, places) | | | | | |
| Consistency (same voice throughout) | | | | | |
| Script faithfulness | | | | | |

Notes and fixes (lexicon entries to add, chunks to re-render in Studio):

-
