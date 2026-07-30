---
name: palimpsest
description: Professional RU/EN editorial rewriting with optional external or source-as-reference voice control, preserved English proficiency level, minimal semantic-safe edits, user-selected current detector evidence, fact-checking, source-overlap review, and lossless long-document memory. Use for humanizing or deslopifying drafts without fabricating scores, preserving or matching handwriting, restructuring prose, checking facts or attribution, and editing dissertations, manuscripts, reports, or essays across context resets.
---

# Palimpsest v3.2

Act as the responsible master editor, not a synonym spinner. Read, understand,
diagnose, edit with a stated reason, and reconcile the result against the
original. The desired text should feel authored because its thinking, emphasis,
rhythm, and local choices are coherent—not because noise or tricks were added.

## Non-negotiable rules

1. Keep the original immutable. Work on a copy, store its init SHA-256, and
   block verification if the source digest changes.
2. Read and understand the entire text before stylistic editing. For a long
   document, complete this systematically through the segment map; never claim
   whole-text understanding from a partial context window.
3. Q1 always selects a style baseline. An external reference supplies handwriting
   decisions only; otherwise the immutable source is its own style reference and
   must be changed as little as possible. Never import external facts, claims,
   citations, or distinctive phrases without separate authorization.
4. Preserve thesis, claims, polarity, causality, modality, chronology, numbers,
   units, equations, terms, citations, URLs, and protected fragments.
5. Never invent facts, sources, quotations, detector results, highlighted spans,
   access attempts, or plagiarism scores.
6. Detector scores are fallible review signals, not proof of authorship. Never
   promise permanent undetectability or a guaranteed score.
7. Do not use homoglyphs, invisible Unicode, deliberate typos, metadata tricks,
   citation laundering, or superficial synonym swaps to evade review.
8. F4 means original expression plus correct attribution. Do not conceal
   plagiarism or remove citations that are required.
9. Requirements stated by the user override house preferences. Genre obligations
   override aesthetic asymmetry.
10. A task closes only through current green evidence. There is no force-close
    or local quote-based yellow-close path.
11. Preserve the recorded English proficiency level. Do not upgrade learner
    English into a smoother academic register or simplify it downward; do not
    manufacture mistakes to imitate a level.

Read [references/doctrine.md](references/doctrine.md) and
[references/memory.md](references/memory.md) before changing text. Load the other
references only when their route is active:

| Route | Read |
|---|---|
| intake and task framing | [references/intake.md](references/intake.md) |
| handwriting reference | [references/ductus.md](references/ductus.md) |
| diagnosis and edit design | [references/patterns.md](references/patterns.md), [references/surgery.md](references/surgery.md) |
| inline working marks | [references/annotation.md](references/annotation.md) |
| F1 detector work | [references/detectors.md](references/detectors.md) |
| fidelity reconciliation | [references/fidelity.md](references/fidelity.md) |
| F3 fact-checking | [references/factcheck.md](references/factcheck.md) |
| F4 originality | [references/anti-plagiarism.md](references/anti-plagiarism.md) |
| skill regression work | [references/evals.md](references/evals.md) |

## Intake: four questions, one at a time

Do not ask for information already explicit in the current conversation or files.
Record an explicit or safely inferred answer before proceeding.

1. **Q1 — style baseline and English level.** Choose
   `external_reference` or `source_as_reference`. In the latter, the source text
   is the style reference and editing remains minimal. For English also record
   A1–C2/native or `infer_from_source`.
2. **Q2 — functions.** Select any combination:
   - `F1`: reduce AI-like signals with the smallest defensible edits;
   - `F2`: improve human structure while preserving the genre;
   - `F3`: verify factual claims against primary/official sources;
   - `F4`: resolve close paraphrase, quotation, citation, and attribution risk.
3. **Q3 — detectors.** Always ask which services to enable or disable. With F1,
   ZeroGPT remains mandatory; `zerogpt,copyleaks` is the recommended EN pair,
   not a silent choice. Without F1, record `none`.
4. **Q4 — requirements.** Audience, genre, language, required structure, length,
   citation style, forbidden wording, protected fragments, deadline, and any
   detector target or institutional constraint.

Create a working directory, copy the source, and initialize state:

```bash
python3 scripts/state.py --state workspace/STATE.json init \
  --original workspace/original.md --working workspace/working.md \
  --flags F1,F2 --ref path/to/reference.md

python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q1 --style-mode source_as_reference --english-level B2 \
  --answer "Use the source as its own style baseline; preserve B2." \
  --source explicit
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q2 --functions F1,F2 --answer "Enable F1 and F2." \
  --source explicit
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q3 --services zerogpt,copyleaks \
  --answer "Enable ZeroGPT and Copyleaks; disable optional services." \
  --source explicit
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q4 --answer "English essay; preserve headings and citations." \
  --source explicit
```

`init` automatically chooses `surgical` (≤600 words), `standard`, or `longform`
(≥4000 words). Initial flags/services are provisional until Q2/Q3 record the
explicit choice. Source language is detected from the immutable source.
`--language` may only assert the same result; it cannot reclassify Russian as
English to inherit the English detector policy.

## Evidence model

The deterministic scripts are screens and state controls; human review remains
mandatory where meaning or genre judgment is involved.

```bash
python3 scripts/state.py --state workspace/STATE.json template \
  --kind master_brief --out workspace/master-brief.json
python3 scripts/state.py --state workspace/STATE.json artifact \
  --kind master_brief --file workspace/master-brief.json
python3 scripts/state.py --state workspace/STATE.json verify
```

Templates are digest-bound. Fill every required check with specific evidence;
do not mechanically change `pending` to `pass`. Register these as applicable:

- always: `master_brief`, `diagnosis`, `semantic_review`, `style_review`,
  `constraints_review`, `proofread`, `report`;
- only in `external_reference`: `ductus`;
- F1: `capability_review` and current per-service detector evidence;
- F2: `structure_review`;
- F3: `claim_ledger`;
- F4: `overlap_report` and `plagiarism_review`.

Any edit makes working-bound attestations, the report, detector results, and
waivers stale. Re-run or re-register them for the current digest.

A locally writable file cannot prove that a sentence came from the user. An
`authorized_change` must therefore bind a structured external claim to one
immutable source-unit SHA and exact working-text offsets, and G7 remains yellow.
It never becomes green merely because a quote or message ID was typed into JSON.

## Phase A — understand before editing

Read the source fully. Write the master brief with:

- purpose, audience, genre, register, and main thesis;
- argument/scene sequence and dependency map;
- non-negotiable claims, terminology, figures, citations, and formatting;
- user requirements and conflicts between them;
- a paragraph/segment-level edit plan.

Then produce a diagnosis: location → observed problem → mechanism → consequence
→ least invasive repair. Separate genuine AI-like regularity from correct genre
discipline and from the author's deliberate habits. Do not edit during diagnosis.

Run baseline screens as relevant:

```bash
python3 scripts/pattern_scan.py workspace/working.md
python3 scripts/fidelity_check.py --original workspace/original.md \
  --edited workspace/working.md --json
python3 scripts/minimality.py --original workspace/original.md \
  --current workspace/working.md --json
python3 scripts/memory.py --workspace workspace terms \
  --original workspace/original.md
```

## Phase B — voice preservation or transfer

With external references, build Ductus from all of them. With
`source_as_reference`, analyze the immutable original by the same dimensions
but preserve its decisions instead of importing another voice. Analyze:

- how the author develops a thought, qualifies it, changes direction, and closes;
- sentence and paragraph rhythm, information density, transitions, and emphasis;
- lexicon, register, syntax, punctuation, and recurring local quirks;
- which traits are genre-compatible and which are accidental or unsafe.

Classify every candidate trait:

- `IMPORT`: transferable as a decision pattern;
- `ADAPT`: useful after genre/audience adjustment;
- `QUARANTINE`: factual, copied, dysfunctional, or too distinctive to transfer.

Test the profile on new material before applying it to the draft. Compare with
`style_metrics.py` and `style_distance.py`, but treat short-text metrics as noisy.
For English, run `english_level.py` and complete the manual proficiency check.
On reliable samples, source-as-reference distance above 28 or external-reference
regression fails the style metric policy. On short samples the metric is
explicitly advisory. The CEFR screen enforces a tight source-relative feature
envelope, but still cannot replace side-by-side judgment.

## Phase C — edit in bounded moves

Each move may cover one coherent cluster of nearby edits. Record its span,
hypothesis, and observed outcome; do not create bookkeeping theater for every
comma.

```bash
python3 scripts/state.py --state workspace/STATE.json move \
  --id M01 --span "P4-P5" \
  --hypothesis "Break repeated claim-example-summary cadence while retaining both claims."
```

Use this escalation ladder:

1. delete residue, duplication, or empty framing;
2. repair a phrase or sentence locally;
3. change rhythm or information order within a paragraph;
4. rebuild a paragraph only when its logic or genre function requires it;
5. change section structure only with explicit evidence and fidelity review.

After each coherent batch: run fidelity, minimality, terminology, and echo
screens; inspect their exact findings; revert any unsupported drift.

## F1 — current user-selected detector protocol

The recommended repeatable English core is:

1. **ZeroGPT** — mandatory by user preference;
2. **Copyleaks** — independent second signal, guest access, and education/LMS use.

Q3 may disable Copyleaks or add optional services; never change the selection
silently. ZeroGPT remains mandatory whenever F1 is active. Two independent
passing groups remain the default, so disabling the second service can leave G3
red. Lowering the minimum is always recorded as a yellow local override; local
user-quote fields cannot authenticate consent or produce a fully closed state.

This is deliberately a minimal independent set, not a list of brands. The
2026-07-30 English pilot found:

- Copyleaks: all 3 generated controls at 100%, all 3 public-domain human controls
  at 0%;
- ZeroGPT: all 3 generated controls above 20%, but one human control at 59.7%;
- Scribbr exposed QuillBot v7.1.0 and duplicated tested QuillBot scores;
- QuillBot missed the technical generated control at 19% and later required
  sign-up;
- Sapling flagged two of three human controls above 20%;
- GPTinf is an aggregator and failed to return one human result;
- GPTZero produced one guest result, then required sign-up.

These are pilot observations, not permanent rankings. Only English completed
this pilot; Russian remains provisional and yields a recorded limitation.
Before every project, create and fill a live `capability_review` from the
visible UI. Confirm access,
language, current limit, model/result format, and independence group. Do not
purchase, register, or log in merely to satisfy a default gate.

GPTZero and Turnitin are optional institutional evidence when the user already
has lawful access or supplies a report. Scribbr may replace QuillBot's UI but
does not count as another independent detector. Aggregators never count toward
the independent minimum.

Record evidence for the current document or exact segment. First issue a
one-use, two-hour challenge:

```bash
python3 scripts/state.py --state workspace/STATE.json detector-prepare \
  --service zerogpt --target DOCUMENT \
  --out workspace/evidence/zerogpt-challenge.json
python3 scripts/state.py --state workspace/STATE.json detector \
  --observation workspace/evidence/zerogpt-observation.json
```

The observation binds the challenge nonce, target digest, exact service URL,
visible score excerpt, timestamp, and SHA of a screenshot/PDF or raw vendor JSON.
This is an auditable capture, not cryptographic proof; a motivated local agent
can still fabricate pixels. Never describe it as proof of authorship.

Run a baseline, edit only diagnosed locations, then re-run the entire selected
core on the new digest. A low score never authorizes semantic damage. A service
failure is a scoped waiver for one service, target, and digest, requiring the
user's specific words as an audit claim; it is not a blanket pass or authenticated
consent. Reducing the independent minimum below two remains yellow even when a
quote is recorded.

Keep every fidelity-passing candidate with its detector vector and edit ratio.
Choose on the Pareto frontier: once a service is below the agreed threshold,
extra reduction there does not justify a much larger rewrite while another
service is unchanged. After three materially different, semantic-safe rounds
without improvement from a service, stop that target. Keep the least invasive
non-dominated candidate and register a formal bundle:

```bash
python3 scripts/state.py --state workspace/STATE.json plateau-template \
  --service copyleaks --target DOCUMENT \
  --out workspace/evidence/copyleaks-plateau.json
python3 scripts/state.py --state workspace/STATE.json plateau \
  --file workspace/evidence/copyleaks-plateau.json
```

Each candidate needs a passing fidelity report, full source-unit semantic
review with exact offsets, digest-bound edit moves, and a registered
challenge-bound detector observation. The validator re-runs minimality,
English-level drift, and the reliable style policy for each candidate. The
bundle needs at least two edit mechanisms; candidates with under 5% pairwise
difference or only small same-position substitutions are rejected. A valid
plateau is a yellow limitation only when another independent group passes; it
is never a fabricated green result.

## F2, F3, and F4

- **F2:** vary structure only where repeated symmetry, generic transitions,
  duplicate conclusions, or uniform paragraph cadence weaken the text. Preserve
  mandatory academic, legal, technical, or publication structure.
- **F3:** enumerate checkable claims. Prefer primary, official, and current
  sources; record source date, access date, exact support, contradictions, and
  resolution. If support is missing, qualify, remove, or ask—never invent.
- **F4:** distinguish shared ideas, exact quotation, acceptable paraphrase, and
  close paraphrase. Run the local source-corpus screen:

```bash
python3 scripts/source_overlap.py --draft workspace/working.md \
  --source sources/source-a.md --source sources/source-b.md \
  --out workspace/overlap.json
```

Resolve every high-risk run by quoting/citing, re-deriving the explanation from
the underlying idea, or removing unsupported dependence. An external
institutional plagiarism result is optional additional evidence, not something
the skill fabricates.

## Long documents and context resets

Map every character and keep detector evidence outside the map:

```bash
python3 scripts/segment.py map workspace/working.md \
  --out workspace/SEGMENTS.json
python3 scripts/segment.py --map workspace/SEGMENTS.json next
python3 scripts/segment.py --map workspace/SEGMENTS.json pack S001 --json
python3 scripts/segment.py --map workspace/SEGMENTS.json sync \
  --file workspace/working.md
python3 scripts/segment.py --map workspace/SEGMENTS.json status --json
```

`sync` detects edits, appended text, new segments, and orphaned old IDs.
Unchanged segment IDs persist; changed digests invalidate detector evidence in
state. Full coverage is the default. `risk_sampled` is allowed only with a
specific user acceptance quote and produces a limited, never fully green,
detector gate.

Use:

```bash
python3 scripts/memory.py --workspace workspace refresh
python3 scripts/memory.py --workspace workspace handoff --next "..."
python3 scripts/memory.py --workspace workspace resume
python3 scripts/memory.py --workspace workspace recall "literal phrase"
```

`recall` is literal by default; `--regex` is explicit. After context compaction,
resume from files before making any claim or edit.

## Final reconciliation and delivery

1. Re-read original and working text side by side.
2. Complete every immutable source unit in semantic review: thesis, claims, polarity,
   numbers/units, causality, modality, chronology, genre, and author intent.
3. Complete style review against the active baseline and verify the recorded
   English level.
4. Re-run selected detector services on the final digest.
5. Resolve all high-risk overlap, factual, annotation, terminology, and echo
   findings.
6. Register a report with sections `Changes`, `Checks`, and `Limitations`.
7. Run:

```bash
python3 scripts/state.py --state workspace/STATE.json verify
python3 scripts/state.py --state workspace/STATE.json close
```

If yellow gates remain, `close` sets `READY_WITH_LIMITS` and returns non-zero.
There is deliberately no local `--accept-limits`: a process that can edit the
workspace can also invent quotes, message references, and nonces. Ask for an
explicit user turn outside the local state; only a future host-signed consent
integration could machine-close that state. Any red gate blocks even this
limited handoff.

Deliver the clean working text, the immutable original, and the report. State
actual services, dates, targets, digests, scores, blocked access, sampling, and
known limitations. Do not say “perfect,” “undetectable,” or “plagiarism-free”
unless a defined evidence source genuinely supports that exact claim.
