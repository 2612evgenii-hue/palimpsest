#!/usr/bin/env python3
"""Create and validate privacy-first detector shadow cases from real work."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402
import minimality  # noqa: E402
import research_variants  # noqa: E402


SCHEMA = "palimpsest.shadow-case.v1"
OBSERVATION_SCHEMA = "palimpsest.shadow-observation.v1"
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "assets/service-registry.json"
ALLOWED_TRANSITIONS = {
    "first_scan_no_prior_result",
    "loading_or_disabled_observed",
    "result_identifier_changed",
    "result_text_changed",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def summary_digest(summary: dict) -> str:
    return canonical_digest(
        {key: value for key, value in summary.items() if key != "lifecycle"}
    )


def registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def relative_path(path: Path, root: Path) -> str:
    return os.path.relpath(path.resolve(), root.resolve())


def resolve_case_file(case_path: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("case file path is required")
    return (case_path.parent / relative).resolve()


def plan_payload(data: dict) -> dict:
    return {
        "schema": data.get("schema"),
        "case_id": data.get("case_id"),
        "privacy": data.get("privacy"),
        "context": data.get("context"),
        "registry": data.get("registry"),
        "original": data.get("original"),
        "policy": data.get("policy"),
        "candidates": data.get("candidates"),
    }


def validate_privacy(data: dict) -> None:
    privacy = data.get("privacy")
    if not isinstance(privacy, dict):
        raise ValueError("shadow case needs a privacy policy")
    mode = privacy.get("mode")
    if mode not in {"delivery_only", "private_research"}:
        raise ValueError("privacy.mode must be delivery_only or private_research")
    if privacy.get("raw_text_retention") != "local_only_never_commit":
        raise ValueError("raw text must stay local and must never be committed")
    if privacy.get("public_export_allowed") is not False:
        raise ValueError("shadow-case raw records cannot be public exports")
    authorized = privacy.get("research_reuse_authorized")
    if mode == "delivery_only":
        if authorized is not False or privacy.get("consent") is not None:
            raise ValueError("delivery_only cannot authorize research reuse")
    else:
        consent = privacy.get("consent")
        if authorized is not True or not isinstance(consent, dict):
            raise ValueError("private_research requires explicit consent metadata")
        if (
            consent.get("source") != "user_message"
            or not isinstance(consent.get("quote_sha256"), str)
            or len(consent["quote_sha256"]) != 64
        ):
            raise ValueError("private_research consent metadata is incomplete")


def validate_plan(case_path: Path, data: dict, *, require_frozen: bool) -> dict:
    if data.get("schema") != SCHEMA:
        raise ValueError("unsupported shadow-case schema")
    if not isinstance(data.get("case_id"), str) or len(data["case_id"]) < 8:
        raise ValueError("shadow case needs a non-identifying case_id")
    validate_privacy(data)

    context = data.get("context")
    if not isinstance(context, dict):
        raise ValueError("shadow case needs context")
    language = context.get("language")
    if language not in {"en", "ru"}:
        raise ValueError("shadow case language must be en or ru")
    if not isinstance(context.get("genre"), str) or not context["genre"].strip():
        raise ValueError("shadow case genre is required")
    if language == "en" and context.get("english_level") not in {
        "A1",
        "A2",
        "B1",
        "B2",
        "C1",
        "C2",
        "native",
        "infer_from_source",
    }:
        raise ValueError("shadow case English level is invalid")
    if language == "ru" and context.get("english_level") != "not_applicable":
        raise ValueError("Russian shadow case must use not_applicable English level")

    reg = registry()
    binding = data.get("registry")
    if binding != {
        "schema": reg["schema"],
        "sha256": file_sha256(REGISTRY_PATH),
        "reviewed_at": reg["reviewed_at"],
    }:
        raise ValueError("shadow case registry binding is stale or forged")

    policy = data.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("shadow case needs a detector policy")
    services = policy.get("mandatory_services")
    if (
        not isinstance(services, list)
        or len(services) < 1
        or len(set(services)) != len(services)
        or "zerogpt" not in services
    ):
        raise ValueError("shadow case needs unique services including ZeroGPT")
    for service in services:
        facts = reg["services"].get(service)
        if not facts:
            raise ValueError(f"unknown shadow service: {service}")
        supported = facts.get("languages", [])
        if "*" not in supported and language not in supported:
            raise ValueError(f"{service} does not support shadow language {language}")
    if policy.get("hard_threshold_pct") != 20:
        raise ValueError("shadow hard threshold must remain 20")
    minimum_repeats = policy.get("minimum_repeats")
    tier = policy.get("evidence_tier")
    if tier == "delivery_diagnostic" and minimum_repeats != 1:
        raise ValueError("delivery_diagnostic uses one required observation")
    if tier == "research_candidate" and (
        minimum_repeats != 3
        or data["privacy"]["research_reuse_authorized"] is not True
    ):
        raise ValueError("research_candidate needs consent and three repeats")
    if tier not in {"delivery_diagnostic", "research_candidate"}:
        raise ValueError("unsupported shadow evidence tier")
    if tier == "research_candidate":
        independent_groups = {
            reg["services"][service]["independence_group"]
            for service in services
            if reg["services"][service]["kind"] in {"direct", "institutional"}
            and not reg["services"][service]["independence_group"].startswith(
                "aggregator:"
            )
        }
        if len(independent_groups) < reg["policy"]["minimum_independent_services"]:
            raise ValueError(
                "research_candidate needs two independent detector groups"
            )

    original = data.get("original")
    if not isinstance(original, dict):
        raise ValueError("shadow original binding is missing")
    original_path = resolve_case_file(case_path, original.get("path"))
    if (
        not original_path.is_file()
        or file_sha256(original_path) != original.get("sha256")
    ):
        raise ValueError("shadow original hash mismatch")

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("shadow case needs at least the baseline candidate")
    ids: set[str] = set()
    hashes: dict[str, str] = {}
    for index, candidate in enumerate(candidates):
        candidate_id = candidate.get("id")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or candidate_id in ids
        ):
            raise ValueError("shadow candidate ids must be unique")
        ids.add(candidate_id)
        candidate_path = resolve_case_file(case_path, candidate.get("path"))
        if (
            not candidate_path.is_file()
            or file_sha256(candidate_path) != candidate.get("sha256")
        ):
            raise ValueError(f"shadow candidate hash mismatch: {candidate_id}")
        hashes[candidate_id] = candidate["sha256"]
        quality = candidate.get("quality")
        if not isinstance(quality, dict) or quality.get("status") not in {
            "pass",
            "rejected",
        }:
            raise ValueError(f"shadow candidate quality is missing: {candidate_id}")
        for field in (
            "fidelity_evidence",
            "style_evidence",
            "english_level_evidence",
        ):
            if len(str(quality.get(field, "")).strip()) < 20:
                raise ValueError(
                    f"shadow candidate needs specific {field}: {candidate_id}"
                )
        if index == 0:
            if (
                candidate_id != "baseline"
                or candidate["sha256"] != original["sha256"]
                or candidate.get("hypothesis_id") != "none_original_baseline"
            ):
                raise ValueError("first shadow candidate must bind the original baseline")
        elif (
            not isinstance(candidate.get("hypothesis_id"), str)
            or len(candidate["hypothesis_id"]) < 4
            or len(str(candidate.get("operation_summary", "")).strip()) < 20
        ):
            raise ValueError(f"shadow edit plan is underspecified: {candidate_id}")

    frozen = data.get("freeze")
    if require_frozen:
        if (
            not isinstance(frozen, dict)
            or frozen.get("plan_digest") != canonical_digest(plan_payload(data))
            or not isinstance(frozen.get("frozen_at"), str)
        ):
            raise ValueError("shadow candidate plan is not digest-frozen")
        if data.get("status") not in {
            "frozen_before_scores",
            "observing",
            "completed",
            "stopped",
        }:
            raise ValueError("shadow case has an invalid frozen lifecycle state")
        if data["status"] == "frozen_before_scores" and data.get("observations"):
            raise ValueError("frozen_before_scores cannot already contain observations")
        if data["status"] == "observing" and not data.get("observations"):
            raise ValueError("observing shadow case has no observations")
        seal = data.get("seal")
        if data["status"] in {"frozen_before_scores", "observing"}:
            if seal not in (None, {}):
                raise ValueError("open shadow case has unexpected seal metadata")
        elif (
            not isinstance(seal, dict)
            or seal.get("outcome") != data["status"]
            or seal.get("observations_digest")
            != canonical_digest(data.get("observations"))
            or not isinstance(seal.get("summary_digest"), str)
            or len(seal["summary_digest"]) != 64
            or not isinstance(seal.get("sealed_at"), str)
            or (
                data["status"] == "stopped"
                and len(str(seal.get("reason", "")).strip()) < 20
            )
        ):
            raise ValueError("shadow terminal seal is missing or stale")
        if data["status"] in {"completed", "stopped"}:
            try:
                frozen_time = datetime.fromisoformat(
                    frozen["frozen_at"].replace("Z", "+00:00")
                )
                sealed_time = datetime.fromisoformat(
                    seal["sealed_at"].replace("Z", "+00:00")
                )
                observation_times = [
                    datetime.fromisoformat(
                        row["observed_at"].replace("Z", "+00:00")
                    )
                    for row in data.get("observations", [])
                ]
                if (
                    frozen_time.tzinfo is None
                    or sealed_time.tzinfo is None
                    or sealed_time < frozen_time
                    or any(
                        observed.tzinfo is None or sealed_time < observed
                        for observed in observation_times
                    )
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("shadow terminal seal time is invalid") from exc
    elif frozen not in (None, {}):
        raise ValueError("unfrozen shadow draft has unexpected freeze metadata")
    return {"hashes": hashes, "services": services}


def validate_observations(case_path: Path, data: dict, scope: dict) -> None:
    observations = data.get("observations")
    if not isinstance(observations, list):
        raise ValueError("shadow observations must be a list")
    keys: set[tuple[str, str, int]] = set()
    frozen_at = datetime.fromisoformat(
        data["freeze"]["frozen_at"].replace("Z", "+00:00")
    )
    repeat_limit = data["policy"]["minimum_repeats"]
    reg = registry()
    for observation in observations:
        candidate_id = observation.get("candidate_id")
        service = observation.get("service")
        repeat = observation.get("repeat")
        key = (candidate_id, service, repeat)
        if (
            candidate_id not in scope["hashes"]
            or service not in scope["services"]
            or not isinstance(repeat, int)
            or repeat < 1
            or repeat > repeat_limit
            or key in keys
        ):
            raise ValueError("shadow observation scope or repeat is invalid")
        keys.add(key)
        candidate = next(
            row for row in data["candidates"] if row["id"] == candidate_id
        )
        if candidate["quality"]["status"] != "pass":
            raise ValueError("quality-rejected shadow candidate was scanned")
        expected_sha = scope["hashes"][candidate_id]
        if (
            observation.get("candidate_sha256") != expected_sha
            or observation.get("post_visible_text_sha256") != expected_sha
        ):
            raise ValueError("shadow observation is not bound to candidate text")
        if observation.get("transition_signal") not in ALLOWED_TRANSITIONS:
            raise ValueError("shadow observation lacks a transition signal")
        try:
            parsed = datetime.fromisoformat(
                str(observation.get("observed_at", "")).replace("Z", "+00:00")
            )
            if parsed.tzinfo is None:
                raise ValueError
            if parsed < frozen_at:
                raise ValueError
        except ValueError as exc:
            raise ValueError(
                "shadow observation needs a post-freeze timezone-aware timestamp"
            ) from exc

        result_url = str(observation.get("result_url", ""))
        expected_url = reg["services"][service]["url"]
        observed_host = urlparse(result_url).netloc.casefold()
        expected_host = urlparse(expected_url).netloc.casefold()
        if (
            not result_url.startswith("https://")
            or not observed_host
            or not (
                observed_host == expected_host
                or observed_host.endswith("." + expected_host)
                or expected_host.endswith("." + observed_host)
            )
        ):
            raise ValueError("shadow observation result_url does not match service")

        evidence = observation.get("evidence")
        if (
            not isinstance(evidence, dict)
            or evidence.get("kind")
            not in {"state_detector_observation", "browser_session_record"}
        ):
            raise ValueError("shadow observation needs bound source evidence")
        evidence_path = resolve_case_file(case_path, evidence.get("path"))
        if (
            not evidence_path.is_file()
            or file_sha256(evidence_path) != evidence.get("sha256")
        ):
            raise ValueError("shadow source evidence hash mismatch")

        status = observation.get("status")
        if status == "scored":
            score = observation.get("score_pct")
            if (
                not isinstance(score, (int, float))
                or not 0 <= score <= 100
                or observation.get("terminal_state") != "complete"
            ):
                raise ValueError("scored shadow observation is invalid")
            if len(str(observation.get("visible_result_excerpt", "")).strip()) < 12:
                raise ValueError("scored shadow observation needs a visible excerpt")
        elif status in {"blocked", "error"}:
            if (
                observation.get("score_pct") is not None
                or observation.get("terminal_state") != status
                or len(str(observation.get("visible_terminal_message", ""))) < 20
            ):
                raise ValueError("blocked/error shadow observation is invalid")
        else:
            raise ValueError("unsupported shadow observation status")

        capture_status = observation.get("capture_status")
        if capture_status == "saved":
            capture = observation.get("capture")
            if not isinstance(capture, dict):
                raise ValueError("saved shadow capture metadata is missing")
            capture_path = resolve_case_file(case_path, capture.get("path"))
            if (
                not capture_path.is_file()
                or file_sha256(capture_path) != capture.get("sha256")
            ):
                raise ValueError("shadow capture hash mismatch")
        elif capture_status == "missing":
            if len(str(observation.get("capture_limitation", "")).strip()) < 20:
                raise ValueError("missing shadow capture needs a specific limitation")
        else:
            raise ValueError("shadow observation capture_status is invalid")


def summarize(case_path: Path) -> dict:
    data = json.loads(case_path.read_text(encoding="utf-8"))
    scope = validate_plan(case_path, data, require_frozen=True)
    validate_observations(case_path, data, scope)
    original_path = resolve_case_file(case_path, data["original"]["path"])
    original = T.read_text(original_path)
    minimum_repeats = data["policy"]["minimum_repeats"]
    threshold = data["policy"]["hard_threshold_pct"]
    observed: dict[tuple[str, str], list[float]] = {}
    unavailable: dict[tuple[str, str], list[str]] = {}
    for row in data["observations"]:
        key = (row["candidate_id"], row["service"])
        if row["status"] == "scored":
            observed.setdefault(key, []).append(float(row["score_pct"]))
        else:
            unavailable.setdefault(key, []).append(row["status"])

    rows = []
    for candidate in data["candidates"]:
        current = T.read_text(resolve_case_file(case_path, candidate["path"]))
        token_ratio = minimality.analyze(
            original,
            current,
            1.0,
            1.0,
        )["doc_change_ratio"]
        surface = research_variants.character_change_metrics(original, current)
        edit_cost = max(token_ratio, surface["char_change_ratio"])
        services = {}
        missing = []
        insufficient = {}
        blocked = []
        for service in data["policy"]["mandatory_services"]:
            scores = observed.get((candidate["id"], service), [])
            if unavailable.get((candidate["id"], service)):
                blocked.append(service)
            if not scores:
                missing.append(service)
                continue
            services[service] = {
                "n": len(scores),
                "median": round(float(statistics.median(scores)), 3),
                "range": round(max(scores) - min(scores), 3),
            }
            if len(scores) < minimum_repeats:
                insufficient[service] = {
                    "observed": len(scores),
                    "required": minimum_repeats,
                }
        complete = (
            not missing
            and not blocked
            and not insufficient
            and candidate["quality"]["status"] == "pass"
        )
        worst = max(
            (service["median"] for service in services.values()),
            default=None,
        )
        rows.append(
            {
                "id": candidate["id"],
                "hypothesis_id": candidate["hypothesis_id"],
                "edit_cost": edit_cost,
                **surface,
                "quality_status": candidate["quality"]["status"],
                "services": services,
                "missing": sorted(set(missing)),
                "blocked": sorted(set(blocked)),
                "insufficient_repeats": insufficient,
                "worst_mandatory_score": worst,
                "hard_pass": bool(
                    complete and worst is not None and worst < threshold
                ),
            }
        )

    comparable = [
        row
        for row in rows
        if row["quality_status"] == "pass"
        and not row["missing"]
        and not row["blocked"]
        and not row["insufficient_repeats"]
    ]
    frontier = []
    for row in comparable:
        if not any(
            other["id"] != row["id"]
            and other["edit_cost"] <= row["edit_cost"]
            and other["worst_mandatory_score"] <= row["worst_mandatory_score"]
            and (
                other["edit_cost"] < row["edit_cost"]
                or other["worst_mandatory_score"] < row["worst_mandatory_score"]
            )
            for other in comparable
        ):
            frontier.append(row["id"])
    passing = sorted(
        (row for row in comparable if row["hard_pass"]),
        key=lambda row: (
            row["edit_cost"],
            row["changed_spans"],
            row["worst_mandatory_score"],
            row["id"],
        ),
    )
    quality_pass_ids = {
        candidate["id"]
        for candidate in data["candidates"]
        if candidate["quality"]["status"] == "pass"
    }
    comparable_ids = {row["id"] for row in comparable}
    full_quality_pass_matrix = (
        len(quality_pass_ids) >= 2 and comparable_ids == quality_pass_ids
    )
    result = {
        "case_id": data["case_id"],
        "privacy_mode": data["privacy"]["mode"],
        "evidence_tier": data["policy"]["evidence_tier"],
        "rows": rows,
        "pareto_frontier": sorted(frontier),
        "least_changed_hard_pass": passing[0]["id"] if passing else None,
        "research_admission": {
            "eligible_for_aggregate_review": bool(
                data["privacy"]["research_reuse_authorized"]
                and data["policy"]["evidence_tier"] == "research_candidate"
                and full_quality_pass_matrix
            ),
            "production_rule_admitted": False,
            "reason": "a single real-work case cannot admit a detector recipe",
        },
    }
    if data["status"] in {"completed", "stopped"}:
        if data["seal"]["summary_digest"] != summary_digest(result):
            raise ValueError("shadow sealed summary digest is stale")
    result["lifecycle"] = {
        "status": data["status"],
        "sealed": data["status"] in {"completed", "stopped"},
        "outcome": (
            data["seal"]["outcome"]
            if data["status"] in {"completed", "stopped"}
            else None
        ),
    }
    return result


def init_case(args: argparse.Namespace) -> dict:
    case_path = args.case.resolve()
    if case_path.exists():
        raise ValueError("shadow case already exists")
    original = args.original.resolve()
    if not original.is_file():
        raise ValueError("shadow original does not exist")
    services = [item.strip().lower() for item in args.services.split(",") if item.strip()]
    privacy = {
        "mode": args.privacy_mode,
        "research_reuse_authorized": args.privacy_mode == "private_research",
        "raw_text_retention": "local_only_never_commit",
        "public_export_allowed": False,
        "consent": None,
    }
    if args.privacy_mode == "private_research":
        if not args.consent_quote or len(args.consent_quote.strip()) < 20:
            raise ValueError("private_research needs a specific 20+ character user quote")
        privacy["consent"] = {
            "source": "user_message",
            "quote_sha256": sha256_bytes(args.consent_quote.encode("utf-8")),
        }
    data = {
        "schema": SCHEMA,
        "case_id": args.case_id,
        "status": "draft",
        "created_at": now(),
        "privacy": privacy,
        "context": {
            "language": args.language,
            "genre": args.genre,
            "english_level": (
                args.english_level if args.language == "en" else "not_applicable"
            ),
        },
        "registry": {
            "schema": registry()["schema"],
            "sha256": file_sha256(REGISTRY_PATH),
            "reviewed_at": registry()["reviewed_at"],
        },
        "original": {
            "path": relative_path(original, case_path.parent),
            "sha256": file_sha256(original),
        },
        "policy": {
            "mandatory_services": services,
            "hard_threshold_pct": 20,
            "evidence_tier": args.evidence_tier,
            "minimum_repeats": 3 if args.evidence_tier == "research_candidate" else 1,
        },
        "candidates": [
            {
                "id": "baseline",
                "path": relative_path(original, case_path.parent),
                "sha256": file_sha256(original),
                "hypothesis_id": "none_original_baseline",
                "operation_summary": "Immutable real-work baseline before detector-driven edits.",
                "quality": {
                    "status": "pass",
                    "fidelity_evidence": "Immutable source baseline; no semantic edit was applied.",
                    "style_evidence": "Immutable source baseline defines source-as-reference style.",
                    "english_level_evidence": "Immutable source baseline defines the preserved level.",
                },
            }
        ],
        "freeze": {},
        "seal": {},
        "observations": [],
    }
    validate_plan(case_path, data, require_frozen=False)
    case_path.parent.mkdir(parents=True, exist_ok=True)
    case_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def add_candidate(args: argparse.Namespace) -> dict:
    case_path = args.case.resolve()
    data = json.loads(case_path.read_text(encoding="utf-8"))
    validate_plan(case_path, data, require_frozen=False)
    if data["observations"]:
        raise ValueError("cannot add a candidate after observations")
    candidate_path = args.candidate.resolve()
    data["candidates"].append(
        {
            "id": args.id,
            "path": relative_path(candidate_path, case_path.parent),
            "sha256": file_sha256(candidate_path),
            "hypothesis_id": args.hypothesis_id,
            "operation_summary": args.operation_summary,
            "quality": {
                "status": args.quality_status,
                "fidelity_evidence": args.fidelity_evidence,
                "style_evidence": args.style_evidence,
                "english_level_evidence": args.english_level_evidence,
            },
        }
    )
    validate_plan(case_path, data, require_frozen=False)
    case_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def freeze_case(case_path: Path) -> dict:
    data = json.loads(case_path.read_text(encoding="utf-8"))
    validate_plan(case_path, data, require_frozen=False)
    if len(data["candidates"]) < 2:
        raise ValueError("freeze needs at least one planned edit candidate")
    data["freeze"] = {
        "plan_digest": canonical_digest(plan_payload(data)),
        "frozen_at": now(),
        "rule": "No candidate or hypothesis may be added after detector scores.",
    }
    data["status"] = "frozen_before_scores"
    validate_plan(case_path, data, require_frozen=True)
    case_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def record_observation(case_path: Path, observation_path: Path) -> dict:
    data = json.loads(case_path.read_text(encoding="utf-8"))
    scope = validate_plan(case_path, data, require_frozen=True)
    if data["status"] in {"completed", "stopped"}:
        raise ValueError("cannot record after the shadow case is sealed")
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    if observation.get("schema") != OBSERVATION_SCHEMA:
        raise ValueError("unsupported shadow observation schema")
    stored = {key: value for key, value in observation.items() if key != "schema"}
    candidate_id = stored.get("candidate_id")
    if candidate_id not in scope["hashes"]:
        raise ValueError("shadow observation references unknown candidate")
    if stored.get("candidate_sha256") != scope["hashes"][candidate_id]:
        raise ValueError("shadow observation candidate hash is stale")
    data["observations"].append(stored)
    data["status"] = "observing"
    validate_observations(case_path, data, scope)
    case_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def prepare_observation(args: argparse.Namespace) -> dict:
    case_path = args.case.resolve()
    output = args.out.resolve()
    if output.exists():
        raise ValueError("shadow observation template already exists")
    data = json.loads(case_path.read_text(encoding="utf-8"))
    scope = validate_plan(case_path, data, require_frozen=True)
    if data["status"] in {"completed", "stopped"}:
        raise ValueError("cannot prepare an observation after seal")
    if args.candidate_id not in scope["hashes"]:
        raise ValueError("unknown shadow candidate")
    candidate = next(
        row for row in data["candidates"] if row["id"] == args.candidate_id
    )
    if candidate["quality"]["status"] != "pass":
        raise ValueError("cannot prepare a quality-rejected shadow candidate")
    if args.service not in scope["services"]:
        raise ValueError("service is outside the frozen shadow scope")
    repeat_limit = data["policy"]["minimum_repeats"]
    if not 1 <= args.repeat <= repeat_limit:
        raise ValueError("repeat is outside the frozen shadow policy")
    existing = {
        (row["candidate_id"], row["service"], row["repeat"])
        for row in data["observations"]
    }
    if (args.candidate_id, args.service, args.repeat) in existing:
        raise ValueError("shadow observation cell is already recorded")
    template = {
        "schema": OBSERVATION_SCHEMA,
        "candidate_id": args.candidate_id,
        "service": args.service,
        "repeat": args.repeat,
        "status": "",
        "candidate_sha256": scope["hashes"][args.candidate_id],
        "post_visible_text_sha256": "",
        "score_pct": None,
        "terminal_state": "",
        "transition_signal": "",
        "observed_at": "",
        "result_url": registry()["services"][args.service]["url"],
        "visible_result_excerpt": "",
        "visible_terminal_message": "",
        "evidence": {
            "kind": "",
            "path": "",
            "sha256": "",
        },
        "capture_status": "",
        "capture_limitation": "",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return template


def seal_case(case_path: Path, outcome: str, reason: str) -> dict:
    data = json.loads(case_path.read_text(encoding="utf-8"))
    scope = validate_plan(case_path, data, require_frozen=True)
    if data["status"] != "observing":
        raise ValueError("only an observing shadow case can be sealed")
    validate_observations(case_path, data, scope)
    summary = summarize(case_path)
    quality_rows = [
        row for row in summary["rows"] if row["quality_status"] == "pass"
    ]
    complete = bool(quality_rows) and all(
        not row["missing"]
        and not row["blocked"]
        and not row["insufficient_repeats"]
        for row in quality_rows
    )
    if outcome == "completed":
        if not complete:
            raise ValueError("completed seal requires the full quality-pass matrix")
        terminal_reason = (
            reason.strip()
            or "All preregistered quality-pass service cells are complete."
        )
    elif outcome == "stopped":
        if len(reason.strip()) < 20:
            raise ValueError("stopped seal needs a specific 20+ character reason")
        terminal_reason = reason.strip()
    else:
        raise ValueError("shadow seal outcome must be completed or stopped")
    data["status"] = outcome
    data["seal"] = {
        "outcome": outcome,
        "sealed_at": now(),
        "reason": terminal_reason,
        "observations_digest": canonical_digest(data["observations"]),
        "summary_digest": summary_digest(summary),
        "rule": "No observation, candidate or verdict may change after seal.",
    }
    case_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summarize(case_path)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--case", type=Path, required=True)
    init.add_argument("--case-id", required=True)
    init.add_argument("--original", type=Path, required=True)
    init.add_argument("--language", choices=["en", "ru"], required=True)
    init.add_argument("--genre", required=True)
    init.add_argument("--english-level", default="infer_from_source")
    init.add_argument("--services", required=True)
    init.add_argument(
        "--privacy-mode",
        choices=["delivery_only", "private_research"],
        default="delivery_only",
    )
    init.add_argument(
        "--evidence-tier",
        choices=["delivery_diagnostic", "research_candidate"],
        default="delivery_diagnostic",
    )
    init.add_argument("--consent-quote", default="")

    candidate = sub.add_parser("add-candidate")
    candidate.add_argument("--case", type=Path, required=True)
    candidate.add_argument("--candidate", type=Path, required=True)
    candidate.add_argument("--id", required=True)
    candidate.add_argument("--hypothesis-id", required=True)
    candidate.add_argument("--operation-summary", required=True)
    candidate.add_argument("--quality-status", choices=["pass", "rejected"], required=True)
    candidate.add_argument("--fidelity-evidence", required=True)
    candidate.add_argument("--style-evidence", required=True)
    candidate.add_argument("--english-level-evidence", required=True)

    freeze = sub.add_parser("freeze")
    freeze.add_argument("--case", type=Path, required=True)

    record = sub.add_parser("record")
    record.add_argument("--case", type=Path, required=True)
    record.add_argument("--observation", type=Path, required=True)

    prepare = sub.add_parser("prepare-observation")
    prepare.add_argument("--case", type=Path, required=True)
    prepare.add_argument("--candidate-id", required=True)
    prepare.add_argument("--service", required=True)
    prepare.add_argument("--repeat", type=int, required=True)
    prepare.add_argument("--out", type=Path, required=True)

    seal = sub.add_parser("seal")
    seal.add_argument("--case", type=Path, required=True)
    seal.add_argument("--outcome", choices=["completed", "stopped"], required=True)
    seal.add_argument("--reason", default="")

    validate = sub.add_parser("validate")
    validate.add_argument("--case", type=Path, required=True)

    summary = sub.add_parser("summary")
    summary.add_argument("--case", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "init":
        result = init_case(args)
    elif args.command == "add-candidate":
        result = add_candidate(args)
    elif args.command == "freeze":
        result = freeze_case(args.case.resolve())
    elif args.command == "record":
        result = record_observation(
            args.case.resolve(),
            args.observation.resolve(),
        )
    elif args.command == "prepare-observation":
        result = prepare_observation(args)
    elif args.command == "seal":
        result = seal_case(
            args.case.resolve(),
            args.outcome,
            args.reason,
        )
    elif args.command == "validate":
        result = summarize(args.case.resolve())
    else:
        result = summarize(args.case.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
