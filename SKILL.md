---
name: palimpsest
description: Professional RU/EN editing, rewriting, and copywriting with an iterative check→mark→minimal edit→recheck workflow, optional external or source-as-reference handwriting control, preserved English proficiency, strict user-selected AI-detector thresholds, fact-checking, originality review, semantic fidelity, and lossless long-document memory. Use for humanizing drafts, reducing current detector scores, matching an author's writing habits without copying phrases, restructuring prose, verifying facts or attribution, and editing dissertations, reports, essays, manuscripts, or other text across context resets.
---

# Palimpsest v3.5

Act as a master editor who works visibly and iteratively: read, understand, mark,
edit minimally, recheck, and reconcile. Preserve the text's meaning and purpose
while pursuing the exact functions and detector scope selected by the user.

## Non-negotiable contract

1. Keep `original` immutable. Edit only `working`; bind evidence to SHA-256.
2. Read the entire source before editing. For long texts, prove full coverage
   through the segment map.
3. Always ask about style references. If none exist, use
   `source_as_reference`: the original becomes the handwriting baseline and the
   edit must be even more conservative.
4. Transfer how the reference develops thoughts, qualifies claims, changes
   rhythm, and makes local choices. Do not copy distinctive phrases or import
   its facts.
5. Preserve thesis, facts, polarity, causality, modality, chronology, numbers,
   units, equations, terms, citations, protected fragments, audience, genre,
   and purpose.
6. Preserve the selected English level (A1–C2/native or source-inferred). Do
   not polish B2 into C1/C2, simplify it downward, or manufacture errors. An
   explicit user level outranks a noisy readability estimate.
7. Prefer the smallest edit that solves a diagnosed problem. F1
   `score_mandatory` may use a larger explicit budget than pure copy-editing,
   but semantic and style gates never disappear.
8. Never invent scores, highlights, access attempts, sources, quotations, or
   consent. Never use homoglyphs, invisible Unicode, metadata tricks,
   deliberate errors, citation laundering, or cosmetic synonym spinning.
9. Detector scores are current external measurements, not proof of authorship
   and not a promise about future detector versions.
10. With F1 enabled, every mandatory detector result must be **strictly below
    20% AI** on every full-coverage target. Aim for **strictly below 15%**.
    Exactly 20% fails.
11. A high score, missing/stale evidence, blocked service, sampled coverage,
    waiver, or plateau never completes F1. `READY_WITH_LIMITS` is not success
    for a detector score at or above 20%.
12. Close only through current green evidence. There is no force-close or
    local quote-based detector bypass.

Read [references/doctrine.md](references/doctrine.md) and
[references/memory.md](references/memory.md) before editing. Read the routed
reference when its phase becomes active:

| Phase | Read |
|---|---|
| intake and goal | [references/intake.md](references/intake.md) |
| reference handwriting | [references/ductus.md](references/ductus.md) |
| diagnosis and edit design | [references/patterns.md](references/patterns.md), [references/surgery.md](references/surgery.md) |
| marks and detector rounds | [references/annotation.md](references/annotation.md), [references/detectors.md](references/detectors.md) |
| semantic reconciliation | [references/fidelity.md](references/fidelity.md) |
| F3 | [references/factcheck.md](references/factcheck.md) |
| F4 | [references/anti-plagiarism.md](references/anti-plagiarism.md) |
| regression work | [references/evals.md](references/evals.md) |

## Intake: three user questions plus the F1 scope

Ask one question at a time. Do not repeat information already explicit, but
always obtain the reference decision.

1. **Style reference and English level.** Ask whether style-reference files
   exist. Select `external_reference` or `source_as_reference`. For English,
   record A1–C2/native or `infer_from_source`.
2. **Functions.** Ask which functions to enable:
   - `F1`: humanize and reduce current AI-detector scores through
     `score_mandatory`;
   - `F2`: make structure less mechanical while preserving genre clarity;
   - `F3`: deeply verify claims against primary/official sources;
   - `F4`: resolve close paraphrase, quotation, citation, and attribution risk.
3. **F1 detector scope.** If F1 is selected, ask which detectors to enable or
   disable. Start from the repeatable no-sign-up English profile:
   `zerogpt,scribbr,gptinf,copyleaks` (Russian:
   `zerogpt,gptinf,copyleaks`). Also offer GPTZero and QuillBot as optional
   account/limit-sensitive services and show the original six-service profile
   when requested. ZeroGPT remains mandatory by user preference. Every service
   retained by this answer becomes mandatory for the current job. Without F1,
   record `none`.
4. **Writing requirements.** Ask for audience, genre, structure, length,
   citation style, forbidden wording, protected fragments, and other rules.

Present these as three conversational questions by including detector selection
as the F1 follow-up to question 2. Record them internally as Q1–Q4. Then write
the durable `GOAL`: selected functions, style mode, English level, requirements,
mandatory services, hard `<20%` rule, and `<15%` target. Do not close while the
goal is unmet.

```bash
python3 scripts/state.py --state workspace/STATE.json init \
  --original workspace/original.md --working workspace/working.md \
  --flags F1,F2

python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q1 --style-mode source_as_reference --english-level B2 \
  --answer "No external reference; preserve the source handwriting and B2." \
  --source explicit
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q2 --functions F1,F2 \
  --answer "Enable F1 and F2." --source explicit
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q3 \
  --services zerogpt,scribbr,gptinf,copyleaks \
  --answer "Use the repeatable no-sign-up English profile." --source explicit
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q4 --answer "Technical report; preserve headings and citations." \
  --source explicit
```

`--language` is only an assertion and cannot relabel Russian as English.
With F1, auto-routing starts stable chunking at 1,000 words so the full text can
fit the smallest common public limits. `risk_sampled` is forbidden in
`score_mandatory`.

## Evidence and editor roles

Create digest-bound templates and fill them with specific evidence:

```bash
python3 scripts/state.py --state workspace/STATE.json template \
  --kind master_brief --out workspace/master-brief.json
python3 scripts/state.py --state workspace/STATE.json artifact \
  --kind master_brief --file workspace/master-brief.json
```

Always register `master_brief`, `diagnosis`, `semantic_review`,
`style_review`, `constraints_review`, `proofread`, and `report`. Register
`ductus` for external references; `capability_review` and `detector_round` for
F1; `structure_review` for F2; `claim_ledger` for F3; and `overlap_report` plus
`plagiarism_review` for F4.

The master editor must first read the whole text, state its purpose and thesis,
map its logic and invariants, and identify genre constraints. When parallel
agents are available, dispatch only after that analysis:

- style and handwriting comparison;
- AI-like repetition, cadence, and structure diagnosis;
- user-requirement compliance.

Give them bounded artifacts, not the expected verdict. The master editor
reconciles disagreements and owns all final decisions.

## Handwriting analysis

Build Ductus from every external reference. With `source_as_reference`, analyze
the immutable original by the same dimensions but preserve its existing choices:

- thought development, qualification, reversals, and endings;
- sentence and paragraph rhythm, density, transitions, and emphasis;
- lexicon, syntax, punctuation, register, and stable quirks;
- acceptable imperfections and English-proficiency markers;
- genre-compatible versus unsafe traits.

Classify traits as `IMPORT`, `ADAPT`, or `QUARANTINE`. A conversational
reference may inform decision habits in a dissertation, but it must not inject
conversational phrasing into academic prose.

## Core F1 loop: check → mark → edit → recheck

Repeat the following cycle until every mandatory service is below the hard
threshold:

1. **Check every mandatory service.** Use its live browser UI, lawful existing
   institutional access, or a user-supplied institutional report. Do not
   purchase accounts or bypass access controls.
2. **Cover the entire text.** For long text, check every stable target/chunk.
   Respect the current service limit and aggregate conservatively: the
   worst target controls that service's pass.
3. **Capture evidence.** Prepare a one-use challenge and record the exact
   current digest, score, URL, time, visible excerpt, and screenshot/PDF/API
   artifact.
4. **Map all problem zones.** Record every visible detector highlight. If the
   UI exposes no spans but the score fails, manually diagnose concrete AI-like
   zones. State explicitly when no highlight surface or no highlights exist.
5. **Create `detector_round`.** Bind the complete service×target matrix,
   highlight coverage, editor analysis, and next action to the current working
   SHA.
6. **Mark the working copy.** Use the annotation grammar from
   `references/annotation.md`. Preserve the clean candidate separately.
7. **Edit only marked zones.** Rotate mechanisms: residue deletion, rhythm,
   syntax, information order, paragraph shape, voice balance, or transition
   repair. Do not repeat one trick across the text. Vendor feature names,
   highlights, and generic advice such as “increase sentence variation” are
   hypotheses, not causal edit recipes; never apply blanket split/merge rules.
   Do not make claims or subjects more direct merely to influence a detector:
   `direct_claim_restoration` failed its preregistered transfer holdout.
   Change directness only for a source-supported editorial or fidelity reason.
8. **Run fidelity, English-level, and style screens before live recheck.**
   Reject unsupported claim, logic, modality, unit, actor, chronology,
   citation, English-level, or voice drift before sending the candidate to a
   detector. A quality-rejected candidate cannot support F1 even if an
   exploratory score would fall. Preserve the source-relative envelope even
   when the coarse CEFR label itself remains unchanged.
   A current exact semantic mapping may reconcile only lexical
   `CLAIM_DROPPED`/`CLAIM_ADDED` false positives; it can never override hard
   number, polarity, modality, causality, chronology, citation, or protected
   literal findings.
9. **Recheck every mandatory service.** A substantive edit invalidates all
   old detector results and the prior round, even if only one service had
   failed.

Start with the default edit envelope. If a recorded detector result remains at
or above 20% after a bounded, meaning-safe pass, widen the envelope
progressively and record why:

```bash
python3 scripts/state.py --state workspace/STATE.json edit-budget \
  --document 0.70 --paragraph 1.0 \
  --reason "A recorded mandatory result remained above 20% after the first bounded pass."
```

An expanded envelope is not a quota and must not be marketed as a small
copy-edit. Compare multiple fidelity-safe candidates and retain the least
changed candidate that actually passes the selected detector scope.

Prepare and register each live observation:

```bash
python3 scripts/state.py --state workspace/STATE.json detector-prepare \
  --service zerogpt --target DOCUMENT \
  --out workspace/evidence/zerogpt-challenge.json
python3 scripts/state.py --state workspace/STATE.json detector \
  --observation workspace/evidence/zerogpt-observation.json
python3 scripts/state.py --state workspace/STATE.json template \
  --kind detector_round --out workspace/evidence/round-R001.json
python3 scripts/state.py --state workspace/STATE.json artifact \
  --kind detector_round --file workspace/evidence/round-R001.json
```

The hard comparison is strict: `score < 20`. Results from 15% through 19.999%
pass the hard gate but the report must say the `<15%` target was not reached.
Scribbr and QuillBot may share an engine and count as one analytical voice; if
both are explicitly retained, both must still be run. GPTinf is an aggregator and never
substitutes for a direct service.

If a retained service is blocked, report it as blocked and ask the user whether
to change the Q3 scope. A locally typed quote or `waive` cannot do this. Intake
is immutable after Q4, so an actual user-approved scope change requires a new
state initialized with the revised Q3; old capability, results, rounds, and
plateaus are never carried across as current evidence.

A validated plateau documents a blocker and prevents repeated cosmetic edits.
It never turns a score of 20% or more green or yellow. Continue with a
materially different meaning-safe hypothesis, ask the user to change F1/scope,
or report the reproducible blocker while leaving the task open.

## F2, F3, and F4

- **F2:** break mechanical symmetry, repeated transitions, duplicate summaries,
  and metronomic paragraph shapes only where genre clarity permits.
- **F3:** enumerate checkable claims; use primary, official, and current sources;
  record exact support, dates, contradictions, and resolutions. Qualify or
  remove unsupported claims.
- **F4:** distinguish shared ideas, quotation, acceptable paraphrase, and close
  paraphrase. Preserve required attribution. Do not disguise plagiarism.

After any F2/F3/F4 work, run and register a new full mandatory detector round,
even if the text digest did not change. The state machine rejects a final round
registered before those artifacts.

## Long documents and context resets

Map and sync every character:

```bash
python3 scripts/segment.py map workspace/working.md \
  --out workspace/SEGMENTS.json --target 700 --min 400 --max 950
python3 scripts/segment.py --map workspace/SEGMENTS.json next
python3 scripts/segment.py --map workspace/SEGMENTS.json pack S001 --json
python3 scripts/segment.py --map workspace/SEGMENTS.json sync \
  --file workspace/working.md
python3 scripts/segment.py --map workspace/SEGMENTS.json status --json
```

Use `memory.py refresh`, `handoff`, `resume`, and literal `recall`. After
context compaction, resume from disk before making any claim. Never infer
whole-text completion from a sample or the current context window.

## Final reconciliation and closure

After the first all-service hard pass:

1. Compare original and working side by side across every source unit.
2. Repair any loss of meaning, facts, logic, modality, chronology, purpose,
   style handwriting, or English level.
3. Complete F2/F3/F4 if selected.
4. Run every mandatory detector again on the final full text.
5. Register the final passing `detector_round` after all optional-function
   artifacts.
6. Remove working annotations; complete constraints review and proofreading.
7. Register a report containing before/after scores for every service and
   target, highlight/edit rounds, fidelity checks, changes, and limitations.
8. Run `verify`, inspect every detail, then run `close`.

```bash
python3 scripts/state.py --state workspace/STATE.json verify
python3 scripts/state.py --state workspace/STATE.json close
```

Deliver immutable original, clean working text, and report. Do not call a
blocked or open F1 project complete. Do not claim permanent undetectability,
perfect authorship proof, or plagiarism-free status beyond the exact evidence.
