# Academic integrity and assessed work

Palimpsest treats a dissertation, thesis, assessed essay, assignment, marking
brief, or comparable student submission as `academic_assessment`.

## Default hard boundary

For assessed academic work without explicit permission:

- F1 detector-score optimisation is disabled;
- do not rewrite to conceal AI authorship or obtain a lower detector score;
- do not present detector output as proof of authorship, plagiarism, or
  misconduct;
- do not upload unpublished student work to third-party services without
  permission and a privacy check;
- do not invent permission, user consent, supervisor approval, citations, or
  source access.

The permitted workflow is quality-first:

1. preserve the student's argument, register, English level, and document
   format;
2. check claims against primary or authoritative sources;
3. check citation/reference consistency and bounded source overlap;
4. identify unsupported, unclear, or structurally weak passages;
5. make only minimal proofreading corrections that the applicable institution
   permits;
6. provide feedback for the student to evaluate and adopt;
7. record AI use and disclosure obligations for the student to confirm with
   the assessment brief or supervisor.

If the supplied draft was substantially AI-generated, do not disguise that
fact with a “humanising” rewrite. Explain that the student must establish
authorship through their own source reading, reasoning, revisions, and any
required disclosure.

## Evidence language

Use precise labels:

- `citation coverage`: every in-text citation maps to the reference list;
- `metadata verified`: DOI/title/year/author metadata agrees with a registry or
  publisher;
- `bounded overlap check`: the draft was compared with an explicitly named
  local/open corpus;
- `institutional similarity report`: only when supplied by the institution or
  produced through authorised institutional access;
- `AI-detector score`: a noisy classifier output, never an authorship verdict.

Never call a bounded overlap check “Turnitin”, “full plagiarism clearance”, or
“80% originality”. Closed institutional databases cannot be reproduced by a
local script.

## State enforcement

`state.py init --content-context auto` detects strong academic-assessment
signals. When present, it:

- rejects F1 at initialisation;
- rejects later attempts to enable F1 through Q2;
- rejects a conflicting `--content-context general` assertion;
- defaults to a 10% document and 25% paragraph edit envelope;
- records `disclosure_review_required: true`.

Use F2, F3, and F4 for structure, fact/source, originality/attribution,
fidelity, style, and proofreading evidence.

## Explicit authorised academic revision

F1 may be enabled only through `academic_authorized_ai_revision` when all of
the following are present:

1. the user supplies an image or PDF authorisation artifact;
2. the recorded scope specifically covers AI-assisted rewriting and the
   requested detector-related work;
3. the artifact is structurally valid and its SHA-256 is bound into state;
4. disclosure review remains required;
5. meaning, evidence, citations, English level, genre and format remain hard
   gates.

```bash
python3 scripts/state.py --state workspace/STATE.json init \
  --original workspace/original.txt --working workspace/working.txt \
  --flags F1,F2,F3,F4 \
  --content-context academic_authorized_ai_revision \
  --authorization-evidence workspace/permission.pdf \
  --authorization-scope \
  "Permission covers AI-assisted paraphrasing, stylistic revision, detector checks, and reduction of false-positive text-origin scores."
```

This mode records `trust: user_supplied_unverified_external_document`,
`independently_authenticated: false`, the evidence path, SHA-256 and structural
validation result. The validator proves that the same structurally valid file
is still present. It does not authenticate a signature, confirm the issuer,
OCR the legal meaning, or prove that the user did not create the artifact.
Never describe it as institution-verified permission unless a separate trusted
channel established that fact.

Authorisation never permits fabricated sources, plagiarism, removed
attribution, invisible characters, homoglyphs, deliberate language errors, or
semantic drift. Fixed bibliography metadata is not rewritten to influence a
classifier. Results remain noisy current service measurements, not proof of
authorship.
