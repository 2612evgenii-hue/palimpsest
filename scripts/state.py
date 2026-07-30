#!/usr/bin/env python3
"""Palimpsest v3.5 project state and fail-closed evidence gates.

There is no command that manually paints a gate green.  Gates are recomputed
from current file digests, structured reconciliations, challenge-bound detector
observations, and deterministic checks.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import secrets
import struct
import subprocess
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402
import _v3lib as V  # noqa: E402

VERSION = "3.5.0"
STATE_SCHEMA = "palimpsest.state.v3.5"
ATTEST_SCHEMA = "palimpsest.attestation.v3.5"
CAPABILITY_SCHEMA = "palimpsest.capability-review.v3.5"
OVERLAP_SCHEMA = "palimpsest.overlap.v3"
DETECTOR_CHALLENGE_SCHEMA = "palimpsest.detector-challenge.v1"
DETECTOR_OBSERVATION_SCHEMA = "palimpsest.detector-observation.v1"
DETECTOR_ROUND_SCHEMA = "palimpsest.detector-round.v1"
PLATEAU_SCHEMA = "palimpsest.detector-plateau.v2"
HARD_DETECTOR_MAX_EXCLUSIVE = 20.0
SOFT_DETECTOR_TARGET_EXCLUSIVE = 15.0
PLATEAU_MECHANISMS = {
    "lexical_cleanup",
    "rhythm_restructure",
    "syntax_restructure",
    "paragraph_restructure",
    "voice_rebalance",
    "redundancy_cut",
    "transition_repair",
}
DEFAULT_STATE = Path("workspace/STATE.json")
SCRIPTS = Path(__file__).resolve().parent
REGISTRY_PATH = SCRIPTS.parent / "assets" / "service-registry.json"

ATTESTATIONS: dict[str, dict] = {
    "master_brief": {
        "bind": "original",
        "checks": [
            "whole_text_read", "thesis_and_logic", "genre_and_audience",
            "nonnegotiables", "edit_plan",
        ],
    },
    "diagnosis": {
        "bind": "original",
        "checks": [
            "ai_pattern_map", "structure_map", "style_map",
            "rule_conflicts", "priority_map",
        ],
    },
    "ductus": {
        "bind": "references",
        "checks": [
            "reference_only_not_facts", "thought_habits", "rhythm",
            "lexicon", "transfer_matrix", "quarantine", "rehearsal",
        ],
    },
    "structure_review": {
        "bind": "working",
        "checks": ["genre_fit", "logic", "nonmechanical_structure", "navigation"],
    },
    "claim_ledger": {
        "bind": "working",
        "checks": [
            "claims_enumerated", "primary_sources", "source_dates",
            "contradictions", "resolutions", "citations",
        ],
    },
    "plagiarism_review": {
        "bind": "working",
        "checks": [
            "source_corpus", "quotes_and_citations", "close_paraphrase",
            "idea_attribution", "external_service_boundary",
        ],
    },
    "semantic_review": {
        "bind": "working",
        "checks": [
            "thesis", "claims", "polarity_and_negation", "numbers_and_units",
            "causality", "modality", "chronology", "genre", "author_intent",
        ],
        "locations_required": True,
    },
    "style_review": {
        "bind": "working",
        "checks": [
            "baseline_mode", "preserved_decisions", "authorized_adaptations",
            "quarantined_traits", "genre_fit", "voice_drift",
            "english_level_preserved", "minimality",
        ],
    },
    "constraints_review": {
        "bind": "working",
        "checks": [
            "mandatory_rules", "forbidden_patterns", "format",
            "terminology", "protected_fragments",
        ],
    },
    "proofread": {
        "bind": "working",
        "checks": [
            "grammar", "punctuation", "typography", "consistency", "read_aloud",
        ],
    },
}

GATE_DESCRIPTIONS = {
    "G0": "intake and master understanding",
    "G1": "diagnostic map",
    "G2": "active style baseline",
    "G3": "current detector evidence",
    "G4": "genre-safe structural edit",
    "G5": "claim verification",
    "G6": "source originality and attribution",
    "G7": "fidelity, semantic review, and edit budget",
    "G8": "style transfer review",
    "G9": "constraints, proofreading, and clean delivery text",
    "G10": "final report",
}


class StateError(RuntimeError):
    pass


def fail(message: str, code: int = 2) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return code


def state_path(raw: Path) -> Path:
    return raw.expanduser().resolve()


def load_state(path: Path) -> dict:
    try:
        st = V.load_json(path)
    except FileNotFoundError as exc:
        raise StateError(f"state does not exist: {path}") from exc
    if st.get("schema") != STATE_SCHEMA:
        raise StateError(
            f"unsupported state schema {st.get('schema')!r}; expected {STATE_SCHEMA}"
        )
    return st


def working_sha(st: dict) -> str:
    return V.sha256_file(st["files"]["working"])


def original_sha(st: dict) -> str:
    return V.sha256_file(st["files"]["original"])


def references_sha(st: dict) -> str:
    refs = st["files"].get("references", [])
    return V.digest_files(refs) if refs else ""


def subject_sha(st: dict, binding: str) -> str:
    if binding == "working":
        return working_sha(st)
    if binding == "original":
        return original_sha(st)
    if binding == "references":
        return references_sha(st)
    if binding == "none":
        return ""
    raise StateError(f"unknown binding: {binding}")


def word_count(path: str | Path) -> int:
    return len(T.words(V.read_text(path)))


def semantic_source_units(st: dict) -> list[dict]:
    """Create a bounded, deterministic source-unit inventory for reconciliation."""
    text = V.read_text(st["files"]["original"])
    if st["route"] == "surgical":
        bodies = T.sentences(text)
        prefix = "S"
    else:
        bodies = [
            paragraph.text.strip()
            for paragraph in T.paragraphs(text)
            if paragraph.text.strip()
        ]
        prefix = "P"
    return [
        {
            "id": f"{prefix}{index:04d}",
            "original_sha256": V.sha256_text(body),
            "original_excerpt": body[:240],
        }
        for index, body in enumerate(bodies, start=1)
    ]


def lexical_overlap(left: str, right: str) -> float:
    a = set(T.words(left))
    b = set(T.words(right))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def registry() -> dict:
    return V.load_json(REGISTRY_PATH)


def infer_language(text: str) -> str:
    return "ru" if T.lang_of(text) == "ru" else "en"


def language_profile(text: str) -> dict:
    letters = [char for char in text if char.isalpha()]
    cyrillic = sum(1 for char in letters if T.CYR.match(char))
    latin = sum(1 for char in letters if "a" <= char.casefold() <= "z")
    return {
        "detected": infer_language(text),
        "letters": len(letters),
        "cyrillic_letters": cyrillic,
        "latin_letters": latin,
        "cyrillic_share": round(cyrillic / len(letters), 4) if letters else 0.0,
        "latin_share": round(latin / len(letters), 4) if letters else 0.0,
        "method": "deterministic_script_profile",
    }


def add_event(st: dict, event: str, **data) -> None:
    st.setdefault("events", []).append({"at": V.now(), "event": event, **data})
    st["updated_at"] = V.now()


def refresh_goal(st: dict) -> None:
    """Keep the user-facing success contract explicit in durable state."""
    selected = st.get("detector_policy", {}).get("selected_services", [])
    score_mandatory = bool(
        st.get("flags", {}).get("F1")
        and st.get("detector_policy", {}).get("score_mandatory", True)
    )
    st["goal"] = {
        "functions": [name for name, enabled in st.get("flags", {}).items() if enabled],
        "style_mode": st.get("style_mode", "unselected"),
        "english_level": st.get("english_level", {}).get("target", "not_applicable"),
        "requirements": st.get("intake", {}).get("Q4_requirements", {}).get("answer", ""),
        "score_mandatory": score_mandatory,
        "mandatory_detectors": list(selected) if score_mandatory else [],
        "hard_pass": (
            f"every mandatory detector score strictly < "
            f"{HARD_DETECTOR_MAX_EXCLUSIVE:g}% "
            "on every current full-coverage target"
            if score_mandatory
            else "not applicable"
        ),
        "soft_target": (
            f"every mandatory detector score < {SOFT_DETECTOR_TARGET_EXCLUSIVE:g}%"
            if score_mandatory
            else "not applicable"
        ),
        "closure_rule": (
            "OPEN while any mandatory detector is missing, blocked, stale, "
            f"or >= {HARD_DETECTOR_MAX_EXCLUSIVE:g}%"
            if score_mandatory
            else "close only when all selected function gates are green"
        ),
    }


def gate(color: str, evidence: str, details: list[str] | None = None) -> dict:
    return {
        "color": color,
        "description": "",
        "evidence": evidence,
        "details": details or [],
    }


def cmd_init(args: argparse.Namespace) -> int:
    target = state_path(args.state)
    if target.exists():
        return fail(f"state already exists: {target}")
    try:
        original = V.resolve_existing(args.original)
        working = V.resolve_existing(args.working)
        refs = [str(V.resolve_existing(p)) for p in (args.ref or [])]
    except FileNotFoundError as exc:
        return fail(f"input file does not exist: {exc}")

    flags = {f"F{i}": False for i in range(1, 5)}
    for item in V.parse_csv(args.flags):
        if item.casefold() == "none":
            continue
        name = item.upper()
        if name not in flags:
            return fail(f"unknown function {item}; expected F1..F4")
        flags[name] = True
    source_words = word_count(original)
    route = args.route
    if route == "auto":
        # In score-mandatory mode, switch to stable chunks before the smallest
        # default public word limit (1,200 words) can be exceeded.
        longform_cutoff = 1000 if flags["F1"] else 4000
        route = (
            "longform"
            if source_words >= longform_cutoff
            else ("surgical" if source_words <= 600 else "standard")
        )
    default_budget = (
        0.30
        if flags["F1"]
        else (0.12 if route == "surgical" else 0.18)
    )
    budget = args.budget if args.budget is not None else default_budget
    para_budget = (
        args.para_budget
        if args.para_budget is not None
        else (0.60 if flags["F1"] else (0.35 if route == "surgical" else 0.45))
    )
    original_text = V.read_text(original)
    source_language = language_profile(original_text)
    detected_language = source_language["detected"]
    if args.language and args.language != detected_language:
        return fail(
            f"--language {args.language} conflicts with source detection "
            f"{detected_language}; detector validation always follows source text"
        )
    language = detected_language
    reg = registry()
    if args.services:
        services = [x.lower() for x in V.parse_csv(args.services)]
    elif flags["F1"]:
        key = "default_english_guest_services" if language == "en" else "default_russian_guest_services"
        services = list(reg["policy"][key])
    else:
        services = []
    if flags["F1"] and "zerogpt" not in services:
        return fail("ZeroGPT is a mandatory selected service for this skill")
    unknown = [x for x in services if x not in reg["services"]]
    if unknown:
        return fail(f"unknown services: {', '.join(unknown)}")
    if flags["F1"] and args.coverage != "full":
        return fail("score_mandatory F1 requires full detector coverage; risk_sampled is forbidden")
    if not 0 <= args.detector_max <= HARD_DETECTOR_MAX_EXCLUSIVE:
        return fail(
            f"score_mandatory hard threshold must be between 0 and "
            f"{HARD_DETECTOR_MAX_EXCLUSIVE:g}%"
        )
    registry_minimum = int(reg["policy"]["minimum_independent_services"])
    if (
        flags["F1"]
        and args.min_independent < registry_minimum
        and len((args.user_quote or "").strip()) < 25
    ):
        return fail(
            f"minimum_independent below {registry_minimum} requires a specific "
            "25+ character user quote"
        )

    st = {
        "schema": STATE_SCHEMA,
        "version": VERSION,
        "task": args.task or original.stem,
        "status": "OPEN",
        "created_at": V.now(),
        "updated_at": V.now(),
        "closed_at": "",
        "close_digest": "",
        "route": route,
        "language": language,
        "source_language": source_language,
        "style_mode": "unselected",
        "english_level": {
            "requested": "unselected" if language == "en" else "not_applicable",
            "target": "unselected" if language == "en" else "not_applicable",
            "source_estimate": "",
            "source_profile": {},
            "policy": (
                "preserve_target_and_source_complexity_without_inventing_errors"
                if language == "en"
                else "not_applicable"
            ),
        },
        "source_words": source_words,
        "files": {
            "original": str(original),
            "original_sha256_at_init": V.sha256_file(original),
            "working": str(working),
            "references": refs,
            "segments": str((target.parent / "SEGMENTS.json").resolve()),
        },
        "flags": flags,
        "intake": {
            "Q1_style_references": {"answer": "", "source": ""},
            "Q2_functions": {"answer": "", "source": ""},
            "Q3_detectors": {"answer": "", "source": ""},
            "Q4_requirements": {"answer": "", "source": ""},
        },
        "budgets": {
            "document_change_ratio": budget,
            "paragraph_change_ratio": para_budget,
        },
        "detector_policy": {
            "selected_services": services,
            "score_mandatory": bool(flags["F1"]),
            "threshold_pct": min(args.detector_max, HARD_DETECTOR_MAX_EXCLUSIVE),
            "threshold_comparison": "strictly_less_than",
            "soft_target_pct": min(
                SOFT_DETECTOR_TARGET_EXCLUSIVE,
                args.detector_max,
            ),
            "minimum_independent": args.min_independent,
            "coverage": args.coverage,
            "sample_ids": V.parse_csv(args.sample_ids),
            "coverage_acceptance_quote": args.user_quote or "",
            "zero_gpt_required": True,
            "language_validation": (
                "pilot_selected"
                if language in reg["policy"].get("pilot_validated_languages", ["en"])
                else "provisional"
            ),
        },
        "artifacts": {},
        "detector_challenges": [],
        "detector_results": [],
        "detector_rounds": [],
        "plateaus": [],
        "waivers": [],
        "moves": [],
        "parked": [],
        "verification": {
            "ran_at": "",
            "working_sha256": "",
            "gates": {},
            "machine_checks": {},
        },
        "events": [{"at": V.now(), "event": "init"}],
    }
    refresh_goal(st)
    V.atomic_write_json(target, st)
    print(f"Palimpsest v{VERSION} state: {target}")
    print(f"route={route} language={language} words={source_words}")
    print(f"functions={','.join(k for k, v in flags.items() if v) or 'none'}")
    if services:
        print(f"detectors={','.join(services)} (live capability review still required)")
    print(
        "Next: answer Q1 style baseline, Q2 functions, Q3 detector selection, "
        "and Q4 requirements with `state.py intake`."
    )
    return 0


def cmd_intake(args: argparse.Namespace) -> int:
    key_map = {
        "Q1": "Q1_style_references",
        "Q2": "Q2_functions",
        "Q3": "Q3_detectors",
        "Q4": "Q4_requirements",
    }
    answer = args.answer.strip()
    if not answer:
        return fail("intake answer cannot be empty")
    path = state_path(args.state)
    try:
        with V.locked_json(path) as st:
            if st.get("schema") != STATE_SCHEMA:
                raise StateError("not a Palimpsest v3 state")
            expected_order = ["Q1", "Q2", "Q3", "Q4"]
            current_index = expected_order.index(args.question)
            missing_before = [
                question
                for question in expected_order[:current_index]
                if not st["intake"][key_map[question]].get("answer")
            ]
            if missing_before:
                raise StateError(
                    f"answer intake in order; complete {', '.join(missing_before)} first"
                )

            if args.question == "Q1":
                if not args.style_mode:
                    raise StateError(
                        "Q1 requires --style-mode external_reference or source_as_reference"
                    )
                if st["language"] == "en" and not args.english_level:
                    raise StateError(
                        "Q1 for English requires --english-level "
                        "infer_from_source, A1..C2, or native"
                    )
                if st["language"] != "en" and args.english_level not in {
                    None, "not_applicable"
                }:
                    raise StateError("--english-level applies only to English projects")
                if args.ref:
                    st["files"]["references"] = [
                        str(V.resolve_existing(item)) for item in args.ref
                    ]
                if args.style_mode == "external_reference" and not st["files"]["references"]:
                    raise StateError(
                        "external_reference requires at least one existing --ref file"
                    )
                st["style_mode"] = args.style_mode
                if st["language"] == "en":
                    level_payload, level_rc, level_err = run_json(
                        [
                            sys.executable,
                            str(SCRIPTS / "english_level.py"),
                            "--text",
                            st["files"]["original"],
                            "--json",
                        ]
                    )
                    if level_rc != 0 or not level_payload:
                        raise StateError(
                            "could not profile source English level: "
                            + (level_err or "unknown screen failure")
                        )
                    requested = args.english_level
                    target = (
                        level_payload["estimated_cefr"]
                        if requested == "infer_from_source"
                        else requested.upper()
                    )
                    st["english_level"] = {
                        "requested": requested,
                        "target": target,
                        "source_estimate": level_payload["estimated_cefr"],
                        "source_profile": level_payload,
                        "policy": (
                            "preserve_target_and_source_complexity_without_inventing_errors"
                        ),
                    }

            if args.question == "Q2":
                if args.functions is None:
                    raise StateError("Q2 requires --functions with F1..F4 or none")
                requested = V.parse_csv(args.functions)
                if len(requested) == 1 and requested[0].casefold() == "none":
                    requested = []
                normalized: list[str] = []
                for item in requested:
                    name = item.upper()
                    if name not in st["flags"]:
                        raise StateError(f"unknown function {item}; expected F1..F4 or none")
                    if name not in normalized:
                        normalized.append(name)
                old_f1 = st["flags"]["F1"]
                st["flags"] = {name: name in normalized for name in st["flags"]}
                if old_f1 != st["flags"]["F1"]:
                    st["artifacts"].pop("capability_review", None)
                    st["detector_challenges"] = []
                    st["detector_results"] = []
                    st["plateaus"] = []
                    st["waivers"] = []
                    st["detector_rounds"] = []
                    st["artifacts"].pop("detector_round", None)
                if not st["flags"]["F1"]:
                    st["detector_policy"]["selected_services"] = []
                    st["detector_policy"]["score_mandatory"] = False
                else:
                    st["detector_policy"]["score_mandatory"] = True
                    st["detector_policy"]["coverage"] = "full"
                    st["detector_policy"]["threshold_pct"] = min(
                        float(st["detector_policy"].get("threshold_pct", 20.0)),
                        HARD_DETECTOR_MAX_EXCLUSIVE,
                    )

            if args.question == "Q3":
                if args.services is None:
                    raise StateError(
                        "Q3 requires --services with the enabled detector IDs or none"
                    )
                selected = [item.lower() for item in V.parse_csv(args.services)]
                if len(selected) == 1 and selected[0] == "none":
                    selected = []
                selected = list(dict.fromkeys(selected))
                unknown = [
                    item for item in selected if item not in registry()["services"]
                ]
                if unknown:
                    raise StateError(f"unknown services: {', '.join(unknown)}")
                if st["flags"]["F1"] and "zerogpt" not in selected:
                    raise StateError(
                        "ZeroGPT is mandatory when F1 detector testing is enabled"
                    )
                if st["flags"]["F1"] and not selected:
                    raise StateError("F1 requires at least one selected detector")
                if not st["flags"]["F1"] and selected:
                    raise StateError(
                        "detectors cannot be selected while F1 is disabled; use --services none"
                    )
                if selected != st["detector_policy"]["selected_services"]:
                    st["artifacts"].pop("capability_review", None)
                    st["detector_challenges"] = []
                    st["detector_results"] = []
                    st["plateaus"] = []
                    st["waivers"] = []
                    st["detector_rounds"] = []
                    st["artifacts"].pop("detector_round", None)
                st["detector_policy"]["selected_services"] = selected

            st["intake"][key_map[args.question]] = {
                "answer": answer,
                "source": args.source,
                "recorded_at": V.now(),
            }
            refresh_goal(st)
            add_event(st, "intake", question=args.question, source=args.source)
    except (FileNotFoundError, StateError) as exc:
        return fail(str(exc))
    print(f"{args.question} recorded ({args.source})")
    return 0


def detector_round_snapshot(st: dict) -> tuple[list[dict], list[str]]:
    """Return the exact current service/target observation matrix."""
    targets, problems = detector_targets(st)
    rows: list[dict] = []
    for target, digest in targets:
        for service in st["detector_policy"]["selected_services"]:
            result = latest_current_result(st, service, target, digest)
            if not result:
                rows.append(
                    {
                        "service": service,
                        "target": target,
                        "content_sha256": digest,
                        "score_pct": None,
                        "observation_sha256": "",
                    }
                )
                continue
            rows.append(
                {
                    "service": service,
                    "target": target,
                    "content_sha256": digest,
                    "score_pct": float(result["score_pct"]),
                    "observation_sha256": result["observation_sha256"],
                }
            )
    return rows, problems


def current_target_text(st: dict, target: str) -> str:
    text = V.read_text(st["files"]["working"])
    if target == "DOCUMENT":
        return text
    segment_path = Path(st["files"]["segments"])
    data = V.load_json(segment_path)
    row = next(
        (item for item in data.get("segments", []) if item.get("id") == target),
        None,
    )
    if not row:
        raise StateError(f"unknown segment target {target}")
    return text[int(row["start"]):int(row["end"])]


def template_payload(st: dict, kind: str) -> dict | str:
    if kind == "capability_review":
        reg = registry()
        selected = st["detector_policy"]["selected_services"]
        services = {}
        for service_id in selected:
            base = reg["services"][service_id]
            services[service_id] = {
                "registry_facts": {
                    "display_name": base["display_name"],
                    "url": base["url"],
                    "kind": base["kind"],
                    "independence_group": base["independence_group"],
                    "guest_access": base.get("guest_access", False),
                    "access_class": base.get("access_class", "unknown"),
                    "languages": base.get("languages", []),
                    "public_limit": base.get("public_limit"),
                    "result": base.get("result", []),
                },
                "observation": {
                    "status": "pending",
                    "checked_at": "",
                    "access_observed": "",
                    "language_tested": False,
                    "result_returned": False,
                    "evidence": "",
                    "access_authorization_quote": "",
                },
            }
        return {
            "schema": CAPABILITY_SCHEMA,
            "language": st["language"],
            "selected_services": selected,
            "services": services,
            "notes": [
                "Edit observation only. registry_facts are immutable and validated byte-for-byte.",
                "Confirm access, a real language test, and an actual returned result in the live UI.",
            ],
        }
    if kind == "detector_round":
        rows, target_problems = detector_round_snapshot(st)
        threshold = float(st["detector_policy"]["threshold_pct"])
        failing = [
            row for row in rows
            if row["score_pct"] is None or float(row["score_pct"]) >= threshold
        ]
        return {
            "schema": DETECTOR_ROUND_SCHEMA,
            "round_id": f"R{len(st.get('detector_rounds', [])) + 1:03d}",
            "working_sha256": working_sha(st),
            "required_services": list(st["detector_policy"]["selected_services"]),
            "coverage": st["detector_policy"]["coverage"],
            "hard_max_exclusive_pct": threshold,
            "soft_target_exclusive_pct": float(
                st["detector_policy"]["soft_target_pct"]
            ),
            "round_status": "requires_edit" if failing else "pass",
            "service_results": rows,
            "coverage_declarations": [
                {
                    "service": row["service"],
                    "target": row["target"],
                    "state": "pending",
                    "evidence": "",
                }
                for row in rows
            ],
            "highlight_map": [],
            "editor_analysis": "",
            "next_action": "",
            "target_problems": target_problems,
            "instructions": [
                "Do not change service_results, digests, thresholds, or required_services.",
                "For every service/target, map all visible highlights or state that the UI exposed none.",
                "Every failing service/target needs at least one visible-highlight or manual-diagnostic zone.",
                "Use round_status=requires_edit when any score is at or above the hard threshold; use pass only when every score is below it.",
            ],
        }
    if kind == "report":
        selected = ", ".join(st["detector_policy"]["selected_services"]) or "none"
        return (
            f"# {st['task']}: итоговый отчёт\n\n"
            "## Изменения\n\n"
            "[Заполнить: диагноз → минимальные moves → сохранённые invariants.]\n\n"
            "## Проверки\n\n"
            f"Mandatory detectors: {selected}. Hard pass: каждый score <20%; "
            "target: каждый score <15%.\n\n"
            "[Добавить before/after service×target table, detector rounds, "
            "fidelity, style, English level и F2/F3/F4 evidence.]\n\n"
            "## Ограничения\n\n"
            "[Указать target misses 15–<20, blocked/open blockers, provisional "
            "corpus и trust boundary; высокий score не называть успехом.]\n"
        )
    spec = ATTESTATIONS[kind]
    payload = {
        "schema": ATTEST_SCHEMA,
        "kind": kind,
        "status": "pending",
        "subject_sha256": subject_sha(st, spec["bind"]),
        "binding": spec["bind"],
        "reviewer": "master",
        "reviewed_at": "",
        "checks": [
            {"id": check, "status": "pending", "evidence": "", "locations": []}
            for check in spec["checks"]
        ],
        "limitations": [],
    }
    if kind == "semantic_review":
        payload["source_units"] = [
            {
                **unit,
                "verdict": "pending",
                "edited_evidence": [],
                "rationale": "",
                "authorization": None,
            }
            for unit in semantic_source_units(st)
        ]
    if kind == "style_review":
        payload["style_mode"] = st.get("style_mode", "unselected")
        payload["style_reference_sha256"] = (
            original_sha(st)
            if st.get("style_mode") == "source_as_reference"
            else references_sha(st)
        )
        payload["english_level_target"] = st.get("english_level", {}).get(
            "target", "not_applicable"
        )
        payload["english_source_estimate"] = st.get("english_level", {}).get(
            "source_estimate", ""
        )
    return payload


def validate_detector_round(st: dict, path: Path) -> tuple[bool, list[str]]:
    problems: list[str] = []
    try:
        data = V.load_json(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return False, [f"invalid JSON: {exc}"]
    if data.get("schema") != DETECTOR_ROUND_SCHEMA:
        problems.append(f"schema must be {DETECTOR_ROUND_SCHEMA}")
    if data.get("working_sha256") != working_sha(st):
        problems.append("detector round is stale for the current working text")
    selected = st["detector_policy"]["selected_services"]
    if data.get("required_services") != selected:
        problems.append("required_services differ from the explicit Q3 detector scope")
    if data.get("coverage") != "full":
        problems.append("score_mandatory detector rounds require full coverage")
    hard = float(st["detector_policy"]["threshold_pct"])
    soft = float(st["detector_policy"]["soft_target_pct"])
    if data.get("hard_max_exclusive_pct") != hard:
        problems.append("hard threshold differs from state policy")
    if data.get("soft_target_exclusive_pct") != soft:
        problems.append("soft target differs from state policy")
    expected_rows, target_problems = detector_round_snapshot(st)
    problems.extend(target_problems)
    observed_rows = data.get("service_results")
    if observed_rows != expected_rows:
        problems.append(
            "service_results must exactly match every current challenge-bound result"
        )
    complete_rows = [
        row for row in expected_rows
        if row.get("score_pct") is not None and row.get("observation_sha256")
    ]
    if len(complete_rows) != len(expected_rows):
        problems.append("detector round is incomplete; every service/target needs a result")
    for row in complete_rows:
        result = latest_current_result(
            st,
            row["service"],
            row["target"],
            row["content_sha256"],
        )
        if not result:
            problems.append(f"{row['service']}/{row['target']}: current result disappeared")
            continue
        integrity_ok, integrity_message = detector_result_integrity(result)
        if not integrity_ok:
            problems.append(
                f"{row['service']}/{row['target']}: {integrity_message}"
            )

    expected_pairs = {
        (row["service"], row["target"]) for row in expected_rows
    }
    declarations = data.get("coverage_declarations", [])
    declaration_pairs: set[tuple[str, str]] = set()
    allowed_states = {
        "all_visible_highlights_mapped",
        "no_highlights_visible",
        "no_highlight_surface",
    }
    for item in declarations if isinstance(declarations, list) else []:
        if not isinstance(item, dict):
            problems.append("coverage_declaration rows must be objects")
            continue
        pair = (str(item.get("service", "")), str(item.get("target", "")))
        if pair in declaration_pairs:
            problems.append(f"duplicate coverage declaration for {pair[0]}/{pair[1]}")
        declaration_pairs.add(pair)
        if item.get("state") not in allowed_states:
            problems.append(
                f"{pair[0]}/{pair[1]}: coverage state must describe visible highlight coverage"
            )
        if len(str(item.get("evidence", "")).strip()) < 20:
            problems.append(
                f"{pair[0]}/{pair[1]}: coverage evidence must contain 20+ characters"
            )
    if declaration_pairs != expected_pairs:
        problems.append("coverage declarations must cover every required service/target once")

    highlights = data.get("highlight_map", [])
    highlight_ids: set[str] = set()
    highlight_pairs: set[tuple[str, str]] = set()
    if not isinstance(highlights, list):
        problems.append("highlight_map must be a list")
        highlights = []
    for item in highlights:
        if not isinstance(item, dict):
            problems.append("highlight rows must be objects")
            continue
        mark_id = str(item.get("id", "")).strip()
        if not mark_id or mark_id in highlight_ids:
            problems.append("every highlight needs a unique non-empty id")
        highlight_ids.add(mark_id)
        pair = (str(item.get("service", "")), str(item.get("target", "")))
        if pair not in expected_pairs:
            problems.append(f"{mark_id}: highlight service/target is outside this round")
        highlight_pairs.add(pair)
        if item.get("origin") not in {"visible_highlight", "manual_diagnosis"}:
            problems.append(f"{mark_id}: origin must be visible_highlight or manual_diagnosis")
        if len(str(item.get("location", "")).strip()) < 2:
            problems.append(f"{mark_id}: precise location is required")
        if len(str(item.get("excerpt", "")).strip()) < 8:
            problems.append(f"{mark_id}: excerpt must contain 8+ characters")
        else:
            try:
                target_text = current_target_text(st, pair[1])
            except (OSError, KeyError, ValueError, StateError) as exc:
                problems.append(f"{mark_id}: cannot resolve target text: {exc}")
            else:
                if str(item.get("excerpt", "")).strip() not in target_text:
                    problems.append(
                        f"{mark_id}: excerpt is not verbatim text from the current target"
                    )
        if len(str(item.get("reason", "")).strip()) < 20:
            problems.append(f"{mark_id}: reason must contain 20+ characters")
        if item.get("status") not in {"open", "resolved", "false_positive"}:
            problems.append(f"{mark_id}: invalid highlight status")

    failing_pairs = {
        (row["service"], row["target"])
        for row in complete_rows
        if float(row["score_pct"]) >= hard
    }
    missing_diagnosis = failing_pairs - highlight_pairs
    for service, target in sorted(missing_diagnosis):
        problems.append(
            f"{service}/{target}: failing result needs at least one mapped or manual diagnostic zone"
        )
    expected_status = "requires_edit" if failing_pairs else "pass"
    if data.get("round_status") != expected_status:
        problems.append(
            f"round_status must be {expected_status} for the current strict threshold"
        )
    if expected_status == "pass" and any(
        item.get("status") == "open" for item in highlights if isinstance(item, dict)
    ):
        problems.append("passing final round cannot contain open highlight zones")
    if len(str(data.get("editor_analysis", "")).strip()) < 40:
        problems.append("editor_analysis must contain 40+ characters")
    if len(str(data.get("next_action", "")).strip()) < 20:
        problems.append("next_action must contain 20+ characters")
    return not problems, problems


def cmd_template(args: argparse.Namespace) -> int:
    try:
        st = load_state(state_path(args.state))
        payload = template_payload(st, args.kind)
        out = Path(args.out).expanduser().resolve()
        if isinstance(payload, str):
            V.atomic_write_text(out, payload)
        else:
            V.atomic_write_json(out, payload)
    except (StateError, FileNotFoundError, KeyError) as exc:
        return fail(str(exc))
    print(f"template created: {out}")
    return 0


def validate_attestation(st: dict, kind: str, path: Path) -> tuple[bool, list[str], str]:
    problems: list[str] = []
    try:
        data = V.load_json(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return False, [f"invalid JSON: {exc}"], ""
    spec = ATTESTATIONS[kind]
    expected_subject = subject_sha(st, spec["bind"])
    if data.get("schema") != ATTEST_SCHEMA:
        problems.append(f"schema must be {ATTEST_SCHEMA}")
    if data.get("kind") != kind:
        problems.append(f"kind must be {kind}")
    if data.get("binding") != spec["bind"]:
        problems.append(f"binding must be {spec['bind']}")
    if data.get("subject_sha256") != expected_subject:
        problems.append("subject_sha256 does not match the current bound text")
    if data.get("status") != "pass":
        problems.append("top-level status must be pass")
    if not str(data.get("reviewed_at", "")).strip():
        problems.append("reviewed_at is required")
    checks = {item.get("id"): item for item in data.get("checks", []) if isinstance(item, dict)}
    for check_id in spec["checks"]:
        item = checks.get(check_id)
        if not item:
            problems.append(f"missing check {check_id}")
            continue
        if item.get("status") != "pass":
            problems.append(f"{check_id}: status must be pass")
        if len(str(item.get("evidence", "")).strip()) < 20:
            problems.append(f"{check_id}: evidence must contain 20+ characters")
        if spec.get("locations_required") and not item.get("locations"):
            problems.append(f"{check_id}: at least one paragraph/segment location is required")
    if kind == "semantic_review":
        expected_units = semantic_source_units(st)
        rows = data.get("source_units", [])
        if not isinstance(rows, list):
            problems.append("semantic_review source_units must be a list")
            rows = []
        if len(rows) != len(expected_units):
            problems.append(
                f"semantic_review must reconcile every source unit "
                f"({len(rows)} present; {len(expected_units)} required)"
            )
        working_text = V.read_text(st["files"]["working"])
        mapped_spans: list[tuple[str, int, int]] = []
        for expected, row in zip(expected_units, rows):
            unit_id = expected["id"]
            if not isinstance(row, dict):
                problems.append(f"{unit_id}: reconciliation row must be an object")
                continue
            for field in ("id", "original_sha256", "original_excerpt"):
                if row.get(field) != expected[field]:
                    problems.append(f"{unit_id}: immutable source field {field} changed")
            verdict = row.get("verdict")
            if verdict not in {"preserved", "authorized_change"}:
                problems.append(f"{unit_id}: verdict must be preserved or authorized_change")
            rationale = str(row.get("rationale", "")).strip()
            if len(rationale) < 30:
                problems.append(f"{unit_id}: rationale must contain 30+ characters")
            evidence_rows = row.get("edited_evidence", [])
            if not isinstance(evidence_rows, list) or not evidence_rows:
                problems.append(f"{unit_id}: at least one edited_evidence mapping is required")
                continue
            best_overlap = 0.0
            unit_spans: list[tuple[int, int]] = []
            for evidence in evidence_rows:
                if not isinstance(evidence, dict):
                    problems.append(f"{unit_id}: edited_evidence row must be an object")
                    continue
                location = str(evidence.get("location", "")).strip()
                excerpt = str(evidence.get("excerpt", "")).strip()
                if not location:
                    problems.append(f"{unit_id}: edited_evidence location is required")
                if len(excerpt) < 20:
                    problems.append(f"{unit_id}: edited excerpt must contain 20+ characters")
                    continue
                start_char = evidence.get("start_char")
                end_char = evidence.get("end_char")
                if (
                    not isinstance(start_char, int)
                    or isinstance(start_char, bool)
                    or not isinstance(end_char, int)
                    or isinstance(end_char, bool)
                    or start_char < 0
                    or end_char <= start_char
                    or working_text[start_char:end_char] != excerpt
                ):
                    problems.append(
                        f"{unit_id}: edited excerpt must be bound to exact "
                        "start_char/end_char offsets in working text"
                    )
                    continue
                unit_spans.append((start_char, end_char))
                best_overlap = max(best_overlap, lexical_overlap(expected["original_excerpt"], excerpt))
            if unit_spans:
                mapped_spans.append(
                    (unit_id, min(start for start, _ in unit_spans), max(end for _, end in unit_spans))
                )
            if verdict == "preserved" and best_overlap < 0.08:
                problems.append(
                    f"{unit_id}: preserved mapping has insufficient lexical overlap "
                    f"({best_overlap:.3f}); inspect for an unrelated rubber stamp"
                )
            if verdict == "authorized_change":
                authorization = row.get("authorization")
                if not isinstance(authorization, dict):
                    problems.append(
                        f"{unit_id}: authorized_change requires a structured "
                        "unverified external authorization claim"
                    )
                else:
                    expected_binding = {
                        "trust": "unverified_external_claim",
                        "source_unit_id": unit_id,
                        "source_unit_sha256": expected["original_sha256"],
                    }
                    for field, value in expected_binding.items():
                        if authorization.get(field) != value:
                            problems.append(
                                f"{unit_id}: authorization {field} is not bound "
                                "to this immutable source unit"
                            )
                    if len(str(authorization.get("change_scope", "")).strip()) < 40:
                        problems.append(
                            f"{unit_id}: authorization change_scope must contain 40+ characters"
                        )
                    if len(str(authorization.get("user_quote", "")).strip()) < 25:
                        problems.append(
                            f"{unit_id}: authorization user_quote must contain 25+ characters"
                        )
                    if len(str(authorization.get("user_message_ref", "")).strip()) < 8:
                        problems.append(
                            f"{unit_id}: authorization user_message_ref must contain 8+ characters"
                        )
        for (left_id, left_start, left_end), (
            right_id,
            right_start,
            right_end,
        ) in zip(mapped_spans, mapped_spans[1:]):
            if right_start < left_start:
                problems.append(
                    f"{right_id}: edited evidence precedes {left_id}; "
                    "source-unit mappings must remain monotonic"
                )
            if right_start < left_end:
                problems.append(
                    f"{right_id}: edited evidence overlaps or reuses the mapping for {left_id}"
                )
    if kind == "style_review":
        mode = st.get("style_mode", "unselected")
        expected_reference = (
            original_sha(st) if mode == "source_as_reference" else references_sha(st)
        )
        if data.get("style_mode") != mode:
            problems.append("style_review style_mode differs from the active intake choice")
        if data.get("style_reference_sha256") != expected_reference:
            problems.append("style_review is stale for the active style baseline")
        expected_level = st.get("english_level", {}).get("target", "not_applicable")
        if data.get("english_level_target") != expected_level:
            problems.append("style_review English level differs from the intake target")
        if data.get("english_source_estimate") != st.get("english_level", {}).get(
            "source_estimate", ""
        ):
            problems.append("style_review English source estimate differs from intake")
    return not problems, problems, expected_subject


def validate_capability(st: dict, path: Path) -> tuple[bool, list[str]]:
    problems: list[str] = []
    try:
        data = V.load_json(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return False, [f"invalid JSON: {exc}"]
    if data.get("schema") != CAPABILITY_SCHEMA:
        problems.append(f"schema must be {CAPABILITY_SCHEMA}")
    if data.get("language") != st["language"]:
        problems.append("capability language does not match project language")
    selected = st["detector_policy"]["selected_services"]
    if data.get("selected_services") != selected:
        problems.append("selected_services do not match state policy")
    entries = data.get("services", {})
    known = registry()["services"]
    for service in selected:
        entry = entries.get(service)
        if not isinstance(entry, dict):
            problems.append(f"{service}: missing capability entry")
            continue
        base = known[service]
        expected_facts = {
            "display_name": base["display_name"],
            "url": base["url"],
            "kind": base["kind"],
            "independence_group": base["independence_group"],
            "guest_access": base.get("guest_access", False),
            "access_class": base.get("access_class", "unknown"),
            "languages": base.get("languages", []),
            "public_limit": base.get("public_limit"),
            "result": base.get("result", []),
        }
        if entry.get("registry_facts") != expected_facts:
            problems.append(f"{service}: registry_facts were changed or are stale")
        observation = entry.get("observation")
        if not isinstance(observation, dict):
            problems.append(f"{service}: observation must be an object")
            continue
        if observation.get("status") not in {"confirmed", "blocked"}:
            problems.append(f"{service}: status must be confirmed or blocked")
        if not observation.get("checked_at"):
            problems.append(f"{service}: checked_at is required")
        else:
            try:
                V.parse_iso(observation["checked_at"])
            except (ValueError, TypeError):
                problems.append(f"{service}: checked_at is not ISO-8601")
        if len(str(observation.get("evidence", "")).strip()) < 20:
            problems.append(f"{service}: evidence must contain 20+ characters")
        status = observation.get("status")
        access = observation.get("access_observed")
        allowed_access = {
            "guest", "authenticated_existing", "institutional_existing", "blocked"
        }
        if access not in allowed_access:
            problems.append(f"{service}: unsupported access_observed")
        supported = "*" in base.get("languages", []) or st["language"] in base.get("languages", [])
        if status == "confirmed":
            if not supported:
                problems.append(
                    f"{service}: registry does not support project language {st['language']}"
                )
            if observation.get("language_tested") is not True:
                problems.append(f"{service}: language_tested must be true after a live result")
            if observation.get("result_returned") is not True:
                problems.append(f"{service}: result_returned must be true when confirmed")
            if base.get("guest_access"):
                if access != "guest":
                    problems.append(
                        f"{service}: registry requires guest access for the default workflow"
                    )
            elif base.get("kind") == "institutional":
                if access != "institutional_existing":
                    problems.append(f"{service}: institutional existing access is required")
            else:
                if access != "authenticated_existing":
                    problems.append(
                        f"{service}: registry marks this service as non-guest; "
                        "guest cannot be asserted in capability"
                    )
                if len(str(observation.get("access_authorization_quote", "")).strip()) < 25:
                    problems.append(
                        f"{service}: authenticated use requires a specific user authorization quote"
                    )
        elif access != "blocked":
            problems.append(f"{service}: blocked status requires access_observed=blocked")
    return not problems, problems


def validate_report(path: Path) -> tuple[bool, list[str]]:
    text = V.read_text(path)
    problems = []
    if len(text.strip()) < 180:
        problems.append("report is too short")
    required = {
        "changes": r"(?im)^#{1,3}\s+(?:изменения|что изменено|changes)\b",
        "checks": r"(?im)^#{1,3}\s+(?:проверки|checks|verification)\b",
        "limits": r"(?im)^#{1,3}\s+(?:ограничения|limits|limitations)\b",
    }
    for name, pattern in required.items():
        if not re.search(pattern, text):
            problems.append(f"missing report section: {name}")
    return not problems, problems


def validate_overlap(st: dict, path: Path) -> tuple[bool, list[str]]:
    problems = []
    try:
        data = V.load_json(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return False, [f"invalid JSON: {exc}"]
    if data.get("schema") != OVERLAP_SCHEMA:
        problems.append(f"schema must be {OVERLAP_SCHEMA}")
    if data.get("draft_sha256") != working_sha(st):
        problems.append("overlap report is stale for the current working text")
    if data.get("high_risk_count") != 0:
        problems.append(f"overlap report has {data.get('high_risk_count')} high-risk matches")
    if not data.get("sources"):
        problems.append("overlap report contains no source corpus")
    return not problems, problems


def cmd_artifact(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    try:
        artifact_path = V.resolve_existing(args.file)
        with V.locked_json(path) as st:
            if st.get("schema") != STATE_SCHEMA:
                raise StateError("not a Palimpsest v3 state")
            if args.kind in ATTESTATIONS:
                ok, problems, subject = validate_attestation(st, args.kind, artifact_path)
            elif args.kind == "capability_review":
                ok, problems = validate_capability(st, artifact_path)
                subject = ""
            elif args.kind == "detector_round":
                ok, problems = validate_detector_round(st, artifact_path)
                subject = working_sha(st)
            elif args.kind == "overlap_report":
                ok, problems = validate_overlap(st, artifact_path)
                subject = working_sha(st)
            elif args.kind == "report":
                ok, problems = validate_report(artifact_path)
                subject = working_sha(st)
            else:  # argparse choices should make this unreachable.
                raise StateError(f"unknown artifact kind {args.kind}")
            if not ok:
                raise StateError("; ".join(problems))
            st["artifacts"][args.kind] = {
                "path": str(artifact_path),
                "file_sha256": V.sha256_file(artifact_path),
                "subject_sha256": subject,
                "registered_at": V.now(),
            }
            if args.kind == "detector_round":
                round_data = V.load_json(artifact_path)
                st.setdefault("detector_rounds", []).append(
                    {
                        "round_id": round_data["round_id"],
                        "round_status": round_data["round_status"],
                        "working_sha256": subject,
                        "path": str(artifact_path),
                        "file_sha256": V.sha256_file(artifact_path),
                        "registered_at": V.now(),
                    }
                )
            add_event(st, "artifact_registered", kind=args.kind)
    except (FileNotFoundError, StateError) as exc:
        return fail(str(exc))
    print(f"artifact accepted: {args.kind} -> {artifact_path}")
    return 0


def current_target_sha(st: dict, target: str) -> str:
    if target == "DOCUMENT":
        return working_sha(st)
    segment_path = Path(st["files"]["segments"])
    if not segment_path.is_file():
        raise StateError(f"segment map does not exist: {segment_path}")
    data = V.load_json(segment_path)
    if data.get("schema") != "palimpsest.segments.v3":
        raise StateError("segment map is not v3")
    segment = next((x for x in data.get("segments", []) if x.get("id") == target), None)
    if not segment:
        raise StateError(f"unknown segment target {target}")
    return segment["current_sha256"]


def capability_entry(st: dict, service: str) -> dict:
    record = st.get("artifacts", {}).get("capability_review")
    if not record:
        raise StateError("register capability_review before detector results")
    path = Path(record["path"])
    if not path.is_file() or V.sha256_file(path) != record["file_sha256"]:
        raise StateError("capability_review is missing or changed; register it again")
    ok, problems = validate_capability(st, path)
    if not ok:
        raise StateError("capability_review invalid: " + "; ".join(problems))
    data = V.load_json(path)
    entry = data["services"].get(service)
    if not entry:
        raise StateError(f"{service} is absent from capability_review")
    observation = entry["observation"]
    if observation.get("status") != "confirmed":
        raise StateError(f"{service} capability is not confirmed")
    base = registry()["services"][service]
    return {
        **base,
        "observation": observation,
    }


def cmd_detector_prepare(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    service = args.service.lower()
    out = Path(args.out).expanduser().resolve()
    try:
        with V.locked_json(path) as st:
            if st.get("schema") != STATE_SCHEMA:
                raise StateError("not a Palimpsest v3 state")
            if service not in st["detector_policy"]["selected_services"]:
                raise StateError(f"{service} is not selected in detector policy")
            capability_entry(st, service)
            digest = current_target_sha(st, args.target)
            issued = datetime.now(timezone.utc)
            challenge = {
                "schema": DETECTOR_CHALLENGE_SCHEMA,
                "id": secrets.token_urlsafe(16),
                "nonce": secrets.token_urlsafe(24),
                "service": service,
                "target": args.target,
                "content_sha256": digest,
                "issued_at": issued.isoformat(),
                "expires_at": (issued + timedelta(hours=2)).isoformat(),
            }
            V.atomic_write_json(out, challenge)
            st.setdefault("detector_challenges", []).append(
                {
                    **challenge,
                    "path": str(out),
                    "file_sha256": V.sha256_file(out),
                    "used_at": "",
                }
            )
            add_event(
                st,
                "detector_challenge",
                challenge_id=challenge["id"],
                service=service,
                target=args.target,
            )
    except (FileNotFoundError, StateError, KeyError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    print(f"detector challenge prepared: {out}")
    return 0


def service_url_matches(service_url: str, result_url: str) -> bool:
    expected = (urlparse(service_url).hostname or "").lower()
    actual = (urlparse(result_url).hostname or "").lower()
    return bool(expected and actual and (actual == expected or actual.endswith("." + expected)))


def observation_raw_path(observation_path: Path, value: str) -> Path:
    raw = Path(value).expanduser()
    return (observation_path.parent / raw).resolve() if not raw.is_absolute() else raw.resolve()


def capture_artifact_health(path: Path) -> tuple[bool, str]:
    """Reject files that only pretend to be a browser image or PDF.

    This is structural validation, not OCR or cryptographic proof of what was
    visible in the browser.  It closes the trivial ``PNG header + random
    bytes`` bypass while keeping the trust boundary explicit.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        return False, f"cannot read raw detector artifact: {exc}"
    suffix = path.suffix.lower()
    if suffix == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return False, "raw PNG has an invalid signature"
        cursor = 8
        chunks: list[bytes] = []
        width = height = 0
        while cursor + 12 <= len(data):
            length = struct.unpack(">I", data[cursor:cursor + 4])[0]
            chunk_type = data[cursor + 4:cursor + 8]
            end = cursor + 12 + length
            if end > len(data):
                return False, "raw PNG contains a truncated chunk"
            payload = data[cursor + 8:cursor + 8 + length]
            expected_crc = struct.unpack(">I", data[cursor + 8 + length:end])[0]
            actual_crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
            if actual_crc != expected_crc:
                return False, "raw PNG contains an invalid chunk checksum"
            chunks.append(chunk_type)
            if chunk_type == b"IHDR":
                if length != 13:
                    return False, "raw PNG has an invalid IHDR"
                width, height = struct.unpack(">II", payload[:8])
            cursor = end
            if chunk_type == b"IEND":
                break
        if not chunks or chunks[0] != b"IHDR" or b"IDAT" not in chunks or b"IEND" not in chunks:
            return False, "raw PNG is missing required image chunks"
        if width < 320 or height < 180:
            return False, "browser screenshot must be at least 320x180 pixels"
        return True, f"valid PNG capture {width}x{height}"
    if suffix in {".jpg", ".jpeg"}:
        if not (data.startswith(b"\xff\xd8") and data.rstrip().endswith(b"\xff\xd9")):
            return False, "raw JPEG has invalid start/end markers"
        cursor = 2
        width = height = 0
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while cursor + 4 <= len(data):
            if data[cursor] != 0xFF:
                cursor += 1
                continue
            marker = data[cursor + 1]
            cursor += 2
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if cursor + 2 > len(data):
                break
            length = struct.unpack(">H", data[cursor:cursor + 2])[0]
            if length < 2 or cursor + length > len(data):
                return False, "raw JPEG contains a truncated segment"
            if marker in sof_markers and length >= 7:
                height, width = struct.unpack(">HH", data[cursor + 3:cursor + 7])
                break
            cursor += length
        if width < 320 or height < 180:
            return False, "browser screenshot must be at least 320x180 pixels"
        return True, f"valid JPEG capture {width}x{height}"
    if suffix == ".webp":
        if not (
            len(data) >= 20
            and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP"
            and data[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
        ):
            return False, "raw WebP has an invalid container"
        declared = struct.unpack("<I", data[4:8])[0] + 8
        if abs(declared - len(data)) > 1:
            return False, "raw WebP length does not match its container"
        return True, "valid WebP capture"
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            return False, "raw PDF has an invalid header or trailer"
        if b"/Type /Page" not in data and b"/Type/Page" not in data:
            return False, "raw PDF does not expose a page object"
        return True, "valid PDF capture"
    return False, "unsupported raw detector artifact format"


def validate_detector_observation(
    st: dict,
    observation_path: Path,
) -> tuple[dict, Path, dict]:
    data = V.load_json(observation_path)
    if data.get("schema") != DETECTOR_OBSERVATION_SCHEMA:
        raise StateError(f"observation schema must be {DETECTOR_OBSERVATION_SCHEMA}")
    challenge = next(
        (
            item for item in st.get("detector_challenges", [])
            if item.get("id") == data.get("challenge_id")
        ),
        None,
    )
    if not challenge:
        raise StateError("observation has no prepared detector challenge")
    if challenge.get("used_at"):
        raise StateError("detector challenge was already consumed")
    challenge_path = Path(challenge["path"])
    if not challenge_path.is_file() or V.sha256_file(challenge_path) != challenge["file_sha256"]:
        raise StateError("detector challenge file is missing or changed")
    if data.get("challenge_nonce") != challenge.get("nonce"):
        raise StateError("detector challenge nonce does not match")
    for field in ("service", "target", "content_sha256"):
        if data.get(field) != challenge.get(field):
            raise StateError(f"observation {field} does not match prepared challenge")
    service = data["service"]
    if service not in st["detector_policy"]["selected_services"]:
        raise StateError(f"{service} is not selected in detector policy")
    entry = capability_entry(st, service)
    if current_target_sha(st, data["target"]) != data["content_sha256"]:
        raise StateError("observation is stale for the current target digest")
    score = data.get("score_pct")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 100:
        raise StateError("observation score_pct must be a number between 0 and 100")
    if not str(data.get("label", "")).strip():
        raise StateError("observation label is required")
    mode = data.get("capture_mode")
    allowed_modes = {"browser_observed", "vendor_api", "institutional_report"}
    if mode not in allowed_modes:
        raise StateError(f"capture_mode must be one of {', '.join(sorted(allowed_modes))}")
    if mode == "institutional_report" and entry.get("kind") != "institutional":
        raise StateError("institutional_report mode is valid only for institutional services")
    result_url = str(data.get("result_url", "")).strip()
    if not service_url_matches(entry["url"], result_url):
        raise StateError("result_url host does not match the selected service registry URL")
    try:
        observed_at = V.parse_iso(str(data.get("observed_at", "")))
        issued_at = V.parse_iso(challenge["issued_at"])
        expires_at = V.parse_iso(challenge["expires_at"])
    except (ValueError, TypeError) as exc:
        raise StateError("observation timestamps must be ISO-8601") from exc
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if observed_at < issued_at - timedelta(minutes=5) or observed_at > expires_at:
        raise StateError("observation timestamp is outside the challenge window")
    excerpt = str(data.get("visible_result_excerpt", "")).strip()
    if len(excerpt) < 15:
        raise StateError("visible_result_excerpt must contain 15+ characters")
    score_tokens = {f"{float(score):g}", f"{float(score):.1f}"}
    if not any(token in excerpt for token in score_tokens):
        raise StateError("visible_result_excerpt must contain the recorded score")
    raw_value = str(data.get("raw_artifact", "")).strip()
    if not raw_value:
        raise StateError("raw_artifact is required")
    raw_path = observation_raw_path(observation_path, raw_value)
    if not raw_path.is_file():
        raise StateError(f"raw detector artifact does not exist: {raw_path}")
    if raw_path.stat().st_size < 512:
        raise StateError("raw detector artifact is too small to be a captured result")
    expected_raw_sha = str(data.get("raw_artifact_sha256", ""))
    if expected_raw_sha != V.sha256_file(raw_path):
        raise StateError("raw detector artifact SHA-256 does not match observation")
    suffix = raw_path.suffix.lower()
    if mode in {"browser_observed", "institutional_report"} and suffix not in {
        ".png", ".jpg", ".jpeg", ".webp", ".pdf"
    }:
        raise StateError("browser/institutional observations require an image or PDF artifact")
    if mode == "vendor_api" and suffix != ".json":
        raise StateError("vendor_api observations require a raw JSON response")
    if mode in {"browser_observed", "institutional_report"}:
        healthy, message = capture_artifact_health(raw_path)
        if not healthy:
            raise StateError(message)
    return data, raw_path, challenge


def cmd_detector(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    try:
        observation_path = V.resolve_existing(args.observation)
        with V.locked_json(path) as st:
            if st.get("schema") != STATE_SCHEMA:
                raise StateError("not a Palimpsest v3 state")
            data, raw_path, challenge = validate_detector_observation(st, observation_path)
            service = data["service"]
            entry = registry()["services"][service]
            result = {
                "service": service,
                "display_name": entry.get("display_name", service),
                "target": data["target"],
                "content_sha256": data["content_sha256"],
                "score_pct": float(data["score_pct"]),
                "label": data["label"],
                "kind": entry["kind"],
                "independence_group": entry["independence_group"],
                "challenge_id": challenge["id"],
                "capture_mode": data["capture_mode"],
                "observation_path": str(observation_path),
                "observation_sha256": V.sha256_file(observation_path),
                "raw_artifact_path": str(raw_path),
                "raw_artifact_sha256": V.sha256_file(raw_path),
                "checked_at": data["observed_at"],
                "evidence_trust": "captured_observation_not_authorship_proof",
                "note": str(data.get("note", "")),
            }
            st["detector_results"].append(result)
            challenge["used_at"] = V.now()
            add_event(
                st,
                "detector_result",
                service=service,
                target=data["target"],
                score=data["score_pct"],
                challenge_id=challenge["id"],
            )
    except (
        FileNotFoundError,
        StateError,
        KeyError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return fail(str(exc))
    print(
        f"detector observation recorded: {result['service']} "
        f"{result['target']} = {result['score_pct']:g}%"
    )
    return 0


def plateau_target_text(
    candidate: Path,
    candidate_sha: str,
    target: str,
    row: dict,
) -> tuple[str, str]:
    text = V.read_text(candidate)
    if target == "DOCUMENT":
        return text, candidate_sha
    map_path = V.resolve_existing(row.get("segment_map_path", ""))
    if row.get("segment_map_sha256") != V.sha256_file(map_path):
        raise StateError("plateau segment map SHA-256 does not match file")
    mapping = V.load_json(map_path)
    if (
        mapping.get("schema") != "palimpsest.segments.v3"
        or mapping.get("file_sha256") != candidate_sha
        or mapping.get("length_chars") != len(text)
    ):
        raise StateError("plateau segment map is not bound to the candidate document")
    cursor = 0
    chosen = None
    for item in mapping.get("segments", []):
        start, end = item.get("start"), item.get("end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or start != cursor
            or end < start
            or end > len(text)
        ):
            raise StateError("plateau segment map does not provide exact ordered coverage")
        body = text[start:end]
        if V.sha256_text(body) != item.get("current_sha256"):
            raise StateError("plateau segment map contains a stale segment digest")
        if item.get("id") == target:
            chosen = (body, item["current_sha256"])
        cursor = end
    if cursor != len(text):
        raise StateError("plateau segment map leaves candidate content unmapped")
    if not chosen:
        raise StateError(f"plateau candidate map has no target {target}")
    return chosen


def validate_plateau_candidate(
    st: dict,
    service: str,
    target: str,
    row: dict,
) -> dict:
    candidate = V.resolve_existing(row.get("candidate_path", ""))
    candidate_sha = V.sha256_file(candidate)
    if row.get("candidate_sha256") != candidate_sha:
        raise StateError("plateau candidate SHA-256 does not match file")
    target_text, target_sha = plateau_target_text(
        candidate,
        candidate_sha,
        target,
        row,
    )
    fidelity_path = V.resolve_existing(row.get("fidelity_path", ""))
    if row.get("fidelity_sha256") != V.sha256_file(fidelity_path):
        raise StateError("plateau fidelity report SHA-256 does not match file")
    fidelity = V.load_json(fidelity_path)
    if (
        fidelity.get("schema") != "palimpsest.fidelity.v3.1"
        or fidelity.get("ok") is not True
        or fidelity.get("scope", {}).get("original_sha256") != original_sha(st)
        or fidelity.get("scope", {}).get("edited_sha256") != candidate_sha
    ):
        raise StateError("plateau candidate does not have a current passing fidelity report")
    semantic_path = V.resolve_existing(row.get("semantic_review_path", ""))
    if row.get("semantic_review_sha256") != V.sha256_file(semantic_path):
        raise StateError("plateau semantic review SHA-256 does not match file")
    candidate_state = {
        **st,
        "files": {**st["files"], "working": str(candidate)},
    }
    semantic_ok, semantic_problems, _ = validate_attestation(
        candidate_state,
        "semantic_review",
        semantic_path,
    )
    if not semantic_ok:
        raise StateError(
            "plateau candidate semantic review is invalid: "
            + "; ".join(semantic_problems)
        )
    if len(str(row.get("change_summary", "")).strip()) < 40:
        raise StateError("plateau candidate change_summary must contain 40+ characters")
    move_ids = row.get("move_ids", [])
    if not isinstance(move_ids, list) or not move_ids:
        raise StateError("plateau candidate requires at least one digest-bound move_id")
    matching_moves = []
    for move_id in move_ids:
        move = next(
            (
                item
                for item in st.get("moves", [])
                if item.get("id") == move_id
                and item.get("working_sha256") == candidate_sha
            ),
            None,
        )
        if not move:
            raise StateError(
                f"plateau candidate move {move_id!r} is missing or bound to another digest"
            )
        if move.get("mechanism") not in PLATEAU_MECHANISMS:
            raise StateError(
                f"plateau candidate move {move_id!r} has no recognized mechanism"
            )
        matching_moves.append(move)
    minimality, minimality_rc, minimality_err = run_json(
        [
            sys.executable,
            str(SCRIPTS / "minimality.py"),
            "--original",
            st["files"]["original"],
            "--current",
            str(candidate),
            "--budget",
            str(st["budgets"]["document_change_ratio"]),
            "--para-budget",
            str(st["budgets"]["paragraph_change_ratio"]),
            "--json",
        ]
    )
    if minimality_rc != 0 or not minimality:
        raise StateError(
            "plateau candidate exceeds the edit budget: "
            + (minimality_err or "minimality screen failed")
        )
    if (
        st["language"] == "en"
        and st.get("english_level", {}).get("target")
        not in {None, "", "unselected", "not_applicable"}
    ):
        level, level_rc, level_err = run_json(
            [
                sys.executable,
                str(SCRIPTS / "english_level.py"),
                "--original",
                st["files"]["original"],
                "--edited",
                str(candidate),
                "--target",
                st["english_level"]["target"],
                "--json",
            ]
        )
        if level_rc != 0 or not level or level.get("ok") is not True:
            raise StateError(
                "plateau candidate drifts outside the English-level envelope: "
                + (level_err or ", ".join(level.get("drift_signals", [])) if level else "screen failed")
            )
    style_command: list[str] | None = None
    if st.get("style_mode") == "external_reference" and st["files"].get("references"):
        style_command = [
            sys.executable,
            str(SCRIPTS / "style_distance.py"),
            "--ref",
            *st["files"]["references"],
            "--cand",
            str(candidate),
            "--baseline",
            st["files"]["original"],
            "--json",
        ]
    elif st.get("style_mode") == "source_as_reference":
        style_command = [
            sys.executable,
            str(SCRIPTS / "style_distance.py"),
            "--ref",
            st["files"]["original"],
            "--cand",
            str(candidate),
            "--json",
        ]
    if style_command:
        style_payload, style_rc, style_err = run_json(style_command)
        style_policy_ok, style_policy_details = assess_style_metric(st, style_payload)
        if style_rc != 0 or not style_payload or not style_policy_ok:
            raise StateError(
                "plateau candidate fails the style metric policy: "
                + (style_err or "; ".join(style_policy_details))
            )
    observation_path = V.resolve_existing(row.get("observation_path", ""))
    if row.get("observation_sha256") != V.sha256_file(observation_path):
        raise StateError("plateau observation SHA-256 does not match file")
    observation = V.load_json(observation_path)
    if (
        observation.get("schema") != DETECTOR_OBSERVATION_SCHEMA
        or observation.get("service") != service
        or observation.get("target") != target
        or observation.get("content_sha256") != target_sha
    ):
        raise StateError("plateau observation does not match service/target/candidate")
    challenge = next(
        (
            item
            for item in st.get("detector_challenges", [])
            if item.get("id") == observation.get("challenge_id")
        ),
        None,
    )
    if not challenge:
        raise StateError("plateau observation has no state-recorded challenge")
    if (
        observation.get("challenge_nonce") != challenge.get("nonce")
        or challenge.get("service") != service
        or challenge.get("target") != target
        or challenge.get("content_sha256") != target_sha
        or not challenge.get("used_at")
    ):
        raise StateError(
            "plateau observation is not bound to a consumed matching challenge"
        )
    challenge_path = Path(str(challenge.get("path", "")))
    if (
        not challenge_path.is_file()
        or V.sha256_file(challenge_path) != challenge.get("file_sha256")
    ):
        raise StateError("plateau detector challenge is missing or changed")
    raw = observation_raw_path(observation_path, str(observation.get("raw_artifact", "")))
    if (
        not raw.is_file()
        or raw.stat().st_size < 512
        or V.sha256_file(raw) != observation.get("raw_artifact_sha256")
    ):
        raise StateError("plateau observation raw artifact is missing or changed")
    score = observation.get("score_pct")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise StateError("plateau observation score is invalid")
    if float(score) != float(row.get("score_pct")):
        raise StateError("plateau row score differs from observation")
    result = next(
        (
            item
            for item in st.get("detector_results", [])
            if item.get("challenge_id") == challenge.get("id")
        ),
        None,
    )
    if not result:
        raise StateError(
            "plateau candidate observation was never registered as a result"
        )
    integrity_ok, integrity_message = detector_result_integrity(result)
    if (
        not integrity_ok
        or result.get("observation_sha256") != V.sha256_file(observation_path)
        or float(result.get("score_pct", -1)) != float(score)
    ):
        raise StateError(
            "plateau candidate result integrity failed: " + integrity_message
        )
    return {
        "score": float(score),
        "target_text": target_text,
        "candidate_sha256": candidate_sha,
        "mechanisms": sorted({move["mechanism"] for move in matching_moves}),
        "doc_change_ratio": minimality.get("doc_change_ratio"),
    }


def cmd_plateau_template(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    service = args.service.lower()
    out = Path(args.out).expanduser().resolve()
    try:
        st = load_state(path)
        if service not in st["detector_policy"]["selected_services"]:
            raise StateError(f"{service} is not selected")
        payload = {
            "schema": PLATEAU_SCHEMA,
            "service": service,
            "target": args.target,
            "content_sha256": current_target_sha(st, args.target),
            "reason": "",
            "candidates": [
                {
                    "candidate_path": "",
                    "candidate_sha256": "",
                    "fidelity_path": "",
                    "fidelity_sha256": "",
                    "semantic_review_path": "",
                    "semantic_review_sha256": "",
                    "move_ids": [],
                    "change_summary": "",
                    "segment_map_path": "",
                    "segment_map_sha256": "",
                    "observation_path": "",
                    "observation_sha256": "",
                    "score_pct": None,
                }
                for _ in range(3)
            ],
            "instructions": [
                "Use three materially different, non-cosmetic candidates, including the current working file.",
                "Every candidate needs a passing v3.1 fidelity report, full semantic review, digest-bound moves, and a registered challenge-bound detector observation.",
                "Candidate moves must use at least two distinct edit mechanisms across the bundle.",
                "Each candidate is re-screened for minimality, English-level drift, and reliable style-metric policy.",
                "The last three service scores must exceed the threshold and stay within one percentage point.",
            ],
        }
        V.atomic_write_json(out, payload)
    except (FileNotFoundError, StateError, KeyError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    print(f"plateau template created: {out}")
    return 0


def cosmetic_substitution_only(left: str, right: str) -> bool:
    """Detect small same-position synonym swaps with no structural intervention."""
    punctuation = ".?!;:—–()"
    left_signature = (
        len([p for p in T.paragraphs(left) if p.text.strip()]),
        len(T.sentences(left)),
        tuple(left.count(mark) for mark in punctuation),
    )
    right_signature = (
        len([p for p in T.paragraphs(right) if p.text.strip()]),
        len(T.sentences(right)),
        tuple(right.count(mark) for mark in punctuation),
    )
    if left_signature != right_signature:
        return False
    left_words = T.words(left)
    right_words = T.words(right)
    opcodes = difflib.SequenceMatcher(
        None,
        left_words,
        right_words,
        autojunk=False,
    ).get_opcodes()
    replaced = 0
    saw_change = False
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        saw_change = True
        left_size = i2 - i1
        right_size = j2 - j1
        if tag != "replace" or left_size != right_size or max(left_size, right_size) > 3:
            return False
        replaced += max(left_size, right_size)
    ratio = replaced / max(len(left_words), len(right_words), 1)
    return saw_change and ratio <= 0.15


def cmd_plateau(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    try:
        plateau_path = V.resolve_existing(args.file)
        data = V.load_json(plateau_path)
        with V.locked_json(path) as st:
            if data.get("schema") != PLATEAU_SCHEMA:
                raise StateError(f"plateau schema must be {PLATEAU_SCHEMA}")
            service = str(data.get("service", "")).lower()
            target = str(data.get("target", "DOCUMENT"))
            if service not in st["detector_policy"]["selected_services"]:
                raise StateError(f"{service} is not selected")
            digest = current_target_sha(st, target)
            if data.get("content_sha256") != digest:
                raise StateError("plateau report is stale for current target")
            if len(str(data.get("reason", "")).strip()) < 40:
                raise StateError("plateau reason must contain 40+ characters")
            candidates = data.get("candidates", [])
            if not isinstance(candidates, list) or len(candidates) < 3:
                raise StateError("plateau requires at least three candidate bundles")
            validated = [
                validate_plateau_candidate(st, service, target, row)
                for row in candidates
                if isinstance(row, dict)
            ]
            if len(validated) != len(candidates):
                raise StateError("every plateau candidate must be an object")
            scores = [item["score"] for item in validated]
            target_texts = [item["target_text"] for item in validated]
            candidate_shas = [row.get("candidate_sha256") for row in candidates]
            if len(set(candidate_shas)) != len(candidate_shas):
                raise StateError("plateau candidates must have distinct content digests")
            if working_sha(st) not in candidate_shas:
                raise StateError("current working text must be one plateau candidate")
            for left_index in range(len(target_texts)):
                for right_index in range(left_index + 1, len(target_texts)):
                    left_words = T.words(target_texts[left_index])
                    right_words = T.words(target_texts[right_index])
                    difference = 1.0 - difflib.SequenceMatcher(
                        None,
                        left_words,
                        right_words,
                        autojunk=False,
                    ).ratio()
                    if difference < 0.05:
                        raise StateError(
                            "plateau candidates are not materially different "
                            f"at the target ({difference:.3f} < 0.050)"
                        )
                    if cosmetic_substitution_only(
                        target_texts[left_index],
                        target_texts[right_index],
                    ):
                        raise StateError(
                            "plateau candidates differ only by small same-position "
                            "substitutions; use a structural or rhetorical mechanism"
                        )
            mechanisms = {
                mechanism
                for item in validated
                for mechanism in item["mechanisms"]
            }
            if len(mechanisms) < 2:
                raise StateError(
                    "plateau bundle must exercise at least two distinct edit mechanisms"
                )
            threshold = float(st["detector_policy"]["threshold_pct"])
            if any(score < threshold for score in scores):
                raise StateError("plateau is only for unresolved above-threshold observations")
            if max(scores[-3:]) - min(scores[-3:]) > 1.0:
                raise StateError("last three plateau scores differ by more than 1 point")
            record = {
                "service": service,
                "target": target,
                "content_sha256": digest,
                "path": str(plateau_path),
                "file_sha256": V.sha256_file(plateau_path),
                "scores": scores,
                "mechanisms": sorted(mechanisms),
                "candidate_change_ratios": [
                    item["doc_change_ratio"] for item in validated
                ],
                "recorded_at": V.now(),
            }
            st.setdefault("plateaus", []).append(record)
            add_event(st, "detector_plateau", service=service, target=target)
    except (
        FileNotFoundError,
        StateError,
        KeyError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return fail(str(exc))
    print(f"detector plateau registered: {record['service']}/{record['target']}")
    return 0


def cmd_waive(args: argparse.Namespace) -> int:
    reason = args.reason.strip()
    quote = args.user_quote.strip()
    if len(reason) < 20:
        return fail("waiver reason must contain 20+ characters")
    if len(quote) < 25:
        return fail("waiver requires a specific user quote of 25+ characters")
    path = state_path(args.state)
    service = args.service.lower()
    try:
        with V.locked_json(path) as st:
            if st.get("schema") != STATE_SCHEMA:
                raise StateError("not a Palimpsest v3 state")
            if st["detector_policy"].get("score_mandatory"):
                raise StateError(
                    "waivers cannot satisfy score_mandatory F1; change the explicit "
                    "Q3 detector scope in conversation and restart current detector evidence"
                )
            if service not in st["detector_policy"]["selected_services"]:
                raise StateError(f"{service} is not selected")
            # Resolve now: a DOCUMENT waiver is tied to the current document
            # digest; a segment waiver is tied to that segment's current digest.
            digest = current_target_sha(st, args.target)
            st["waivers"].append(
                {
                    "service": service,
                    "target": args.target,
                    "content_sha256": digest,
                    "reason": reason,
                    "user_quote": quote,
                    "code": args.code,
                    "recorded_at": V.now(),
                }
            )
            add_event(st, "waiver", service=service, target=args.target, code=args.code)
    except (FileNotFoundError, StateError, KeyError) as exc:
        return fail(str(exc))
    print(f"waiver recorded only for {service}/{args.target}; final status cannot be fully green")
    return 0


def cmd_detector_policy(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    services = [x.lower() for x in V.parse_csv(args.services)] if args.services else None
    try:
        with V.locked_json(path) as st:
            if st.get("schema") != STATE_SCHEMA:
                raise StateError("not a Palimpsest v3 state")
            policy = st["detector_policy"]
            if services is not None:
                if policy.get("score_mandatory"):
                    raise StateError(
                        "score_mandatory detector scope cannot be changed with "
                        "detector-policy; record a new explicit Q3 intake answer "
                        "after an actual user message"
                    )
                known = registry()["services"]
                unknown = [x for x in services if x not in known]
                if unknown:
                    raise StateError(f"unknown services: {', '.join(unknown)}")
                if st["flags"]["F1"] and "zerogpt" not in services:
                    raise StateError("ZeroGPT cannot be removed from the F1 policy")
                policy["selected_services"] = services
                # A capability review for another selection is no longer valid.
                st["artifacts"].pop("capability_review", None)
            if args.threshold is not None:
                if not 0 <= args.threshold <= 100:
                    raise StateError("threshold must be 0..100")
                if (
                    policy.get("score_mandatory")
                    and args.threshold > HARD_DETECTOR_MAX_EXCLUSIVE
                ):
                    raise StateError(
                        f"score_mandatory threshold cannot exceed "
                        f"{HARD_DETECTOR_MAX_EXCLUSIVE:g}%"
                    )
                policy["threshold_pct"] = args.threshold
                policy["soft_target_pct"] = min(
                    SOFT_DETECTOR_TARGET_EXCLUSIVE,
                    args.threshold,
                )
            if args.min_independent is not None:
                if args.min_independent < 1:
                    raise StateError("minimum independent services must be >=1")
                registry_minimum = int(registry()["policy"]["minimum_independent_services"])
                if (
                    args.min_independent < registry_minimum
                    and len((args.user_quote or "").strip()) < 25
                ):
                    raise StateError(
                        f"reducing minimum below {registry_minimum} requires a "
                        "specific 25+ character user quote"
                    )
                policy["minimum_independent"] = args.min_independent
                if args.min_independent < registry_minimum:
                    policy["minimum_acceptance_quote"] = args.user_quote.strip()
            if args.coverage:
                if policy.get("score_mandatory") and args.coverage != "full":
                    raise StateError(
                        "score_mandatory F1 forbids risk_sampled detector coverage"
                    )
                if args.coverage == "risk_sampled" and len((args.user_quote or "").strip()) < 25:
                    raise StateError("risk_sampled requires a specific 25+ character user quote")
                policy["coverage"] = args.coverage
                policy["coverage_acceptance_quote"] = args.user_quote or ""
            if args.sample_ids is not None:
                policy["sample_ids"] = V.parse_csv(args.sample_ids)
            st["detector_results"] = []
            st["detector_rounds"] = []
            st["artifacts"].pop("detector_round", None)
            refresh_goal(st)
            add_event(st, "detector_policy_changed")
    except (FileNotFoundError, StateError) as exc:
        return fail(str(exc))
    print("detector policy updated; re-register capability_review when service selection changed")
    return 0


def cmd_move(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    if len(args.hypothesis.strip()) < 15:
        return fail("move hypothesis must contain 15+ characters")
    try:
        with V.locked_json(path) as st:
            st["moves"].append(
                {
                    "id": args.id,
                    "span": args.span,
                    "mechanism": args.mechanism or "",
                    "hypothesis": args.hypothesis,
                    "outcome": args.outcome or "",
                    "working_sha256": working_sha(st),
                    "recorded_at": V.now(),
                }
            )
            add_event(st, "move", move_id=args.id, span=args.span)
    except (FileNotFoundError, KeyError) as exc:
        return fail(str(exc))
    print(f"move recorded: {args.id} @ {args.span}")
    return 0


def cmd_park(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    try:
        with V.locked_json(path) as st:
            st["parked"].append(
                {
                    "id": args.id,
                    "reason": args.reason,
                    "revisit_after": args.revisit_after or "",
                    "recorded_at": V.now(),
                }
            )
            add_event(st, "park", parked_id=args.id)
    except FileNotFoundError as exc:
        return fail(str(exc))
    print(f"parked: {args.id}")
    return 0


def artifact_health(st: dict, kind: str) -> tuple[bool, str]:
    record = st.get("artifacts", {}).get(kind)
    if not record:
        return False, f"{kind}: not registered"
    path = Path(record["path"])
    if not path.is_file():
        return False, f"{kind}: file missing"
    if V.sha256_file(path) != record.get("file_sha256"):
        return False, f"{kind}: file changed after registration"
    if kind in ATTESTATIONS:
        ok, problems, _ = validate_attestation(st, kind, path)
    elif kind == "capability_review":
        ok, problems = validate_capability(st, path)
    elif kind == "detector_round":
        ok, problems = validate_detector_round(st, path)
    elif kind == "overlap_report":
        ok, problems = validate_overlap(st, path)
    elif kind == "report":
        ok, problems = validate_report(path)
        if record.get("subject_sha256") != working_sha(st):
            ok = False
            problems.append("report is stale for current working text")
    else:
        return False, f"{kind}: unknown artifact type"
    return ok, f"{kind}: {'valid' if ok else '; '.join(problems)}"


def semantic_authorization_units(st: dict) -> list[str]:
    """Return declared change exceptions; local files cannot authenticate consent."""
    record = st.get("artifacts", {}).get("semantic_review")
    if not record:
        return []
    path = Path(str(record.get("path", "")))
    if not path.is_file() or V.sha256_file(path) != record.get("file_sha256"):
        return []
    try:
        data = V.load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return [
        str(row.get("id"))
        for row in data.get("source_units", [])
        if isinstance(row, dict) and row.get("verdict") == "authorized_change"
    ]


def latest_current_result(st: dict, service: str, target: str, digest: str) -> dict | None:
    matches = [
        x for x in st.get("detector_results", [])
        if x.get("service") == service
        and x.get("target") == target
        and x.get("content_sha256") == digest
    ]
    return matches[-1] if matches else None


def current_waiver(st: dict, service: str, target: str, digest: str) -> dict | None:
    matches = [
        x for x in st.get("waivers", [])
        if x.get("service") == service
        and x.get("target") == target
        and x.get("content_sha256") == digest
    ]
    return matches[-1] if matches else None


def current_plateau(st: dict, service: str, target: str, digest: str) -> dict | None:
    matches = [
        item for item in st.get("plateaus", [])
        if item.get("service") == service
        and item.get("target") == target
        and item.get("content_sha256") == digest
    ]
    if not matches:
        return None
    record = matches[-1]
    path = Path(record["path"])
    if not path.is_file() or V.sha256_file(path) != record.get("file_sha256"):
        return None
    return record


def detector_result_integrity(result: dict) -> tuple[bool, str]:
    service = result.get("service", "")
    base = registry()["services"].get(service)
    if not base:
        return False, "unknown service"
    if result.get("kind") != base.get("kind"):
        return False, "kind differs from registry"
    if result.get("independence_group") != base.get("independence_group"):
        return False, "independence group differs from registry"
    observation_path = Path(str(result.get("observation_path", "")))
    raw_path = Path(str(result.get("raw_artifact_path", "")))
    if not observation_path.is_file():
        return False, "observation file missing"
    if V.sha256_file(observation_path) != result.get("observation_sha256"):
        return False, "observation file changed"
    if not raw_path.is_file():
        return False, "raw artifact missing"
    if V.sha256_file(raw_path) != result.get("raw_artifact_sha256"):
        return False, "raw artifact changed"
    try:
        observation = V.load_json(observation_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False, "observation JSON is invalid"
    expected = {
        "service": result.get("service"),
        "target": result.get("target"),
        "content_sha256": result.get("content_sha256"),
        "score_pct": result.get("score_pct"),
        "label": result.get("label"),
        "capture_mode": result.get("capture_mode"),
        "raw_artifact_sha256": result.get("raw_artifact_sha256"),
    }
    for key, value in expected.items():
        observed = observation.get(key)
        if key == "score_pct":
            try:
                if float(observed) != float(value):
                    return False, "observation score differs from state"
            except (TypeError, ValueError):
                return False, "observation score is invalid"
        elif observed != value:
            return False, f"observation {key} differs from state"
    return True, "current challenge-bound observation"


def detector_targets(st: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """Return [(target, digest)] and policy problems."""
    if st["route"] != "longform":
        return [("DOCUMENT", working_sha(st))], []
    segment_path = Path(st["files"]["segments"])
    if not segment_path.is_file():
        return [], [f"segment map missing: {segment_path}"]
    try:
        data = V.load_json(segment_path)
    except (ValueError, json.JSONDecodeError) as exc:
        return [], [f"invalid segment map: {exc}"]
    if data.get("schema") != "palimpsest.segments.v3":
        return [], ["segment map schema is not v3"]
    if data.get("file_sha256") != working_sha(st):
        return [], ["segment map is stale; run segment.py sync"]
    segments = data.get("segments", [])
    coverage = st["detector_policy"]["coverage"]
    if coverage == "full":
        selected = segments
    else:
        requested = set(st["detector_policy"].get("sample_ids", []))
        requested.update(
            x["id"] for x in segments
            if x.get("risk") or x.get("changed") or x.get("status") == "edited"
        )
        if not requested:
            return [], ["risk_sampled coverage has no sample_ids and no risk/edited segments"]
        missing = requested - {x["id"] for x in segments}
        if missing:
            return [], [f"sample_ids absent from map: {', '.join(sorted(missing))}"]
        selected = [x for x in segments if x["id"] in requested]
    return [(x["id"], x["current_sha256"]) for x in selected], []


def detector_gate(st: dict) -> dict:
    if not st["flags"]["F1"]:
        return gate("na", "F1 not selected")
    selected = st["detector_policy"]["selected_services"]
    if "zerogpt" not in selected:
        return gate("red", "ZeroGPT is missing from selected services")
    cap_ok, cap_msg = artifact_health(st, "capability_review")
    if not cap_ok:
        return gate("red", cap_msg)
    cap_path = Path(st["artifacts"]["capability_review"]["path"])
    cap = V.load_json(cap_path)
    refresh_days = registry().get("refresh_after_days", 30)
    problems: list[str] = []
    limits: list[str] = []
    target_notes: list[str] = []
    now_dt = datetime.now(timezone.utc)
    for service in selected:
        observation = cap["services"][service]["observation"]
        try:
            checked = V.parse_iso(observation["checked_at"])
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
            if (now_dt - checked.astimezone(timezone.utc)).days > refresh_days:
                problems.append(f"{service}: capability review older than {refresh_days} days")
        except (ValueError, TypeError):
            problems.append(f"{service}: invalid capability checked_at")

    targets, target_problems = detector_targets(st)
    problems.extend(target_problems)
    threshold = st["detector_policy"]["threshold_pct"]
    minimum = st["detector_policy"]["minimum_independent"]
    for target, digest in targets:
        independent_groups: set[str] = set()
        plateau_services: set[str] = set()
        for service in selected:
            observation = cap["services"][service]["observation"]
            waiver = current_waiver(st, service, target, digest)
            if waiver:
                if st["detector_policy"].get("score_mandatory"):
                    problems.append(
                        f"{service}/{target}: local waiver cannot satisfy score_mandatory"
                    )
                else:
                    limits.append(f"{service}/{target}: waived ({waiver['code']})")
                continue
            if observation.get("status") != "confirmed":
                problems.append(f"{service}/{target}: capability not confirmed and no scoped waiver")
                continue
            result = latest_current_result(st, service, target, digest)
            if not result:
                stale = any(
                    x.get("service") == service and x.get("target") == target
                    for x in st.get("detector_results", [])
                )
                problems.append(
                    f"{service}/{target}: {'only stale results' if stale else 'no current result'}"
                )
                continue
            integrity_ok, integrity_message = detector_result_integrity(result)
            if not integrity_ok:
                problems.append(f"{service}/{target}: {integrity_message}")
                continue
            if result["score_pct"] >= threshold:
                plateau = current_plateau(st, service, target, digest)
                if plateau:
                    plateau_services.add(service)
                    problems.append(
                        f"{service}/{target}: validated plateau is still a blocker "
                        f"({result['score_pct']:g}% >= strict {threshold:g}% limit)"
                    )
                else:
                    problems.append(
                        f"{service}/{target}: {result['score_pct']:g}% is not strictly "
                        f"below {threshold:g}%"
                    )
                continue
            soft_target = float(
                st["detector_policy"].get(
                    "soft_target_pct", SOFT_DETECTOR_TARGET_EXCLUSIVE
                )
            )
            if result["score_pct"] >= soft_target:
                target_notes.append(
                    f"{service}/{target}: hard pass {result['score_pct']:g}%, "
                    f"soft target <{soft_target:g}% not reached"
                )
            group = result.get("independence_group", "")
            if (
                result.get("kind") in {"direct", "institutional"}
                and not group.startswith("aggregator:")
            ):
                independent_groups.add(group)
        if len(independent_groups) < minimum:
            problems.append(
                f"{target}: only {len(independent_groups)} independent passing groups; "
                f"need {minimum}"
            )
    if st["detector_policy"]["coverage"] == "risk_sampled":
        if st["detector_policy"].get("score_mandatory"):
            problems.append(
                "score_mandatory requires full text coverage; risk_sampled cannot pass"
            )
        else:
            limits.append("long-form detector evidence covers an accepted risk sample, not the full text")
    registry_minimum = int(registry()["policy"]["minimum_independent_services"])
    if st["detector_policy"]["minimum_independent"] < registry_minimum:
        limits.append(
            "independent-service minimum was lowered below the registry default "
            f"({st['detector_policy']['minimum_independent']} < {registry_minimum}); "
            "local user words are not authenticated consent"
        )
    if st["detector_policy"].get("language_validation") == "provisional":
        limits.append(
            f"{st['language']} detector core is provisional; no full release corpus is recorded"
        )
    round_ok, round_msg = artifact_health(st, "detector_round")
    if not round_ok:
        problems.append(round_msg)
    else:
        round_record = st["artifacts"]["detector_round"]
        round_data = V.load_json(round_record["path"])
        if round_data.get("round_status") != "pass":
            problems.append(
                "current detector round still requires edits; plateau/diagnosis is not success"
            )
        final_stage_kinds = [
            kind
            for kind, enabled in (
                ("structure_review", st["flags"]["F2"]),
                ("claim_ledger", st["flags"]["F3"]),
                ("overlap_report", st["flags"]["F4"]),
                ("plagiarism_review", st["flags"]["F4"]),
            )
            if enabled and kind in st.get("artifacts", {})
        ]
        try:
            round_time = V.parse_iso(round_record["registered_at"])
            later = [
                kind
                for kind in final_stage_kinds
                if V.parse_iso(st["artifacts"][kind]["registered_at"]) > round_time
            ]
        except (ValueError, TypeError, KeyError):
            later = ["invalid artifact timestamp"]
        if later:
            problems.append(
                "final full detector round must be registered after F2/F3/F4 "
                f"artifacts: {', '.join(later)}"
            )
    if problems:
        return gate(
            "red",
            "score_mandatory detector contract is incomplete or failing",
            problems + limits + target_notes,
        )
    if limits:
        return gate(
            "yellow",
            "hard detector threshold passed with explicit non-score limitations",
            limits + target_notes,
        )
    return gate(
        "green",
        f"{len(targets)} target(s), {len(selected)} mandatory service(s), "
        f"every score strictly below {threshold:g}%",
        target_notes,
    )


def run_json(command: list[str]) -> tuple[dict | None, int, str]:
    proc = subprocess.run(command, capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, proc.returncode, (proc.stderr or proc.stdout).strip()
    return payload, proc.returncode, proc.stderr.strip()


def assess_style_metric(st: dict, payload: dict | None) -> tuple[bool, list[str]]:
    """Apply only thresholds the metric can support; keep short-text limits explicit."""
    if not payload:
        return False, ["style-distance payload is unavailable"]
    reliability = str(payload.get("reliability", ""))
    if reliability != "ok":
        return True, [
            "short-text style distance is advisory only; no numeric match is claimed",
            reliability or "reliability was not reported",
        ]
    distance = float(payload.get("distance", 101))
    mode = st.get("style_mode")
    if mode == "source_as_reference":
        ok = distance <= 28.0
        return ok, [
            f"reliable source-baseline distance {distance:g}/100 "
            f"({'within' if ok else 'above'} the 28-point preservation ceiling)"
        ]
    if mode == "external_reference":
        improvement = float(payload.get("improvement", -101))
        ok = distance <= 45.0 and improvement >= 0.0
        return ok, [
            f"reliable external-reference distance {distance:g}/100 (ceiling 45)",
            f"baseline improvement {improvement:+g} (must not be negative)",
        ]
    return False, ["style baseline is not selected"]


def machine_checks(st: dict, state_file: Path) -> dict:
    verification_dir = state_file.parent / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    fidelity_out = verification_dir / "fidelity.json"
    fidelity, fidelity_rc, fidelity_err = run_json(
        [
            sys.executable, str(SCRIPTS / "fidelity_check.py"),
            "--original", st["files"]["original"],
            "--edited", st["files"]["working"],
            "--json",
        ]
    )
    if fidelity is not None:
        V.atomic_write_json(fidelity_out, fidelity)
    minimality, minimality_rc, minimality_err = run_json(
        [
            sys.executable, str(SCRIPTS / "minimality.py"),
            "--original", st["files"]["original"],
            "--current", st["files"]["working"],
            "--budget", str(st["budgets"]["document_change_ratio"]),
            "--para-budget", str(st["budgets"]["paragraph_change_ratio"]),
            "--json",
        ]
    )
    patterns, patterns_rc, patterns_err = run_json(
        [
            sys.executable, str(SCRIPTS / "pattern_scan.py"),
            st["files"]["working"],
            "--json",
        ]
    )
    style = None
    style_rc = 0
    style_err = ""
    style_mode = st.get("style_mode", "unselected")
    style_command: list[str] | None = None
    if style_mode == "external_reference" and st["files"].get("references"):
        style_command = [
            sys.executable, str(SCRIPTS / "style_distance.py"),
            "--ref", *st["files"]["references"],
            "--cand", st["files"]["working"],
            "--baseline", st["files"]["original"],
            "--json",
        ]
    elif style_mode == "source_as_reference":
        style_command = [
            sys.executable, str(SCRIPTS / "style_distance.py"),
            "--ref", st["files"]["original"],
            "--cand", st["files"]["working"],
            "--json",
        ]
    if style_command:
        style, style_rc, style_err = run_json(
            style_command
        )
    style_policy_ok, style_policy_details = assess_style_metric(st, style)
    english_level = None
    english_level_rc = 0
    english_level_err = ""
    if st["language"] == "en" and st.get("english_level", {}).get("target") not in {
        None, "", "unselected", "not_applicable"
    }:
        english_level, english_level_rc, english_level_err = run_json(
            [
                sys.executable, str(SCRIPTS / "english_level.py"),
                "--original", st["files"]["original"],
                "--edited", st["files"]["working"],
                "--target", st["english_level"]["target"],
                "--json",
            ]
        )
    working_text = V.read_text(st["files"]["working"])
    annotations_clean = "⟦" not in working_text and "⟧" not in working_text
    return {
        "fidelity": {
            "ok": bool(fidelity and fidelity.get("ok") and fidelity_rc == 0),
            "returncode": fidelity_rc,
            "error": fidelity_err,
            "report": str(fidelity_out) if fidelity is not None else "",
            "payload": fidelity,
        },
        "minimality": {
            "ok": minimality_rc == 0 and minimality is not None,
            "returncode": minimality_rc,
            "error": minimality_err,
            "payload": minimality,
        },
        "pattern_scan": {
            "ok": patterns_rc == 0 and patterns is not None,
            "returncode": patterns_rc,
            "error": patterns_err,
            "payload": patterns,
            "advisory": True,
        },
        "style_distance": {
            "ok": style_command is not None and style_rc == 0 and style is not None,
            "policy_ok": style_policy_ok,
            "policy_details": style_policy_details,
            "returncode": style_rc,
            "error": style_err,
            "payload": style,
            "advisory_when_low_reliability": True,
        },
        "english_level": {
            "ok": (
                st["language"] != "en"
                or (
                    english_level is not None
                    and english_level_rc == 0
                    and english_level.get("ok") is True
                )
            ),
            "returncode": english_level_rc,
            "error": english_level_err,
            "payload": english_level,
            "screen_only": True,
        },
        "annotations_clean": annotations_clean,
    }


def verify_state(st: dict, state_file: Path) -> dict:
    checks = machine_checks(st, state_file)
    gates: dict[str, dict] = {}
    intake_missing = [key for key, item in st["intake"].items() if not item.get("answer")]
    master_ok, master_msg = artifact_health(st, "master_brief")
    source_text = V.read_text(st["files"]["original"])
    detected_language = infer_language(source_text)
    language_ok = (
        st.get("language") == detected_language
        and st.get("source_language", {}).get("detected") == detected_language
    )
    original_ok = (
        st.get("files", {}).get("original_sha256_at_init") == original_sha(st)
    )
    if intake_missing or not master_ok or not language_ok or not original_ok:
        details = (
            ([f"missing intake: {', '.join(intake_missing)}"] if intake_missing else [])
            + [master_msg]
            + [
                (
                    f"source language binding: stored={st.get('language')} "
                    f"detected={detected_language}"
                ),
                f"original immutable digest: {'pass' if original_ok else 'changed after init'}",
            ]
        )
        gates["G0"] = gate("red", "intake/master brief incomplete", details)
    else:
        gates["G0"] = gate(
            "green",
            master_msg,
            [
                f"source language bound to detected {detected_language}",
                "original SHA-256 still matches init",
            ],
        )

    diag_ok, diag_msg = artifact_health(st, "diagnosis")
    pattern_ok = checks["pattern_scan"]["ok"]
    pattern_payload = checks["pattern_scan"].get("payload") or {}
    pattern_counts = pattern_payload.get("counts", {})
    gates["G1"] = gate(
        "green" if diag_ok and pattern_ok else "red",
        diag_msg,
        [
            f"pattern scan executed: {pattern_ok}",
            (
                "advisory pattern counts: "
                f"P0={pattern_counts.get('P0', 0)}, "
                f"P1={pattern_counts.get('P1', 0)}, "
                f"P2={pattern_counts.get('P2', 0)}"
            ),
        ],
    )

    if st.get("style_mode") == "external_reference":
        ductus_ok, ductus_msg = artifact_health(st, "ductus")
        gates["G2"] = gate("green" if ductus_ok else "red", ductus_msg)
    elif st.get("style_mode") == "source_as_reference":
        gates["G2"] = gate(
            "green",
            "source_as_reference: the original text is the active style baseline",
            [
                "external-reference transfer is disabled",
                "minimum necessary edits and source-voice preservation remain mandatory",
            ],
        )
    else:
        gates["G2"] = gate("red", "style baseline was not selected in Q1")

    gates["G3"] = detector_gate(st)

    if st["flags"]["F2"]:
        ok, msg = artifact_health(st, "structure_review")
        gates["G4"] = gate("green" if ok else "red", msg)
    else:
        gates["G4"] = gate("na", "F2 not selected")

    if st["flags"]["F3"]:
        ok, msg = artifact_health(st, "claim_ledger")
        gates["G5"] = gate("green" if ok else "red", msg)
    else:
        gates["G5"] = gate("na", "F3 not selected")

    if st["flags"]["F4"]:
        overlap_ok, overlap_msg = artifact_health(st, "overlap_report")
        plag_ok, plag_msg = artifact_health(st, "plagiarism_review")
        ok = overlap_ok and plag_ok
        gates["G6"] = gate("green" if ok else "red", f"{overlap_msg}; {plag_msg}")
    else:
        gates["G6"] = gate("na", "F4 not selected")

    semantic_ok, semantic_msg = artifact_health(st, "semantic_review")
    authorized_units = semantic_authorization_units(st) if semantic_ok else []
    fidelity_ok = checks["fidelity"]["ok"]
    minimality_ok = checks["minimality"]["ok"]
    details = [
        f"fidelity machine screen: {'pass' if fidelity_ok else 'fail'}",
        f"edit budget: {'pass' if minimality_ok else 'fail'}",
        semantic_msg,
    ]
    if authorized_units:
        details.append(
            "externally authorized replacements are declared but cannot be "
            "authenticated by the local CLI: " + ", ".join(authorized_units)
        )
    g7_color = (
        "red"
        if not (fidelity_ok and minimality_ok and semantic_ok)
        else ("yellow" if authorized_units else "green")
    )
    gates["G7"] = gate(
        g7_color,
        "machine screen + structured human semantic reconciliation",
        details,
    )

    if st.get("style_mode") in {"external_reference", "source_as_reference"}:
        style_ok, style_msg = artifact_health(st, "style_review")
        metric_executed = checks["style_distance"]["ok"]
        metric_policy_ok = checks["style_distance"]["policy_ok"]
        metric_ok = metric_executed and metric_policy_ok
        english_ok = checks["english_level"]["ok"]
        payload = checks["style_distance"].get("payload") or {}
        level_payload = checks["english_level"].get("payload") or {}
        gates["G8"] = gate(
            "green" if style_ok and metric_ok and english_ok else "red",
            style_msg,
            [
                f"style baseline: {st['style_mode']}",
                f"style distance executed: {metric_executed}",
                f"style metric policy passed: {metric_policy_ok}",
                f"distance: {payload.get('distance', 'unavailable')}",
                *checks["style_distance"].get("policy_details", []),
                (
                    "English-level screen: "
                    + (
                        f"{level_payload.get('source', {}).get('estimated_cefr')} -> "
                        f"{level_payload.get('edited', {}).get('estimated_cefr')} "
                        f"(target {level_payload.get('target_cefr')})"
                        if st["language"] == "en"
                        else "not applicable"
                    )
                ),
                f"English-level screen passed: {english_ok}",
                "distance is never a semantic or authorship verdict",
                "CEFR screen is approximate; structured style review remains required",
            ],
        )
    else:
        gates["G8"] = gate("red", "style baseline was not selected in Q1")

    constraints_ok, constraints_msg = artifact_health(st, "constraints_review")
    proof_ok, proof_msg = artifact_health(st, "proofread")
    clean = checks["annotations_clean"]
    g9_ok = constraints_ok and proof_ok and clean
    gates["G9"] = gate(
        "green" if g9_ok else "red",
        "delivery cleanliness",
        [constraints_msg, proof_msg, f"annotations clean: {clean}"],
    )

    report_ok, report_msg = artifact_health(st, "report")
    gates["G10"] = gate("green" if report_ok else "red", report_msg)

    for gate_id, info in gates.items():
        info["description"] = GATE_DESCRIPTIONS[gate_id]
    return {
        "ran_at": V.now(),
        "working_sha256": working_sha(st),
        "gates": gates,
        "machine_checks": checks,
    }


def status_counts(verification: dict) -> tuple[list[str], list[str]]:
    red = [g for g, info in verification["gates"].items() if info["color"] == "red"]
    yellow = [g for g, info in verification["gates"].items() if info["color"] == "yellow"]
    return red, yellow


def print_verification(st: dict) -> None:
    verification = st.get("verification", {})
    print(f"TASK: {st['task']}  STATUS: {st['status']}  route={st['route']} language={st['language']}")
    current = working_sha(st)
    if st.get("close_digest") and st["close_digest"] != current:
        print("WARNING: working text changed after closure; run verify (it will reopen the task).")
    print(f"working sha256: {current}")
    print("GATES:")
    for gate_id in sorted(verification.get("gates", {})):
        info = verification["gates"][gate_id]
        mark = {"green": "OK", "yellow": "LIMIT", "red": "BLOCK", "na": "n/a"}[info["color"]]
        print(f"  [{mark:5}] {gate_id} {info['description']}: {info['evidence']}")
        for detail in info.get("details", []):
            print(f"          - {detail}")


def cmd_verify(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    try:
        with V.locked_json(path) as st:
            if st.get("schema") != STATE_SCHEMA:
                raise StateError("not a Palimpsest v3 state")
            current = working_sha(st)
            closed_stale = (
                st["status"] == "CLOSED"
                and st.get("close_digest") != current
            )
            pending_stale = (
                st["status"] == "READY_WITH_LIMITS"
                and st.get("pending_limitations", {}).get("working_sha256") != current
            )
            if closed_stale or pending_stale:
                st["status"] = "OPEN"
                st["closed_at"] = ""
                st["close_digest"] = ""
                st.pop("pending_limitations", None)
                add_event(st, "automatic_reopen", reason="working digest changed")
            st["verification"] = verify_state(st, path)
            add_event(st, "verify")
            red, yellow = status_counts(st["verification"])
            result_code = 1 if red else 0
            if args.json:
                print(json.dumps(st["verification"], ensure_ascii=False, indent=2))
            else:
                print_verification(st)
                print(f"RESULT: {len(red)} blocker(s), {len(yellow)} limitation gate(s)")
    except (FileNotFoundError, StateError, KeyError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    return result_code


def cmd_show(args: argparse.Namespace) -> int:
    try:
        st = load_state(state_path(args.state))
    except StateError as exc:
        return fail(str(exc))
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
    else:
        print_verification(st)
        print(f"detector results: {len(st.get('detector_results', []))}")
        print(f"scoped waivers: {len(st.get('waivers', []))}")
        print(f"registered artifacts: {', '.join(sorted(st.get('artifacts', {}))) or 'none'}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    pending_yellow: list[str] = []
    try:
        with V.locked_json(path) as st:
            if st.get("schema") != STATE_SCHEMA:
                raise StateError("not a Palimpsest v3.5 state")
            st["verification"] = verify_state(st, path)
            red, yellow = status_counts(st["verification"])
            if red:
                raise StateError(f"cannot close: blocker gates {', '.join(red)}")
            if yellow:
                # A local process can invent quotes, message references, files, and
                # nonces.  It therefore cannot authenticate user consent.  Keep a
                # machine-readable handoff state, but never turn yellow green/closed
                # through CLI arguments.
                pending_yellow = yellow
                st["status"] = "READY_WITH_LIMITS"
                st["pending_limitations"] = {
                    "gates": yellow,
                    "working_sha256": working_sha(st),
                    "prepared_at": V.now(),
                    "trust_boundary": (
                        "requires an explicit user turn or host-signed consent "
                        "outside this locally writable workspace"
                    ),
                }
                st["closed_at"] = ""
                st["close_digest"] = ""
                add_event(st, "ready_with_limits", gates=yellow)
            else:
                st["status"] = "CLOSED"
                st.pop("pending_limitations", None)
                st["closed_at"] = V.now()
                st["close_digest"] = working_sha(st)
                add_event(st, "close", status=st["status"])
            final_status = st["status"]
    except (FileNotFoundError, StateError, KeyError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    if pending_yellow:
        return fail(
            "cannot close yellow limitation gates from local CLI: "
            f"{', '.join(pending_yellow)}; status is READY_WITH_LIMITS and "
            "external user confirmation is required",
            code=1,
        )
    print(f"project {final_status}: digest {V.load_json(path)['close_digest']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create v3.5 state")
    p.add_argument("--original", required=True)
    p.add_argument("--working", required=True)
    p.add_argument("--flags", default="F1,F2")
    p.add_argument("--ref", action="append")
    p.add_argument("--task")
    p.add_argument("--route", choices=["auto", "surgical", "standard", "longform"], default="auto")
    p.add_argument(
        "--language",
        choices=["en", "ru"],
        help="optional assertion only; must match deterministic source detection",
    )
    p.add_argument("--services")
    p.add_argument("--coverage", choices=["full", "risk_sampled"], default="full")
    p.add_argument("--sample-ids", default="")
    p.add_argument("--user-quote")
    p.add_argument("--detector-max", type=float, default=20.0)
    p.add_argument("--min-independent", type=int, default=2)
    p.add_argument("--budget", type=float)
    p.add_argument("--para-budget", type=float)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("intake", help="record one of the four sequential intake answers")
    p.add_argument("--question", choices=["Q1", "Q2", "Q3", "Q4"], required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--source", choices=["explicit", "inferred_from_user_message"], default="explicit")
    p.add_argument(
        "--style-mode",
        choices=["external_reference", "source_as_reference"],
        help="required for Q1",
    )
    p.add_argument(
        "--english-level",
        choices=[
            "infer_from_source", "A1", "A2", "B1", "B2", "C1", "C2",
            "a1", "a2", "b1", "b2", "c1", "c2", "native", "not_applicable",
        ],
        help="required for Q1 on English projects",
    )
    p.add_argument("--ref", action="append", help="external style reference file for Q1")
    p.add_argument("--functions", help="comma-separated F1..F4 or none; required for Q2")
    p.add_argument(
        "--services",
        help="comma-separated enabled detector IDs or none; required for Q3",
    )
    p.set_defaults(func=cmd_intake)

    artifact_choices = list(ATTESTATIONS) + [
        "capability_review", "detector_round", "overlap_report", "report"
    ]
    p = sub.add_parser("template", help="create a digest-bound evidence template")
    p.add_argument(
        "--kind",
        choices=list(ATTESTATIONS) + ["capability_review", "detector_round", "report"],
        required=True,
    )
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_template)

    p = sub.add_parser("artifact", help="validate and register an evidence artifact")
    p.add_argument("--kind", choices=artifact_choices, required=True)
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_artifact)

    p = sub.add_parser(
        "detector-prepare",
        help="issue a one-use challenge for a detector observation",
    )
    p.add_argument("--service", required=True)
    p.add_argument("--target", default="DOCUMENT")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_detector_prepare)

    p = sub.add_parser(
        "detector",
        help="record a challenge-bound detector observation package",
    )
    p.add_argument("--observation", required=True)
    p.set_defaults(func=cmd_detector)

    p = sub.add_parser(
        "plateau-template",
        help="create a formal plateau bundle template for one selected service",
    )
    p.add_argument("--service", required=True)
    p.add_argument("--target", default="DOCUMENT")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_plateau_template)

    p = sub.add_parser(
        "plateau",
        help="register three current, fidelity-safe, challenge-bound plateau candidates",
    )
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_plateau)

    p = sub.add_parser("waive", help="waive exactly one service/target/current digest")
    p.add_argument("--service", required=True)
    p.add_argument("--target", default="DOCUMENT")
    p.add_argument("--code", choices=["unavailable", "unsupported", "quality_stop", "user_choice"], required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--user-quote", required=True)
    p.set_defaults(func=cmd_waive)

    p = sub.add_parser("detector-policy", help="change selected detector policy")
    p.add_argument("--services")
    p.add_argument("--threshold", type=float)
    p.add_argument("--min-independent", type=int)
    p.add_argument("--coverage", choices=["full", "risk_sampled"])
    p.add_argument("--sample-ids")
    p.add_argument("--user-quote")
    p.set_defaults(func=cmd_detector_policy)

    p = sub.add_parser("move", help="record a hypothesis-driven edit")
    p.add_argument("--id", required=True)
    p.add_argument("--span", required=True)
    p.add_argument("--mechanism", choices=sorted(PLATEAU_MECHANISMS))
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--outcome")
    p.set_defaults(func=cmd_move)

    p = sub.add_parser("park", help="park an unresolved issue")
    p.add_argument("--id", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--revisit-after")
    p.set_defaults(func=cmd_park)

    p = sub.add_parser("verify", help="recompute all gates")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("show", help="show current state")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("close", help="close only when current evidence permits it")
    p.set_defaults(func=cmd_close)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
