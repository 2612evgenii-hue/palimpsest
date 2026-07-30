#!/usr/bin/env python3
"""Validate a transition-bound preregistered detector holdout."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path


ALLOWED_TRANSITIONS = {
    "first_scan_no_prior_result",
    "loading_or_disabled_observed",
    "result_identifier_changed",
    "result_text_changed",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound_path(
    preregistration_path: Path,
    binding: dict,
    *,
    label: str,
) -> Path:
    relative = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} path is required")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError(f"{label} sha256 is required")
    root = preregistration_path.parent.resolve()
    path = (preregistration_path.parent / relative).resolve()
    if root != path.parent and root not in path.parents:
        raise ValueError(f"{label} path escapes preregistration directory")
    if not path.is_file() or file_sha256(path) != expected_sha:
        raise ValueError(f"{label} hash mismatch")
    return path


def validate_preregistration(path: Path) -> dict:
    """Validate the frozen v3 holdout before any detector score is collected."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "palimpsest.holdout-preregistration.v3":
        raise ValueError("unsupported standalone holdout preregistration schema")
    if data.get("status") != "frozen_before_live_scores":
        raise ValueError("holdout preregistration is not frozen")
    if data.get("hypothesis", {}).get("factor") != "quote_integrity_restoration":
        raise ValueError("holdout-03 factor is not quote integrity restoration")

    calibration_binding = data.get("calibration_binding")
    corpus_binding = data.get("corpus_binding")
    if not isinstance(calibration_binding, dict) or not isinstance(
        corpus_binding,
        dict,
    ):
        raise ValueError("holdout preregistration bindings are incomplete")
    calibration_path = _bound_path(
        path,
        calibration_binding,
        label="calibration result",
    )
    corpus_path = _bound_path(path, corpus_binding, label="corpus manifest")

    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    if calibration.get("schema") != "palimpsest.micro-edit-result.v1":
        raise ValueError("holdout calibration result schema mismatch")
    if calibration.get("analysis", {}).get("rule_admission") != (
        "none_holdout_required"
    ):
        raise ValueError("holdout calibration did not require a holdout")
    factors = {
        item.get("factor"): item
        for item in calibration.get("analysis", {}).get("factor_results", [])
    }
    factor = factors.get(calibration_binding.get("factor"))
    if not factor or factor.get("screen_success") is not True:
        raise ValueError("bound calibration factor did not pass its screen")
    commit = calibration_binding.get("git_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("calibration binding needs a full pre-holdout commit")

    manifest = json.loads(corpus_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "palimpsest.research-corpus.v3":
        raise ValueError("holdout corpus schema mismatch")
    dataset_revision = corpus_binding.get("dataset_revision")
    if dataset_revision not in {
        item.get("revision") for item in manifest.get("datasets", {}).values()
    }:
        raise ValueError("holdout dataset revision is not in the manifest")
    samples = {sample.get("id"): sample for sample in manifest.get("samples", [])}

    plans = data.get("plans")
    if not isinstance(plans, list) or len(plans) != 3:
        raise ValueError("holdout-03 requires exactly three frozen plans")
    if len({plan.get("sample") for plan in plans}) != len(plans):
        raise ValueError("holdout-03 sample ids must be unique")
    for frozen in plans:
        sample = frozen.get("sample")
        human = samples.get(f"{sample}-human")
        ai = samples.get(f"{sample}-ai")
        if not human or not ai:
            raise ValueError(f"{sample}: missing balanced corpus pair")
        if human.get("partition") != "holdout" or ai.get("partition") != "holdout":
            raise ValueError(f"{sample}: corpus pair is not holdout")
        human_sha = human.get("canonical_sha256", human.get("sha256"))
        ai_sha = ai.get("canonical_sha256", ai.get("sha256"))
        if (
            frozen.get("human_sha256") != human_sha
            or frozen.get("ai_sha256") != ai_sha
        ):
            raise ValueError(f"{sample}: corpus hashes do not match the frozen plan")
        plan_path = _bound_path(path, frozen, label=f"{sample} plan")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if (
            plan.get("schema") != "palimpsest.variant-plan.v1"
            or plan.get("sample_id") != f"{sample}-ai"
            or plan.get("original_sha256") != ai_sha
            or plan.get("reference_sha256") != human_sha
        ):
            raise ValueError(f"{sample}: variant plan binding mismatch")
        operations = plan.get("operations")
        if not isinstance(operations, list) or len(operations) != 1:
            raise ValueError(f"{sample}: holdout plan must have one operation")
        operation = operations[0]
        evidence = operation.get("source_evidence")
        if (
            operation.get("id") != "quote-integrity"
            or operation.get("factor") != "quote_integrity_restoration"
            or operation.get("candidate_sha256") != frozen.get("candidate_sha256")
            or not isinstance(evidence, dict)
            or not isinstance(evidence.get("reference_excerpt"), str)
            or not evidence["reference_excerpt"]
            or not isinstance(evidence.get("relation"), str)
            or len(evidence["relation"]) < 12
        ):
            raise ValueError(f"{sample}: source-bound quote operation mismatch")
        quality = frozen.get("quality")
        if (
            not isinstance(quality, dict)
            or quality.get("english_level") != "pass_C2"
            or not str(quality.get("fidelity_screen", "")).startswith(
                ("pass", "source_reconciled_")
            )
            or not 0 < float(frozen.get("edit_cost", 0)) <= 0.08
        ):
            raise ValueError(f"{sample}: frozen quality screen is not eligible")

    repo_root = path.resolve().parents[2]
    registry_path = repo_root / "assets/service-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    services = data.get("services", {})
    declared = []
    for role in ("primary_effect", "guardrail", "diagnostic"):
        rows = services.get(role)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"holdout service role {role} is empty")
        for row in rows:
            service_id = row.get("id")
            facts = registry.get("services", {}).get(service_id)
            if not facts:
                raise ValueError(f"unknown holdout service: {service_id}")
            if row.get("independence_group") != facts.get("independence_group"):
                raise ValueError(f"{service_id}: forged independence group")
            if facts.get("guest_access") is not True or "en" not in facts.get(
                "languages",
                [],
            ) and "*" not in facts.get("languages", []):
                raise ValueError(f"{service_id}: not an EN guest service")
            declared.append(service_id)
    if set(declared) != {"zerogpt", "copyleaks", "scribbr", "sapling"}:
        raise ValueError("holdout-03 detector scope changed")
    if {
        row["id"] for row in services["primary_effect"]
    } != {"zerogpt", "copyleaks"}:
        raise ValueError("holdout-03 primary independent pair changed")

    repeats = data.get("repeat_policy", {})
    if repeats.get("primary_effect") != {"human": 1, "ai": 3, "candidate": 3}:
        raise ValueError("holdout-03 primary repeat policy changed")
    if repeats.get("guardrail") != {"human": 1, "ai": 3, "candidate": 3}:
        raise ValueError("holdout-03 guardrail repeat policy changed")
    if repeats.get("diagnostic") != {"human": 1, "ai": 1, "candidate": 1}:
        raise ValueError("holdout-03 diagnostic repeat policy changed")
    return data


def load_preregistration(result_path: Path, data: dict) -> dict:
    binding = data.get("preregistration")
    if not isinstance(binding, dict):
        raise ValueError("holdout result needs preregistration binding")
    relative = binding.get("path")
    expected_sha = binding.get("sha256")
    commit = binding.get("git_commit")
    if not isinstance(relative, str) or not relative:
        raise ValueError("preregistration path is required")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError("preregistration sha256 is required")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("preregistration needs a full pre-score git commit")
    root = result_path.parent.resolve()
    path = (result_path.parent / relative).resolve()
    if root != path.parent and root not in path.parents:
        raise ValueError("preregistration path escapes result directory")
    if not path.is_file() or file_sha256(path) != expected_sha:
        raise ValueError("preregistration hash mismatch")
    prereg = json.loads(path.read_text(encoding="utf-8"))
    if prereg.get("status") != "frozen_before_live_scores":
        raise ValueError("referenced holdout was not frozen")
    if prereg.get("experiment_id") != data.get("experiment_id"):
        raise ValueError("preregistration experiment mismatch")
    return prereg


def _role_hashes(prereg: dict) -> dict[tuple[str, str], str]:
    result = {}
    for plan in prereg.get("plans", []):
        sample = plan["sample"]
        result[(sample, "human")] = plan["human_sha256"]
        result[(sample, "ai")] = plan["ai_sha256"]
        result[(sample, "candidate")] = plan["candidate_sha256"]
    return result


def observation_map(data: dict, prereg: dict) -> dict[tuple[str, str, str], dict]:
    hashes = _role_hashes(prereg)
    services = {service["id"] for service in prereg["services"]["primary"]}
    mapped: dict[tuple[str, str, str], dict] = {}
    first_transitions = {service: 0 for service in services}
    for observation in data.get("observations", []):
        sample = observation.get("sample")
        role = observation.get("role")
        service = observation.get("service")
        if (sample, role) not in hashes or service not in services:
            raise ValueError("holdout observation references unknown scope")
        key = (sample, role, service)
        if key in mapped:
            raise ValueError("duplicate holdout sample/role/service observation")
        expected_sha = hashes[(sample, role)]
        if (
            observation.get("candidate_sha256") != expected_sha
            or observation.get("post_visible_text_sha256") != expected_sha
        ):
            raise ValueError("holdout observation is not bound to frozen text")
        scores = observation.get("scores_pct")
        states = observation.get("terminal_states")
        times = observation.get("observed_at")
        transitions = observation.get("transition_signals")
        if (
            not isinstance(scores, list)
            or len(scores) != 3
            or any(
                not isinstance(score, (int, float)) or not 0 <= score <= 100
                for score in scores
            )
        ):
            raise ValueError("holdout requires three percentage scores per cell")
        if states != ["complete", "complete", "complete"]:
            raise ValueError("holdout cells require three complete terminal states")
        if not isinstance(times, list) or len(times) != 3:
            raise ValueError("holdout cells require three timestamps")
        if (
            not isinstance(transitions, list)
            or len(transitions) != 3
            or any(signal not in ALLOWED_TRANSITIONS for signal in transitions)
        ):
            raise ValueError("holdout scan lacks a valid transition signal")
        first_transitions[service] += transitions.count(
            "first_scan_no_prior_result"
        )
        if observation.get("included_in_analysis") is not True:
            raise ValueError("primary holdout observation was excluded")
        if service == "scribbr":
            for field in ("ai_generated_pct", "ai_refined_pct", "human_pct"):
                values = observation.get(field)
                if not isinstance(values, list) or len(values) != 3:
                    raise ValueError("Scribbr components must match repeats")
            for generated, refined, human in zip(
                observation["ai_generated_pct"],
                observation["ai_refined_pct"],
                observation["human_pct"],
            ):
                if round(generated + refined + human, 6) != 100:
                    raise ValueError("Scribbr components must total 100")
        mapped[key] = observation
    expected = {
        (sample, role, service)
        for sample in {plan["sample"] for plan in prereg["plans"]}
        for role in ("human", "ai", "candidate")
        for service in services
    }
    if set(mapped) != expected:
        raise ValueError("holdout observation matrix is incomplete")
    if any(count != 1 for count in first_transitions.values()):
        raise ValueError("each fresh service needs exactly one first-scan transition")
    return mapped


def _summary(scores: list[float]) -> dict:
    values = [float(score) for score in scores]
    return {
        "scores_pct": scores,
        "median_pct": round(float(statistics.median(values)), 6),
        "range_pct": round(max(values) - min(values), 6),
    }


def recompute_analysis(data: dict, prereg: dict) -> dict:
    mapped = observation_map(data, prereg)
    sample_results = []
    successful = 0
    for plan in prereg["plans"]:
        sample = plan["sample"]
        human_zero = _summary(mapped[(sample, "human", "zerogpt")]["scores_pct"])
        baseline_zero = _summary(mapped[(sample, "ai", "zerogpt")]["scores_pct"])
        candidate_zero = _summary(
            mapped[(sample, "candidate", "zerogpt")]["scores_pct"]
        )
        baseline_scribbr = _summary(
            mapped[(sample, "ai", "scribbr")]["scores_pct"]
        )
        candidate_scribbr = _summary(
            mapped[(sample, "candidate", "scribbr")]["scores_pct"]
        )
        reduction = round(
            baseline_zero["median_pct"] - candidate_zero["median_pct"],
            6,
        )
        required_reduction = max(
            baseline_zero["range_pct"],
            candidate_zero["range_pct"],
            1.0,
        )
        scribbr_regression = round(
            candidate_scribbr["median_pct"]
            - baseline_scribbr["median_pct"],
            6,
        )
        eligible = baseline_zero["median_pct"] >= 20
        success = (
            eligible
            and baseline_zero["range_pct"] <= 5
            and candidate_zero["range_pct"] <= 5
            and reduction > required_reduction
            and scribbr_regression <= 5
        )
        if not eligible:
            status = "ineligible_zerogpt_baseline_below_20"
        elif reduction <= required_reduction:
            status = "failed_no_effect_above_noise"
        elif baseline_zero["range_pct"] > 5 or candidate_zero["range_pct"] > 5:
            status = "failed_same_sha_instability"
        elif scribbr_regression > 5:
            status = "failed_cross_service_regression"
        else:
            status = "success"
        successful += int(success)
        sample_results.append(
            {
                "sample": sample,
                "status": status,
                "eligible": eligible,
                "success": success,
                "edit_cost": plan["edit_cost"],
                "zerogpt_human": human_zero,
                "zerogpt_baseline": baseline_zero,
                "zerogpt_candidate": candidate_zero,
                "zerogpt_reduction_pct": reduction,
                "required_reduction_pct": required_reduction,
                "scribbr_baseline": baseline_scribbr,
                "scribbr_candidate": candidate_scribbr,
                "scribbr_regression_pct": scribbr_regression,
            }
        )
    for attempt in data.get("excluded_technical_attempts", []):
        if attempt.get("included_in_analysis") is not False:
            raise ValueError("technical attempt must be excluded")
    return {
        "sample_results": sample_results,
        "successful_samples": successful,
        "holdout_success": successful == len(sample_results),
        "factor": prereg["hypothesis"]["factor"],
        "production_rule_admitted": False,
        "admission_reason": "holdout_failed_and_independent_group_missing",
    }


def load_result(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "palimpsest.holdout-result.v2":
        raise ValueError("unsupported holdout result schema")
    if data.get("status") != "completed_holdout":
        raise ValueError("holdout result is not completed")
    prereg = load_preregistration(path, data)
    computed = recompute_analysis(data, prereg)
    if data.get("analysis") != computed:
        raise ValueError("declared holdout analysis does not recompute")
    return data


def partial_observation_map(
    data: dict,
    prereg: dict,
) -> dict[tuple[str, str], dict]:
    """Validate the complete ZeroGPT slice of an interrupted holdout.

    A partial result is intentionally not accepted by ``load_result``.  This
    narrower validator preserves a useful falsification signal without
    pretending that the preregistered multi-service matrix was completed.
    """
    hashes = _role_hashes(prereg)
    repeat_policy = prereg["repeat_policy"]["primary_effect"]
    mapped: dict[tuple[str, str], dict] = {}
    for observation in data.get("observations", []):
        sample = observation.get("sample")
        role = observation.get("role")
        if observation.get("service") != "zerogpt":
            raise ValueError("partial holdout observations are limited to ZeroGPT")
        if (sample, role) not in hashes:
            raise ValueError("partial holdout observation references unknown scope")
        key = (sample, role)
        if key in mapped:
            raise ValueError("duplicate partial holdout sample/role observation")
        expected_sha = hashes[key]
        if (
            observation.get("candidate_sha256") != expected_sha
            or observation.get("post_visible_text_sha256") != expected_sha
        ):
            raise ValueError("partial holdout observation is not bound to frozen text")
        expected_repeats = repeat_policy[role]
        scores = observation.get("scores_pct")
        states = observation.get("terminal_states")
        transitions = observation.get("transition_signals")
        if (
            not isinstance(scores, list)
            or len(scores) != expected_repeats
            or any(
                not isinstance(score, (int, float)) or not 0 <= score <= 100
                for score in scores
            )
        ):
            raise ValueError("partial holdout score count does not match frozen repeats")
        if states != ["complete"] * expected_repeats:
            raise ValueError("partial holdout scores require complete terminal states")
        if (
            not isinstance(transitions, list)
            or len(transitions) != expected_repeats
            or any(signal not in ALLOWED_TRANSITIONS for signal in transitions)
        ):
            raise ValueError("partial holdout scan lacks a valid transition signal")
        if observation.get("included_in_analysis") is not True:
            raise ValueError("completed partial observation was excluded")
        if observation.get("capture_status") != "missing":
            raise ValueError("partial holdout capture status is not honest")
        if observation.get("timestamp_status") != (
            "not_preserved_after_user_interruption"
        ):
            raise ValueError("partial holdout timestamp limitation is missing")
        if "observed_at" in observation:
            raise ValueError("partial holdout must not invent lost timestamps")
        mapped[key] = observation
    expected = {
        (plan["sample"], role)
        for plan in prereg["plans"]
        for role in ("human", "ai", "candidate")
    }
    if set(mapped) != expected:
        raise ValueError("partial holdout ZeroGPT matrix is incomplete")
    return mapped


def recompute_partial_analysis(data: dict, prereg: dict) -> dict:
    mapped = partial_observation_map(data, prereg)
    sample_results = []
    successful = 0
    for plan in prereg["plans"]:
        sample = plan["sample"]
        human = _summary(mapped[(sample, "human")]["scores_pct"])
        baseline = _summary(mapped[(sample, "ai")]["scores_pct"])
        candidate = _summary(mapped[(sample, "candidate")]["scores_pct"])
        reduction = round(baseline["median_pct"] - candidate["median_pct"], 6)
        required_reduction = max(
            baseline["range_pct"],
            candidate["range_pct"],
            2.0,
        )
        eligible = baseline["median_pct"] >= 20
        success = (
            eligible
            and baseline["range_pct"] <= 5
            and candidate["range_pct"] <= 5
            and reduction > required_reduction
        )
        if not eligible:
            status = "ineligible_zerogpt_baseline_below_20"
        elif reduction <= required_reduction:
            status = "failed_no_effect_above_noise"
        elif baseline["range_pct"] > 5 or candidate["range_pct"] > 5:
            status = "failed_same_sha_instability"
        else:
            status = "zerogpt_effect_only"
        successful += int(success)
        sample_results.append(
            {
                "sample": sample,
                "status": status,
                "eligible": eligible,
                "zerogpt_effect": success,
                "edit_cost": plan["edit_cost"],
                "zerogpt_human": human,
                "zerogpt_baseline": baseline,
                "zerogpt_candidate": candidate,
                "zerogpt_reduction_pct": reduction,
                "required_reduction_pct": required_reduction,
            }
        )

    blocked = data.get("blocked_attempts")
    if not isinstance(blocked, list) or len(blocked) != 1:
        raise ValueError("partial holdout needs the single recorded blocked attempt")
    attempt = blocked[0]
    hashes = _role_hashes(prereg)
    if (
        attempt.get("service") != "copyleaks"
        or attempt.get("sample") != "news-quote-01"
        or attempt.get("role") != "human"
        or attempt.get("candidate_sha256")
        != hashes[("news-quote-01", "human")]
        or attempt.get("post_visible_text_sha256")
        != hashes[("news-quote-01", "human")]
        or attempt.get("terminal_state") != "blocked"
        or attempt.get("score_pct") is not None
        or attempt.get("transition_signal") not in ALLOWED_TRANSITIONS
        or attempt.get("included_in_analysis") is not False
        or len(str(attempt.get("visible_terminal_message", ""))) < 20
    ):
        raise ValueError("Copyleaks blocked attempt is incomplete or unbound")
    if attempt.get("timestamp_status") != "not_preserved_after_user_interruption":
        raise ValueError("blocked attempt timestamp limitation is missing")
    if "observed_at" in attempt:
        raise ValueError("blocked attempt must not invent a lost timestamp")

    zero_failed_all = len(sample_results) == 3 and all(
        row["eligible"] and not row["zerogpt_effect"]
        for row in sample_results
    )
    return {
        "sample_results": sample_results,
        "zerogpt_successful_samples": successful,
        "zerogpt_transfer_rejected": zero_failed_all,
        "confirmatory_holdout_completed": False,
        "primary_pair_available": False,
        "factor": prereg["hypothesis"]["factor"],
        "production_rule_admitted": False,
        "admission_reason": (
            "all_three_zerogpt_effect_tests_failed_and_copyleaks_was_blocked"
        ),
    }


def load_partial_result(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "palimpsest.holdout-partial-result.v1":
        raise ValueError("unsupported partial holdout result schema")
    if data.get("status") != "stopped_incomplete_nonconfirmatory":
        raise ValueError("partial holdout status overclaims completion")
    prereg = load_preregistration(path, data)
    prereg_path = (path.parent / data["preregistration"]["path"]).resolve()
    validate_preregistration(prereg_path)
    if data.get("evidence_limits") != {
        "individual_timestamps_preserved": False,
        "captures_preserved": False,
        "multi_service_matrix_complete": False,
        "safe_claim": (
            "The preregistered quote-integrity factor failed all three "
            "ZeroGPT effect tests; the full confirmatory holdout was not completed."
        ),
    }:
        raise ValueError("partial holdout evidence limits changed")
    expected_not_run = [
        {
            "service": "copyleaks",
            "scope": "remaining preregistered cells",
            "reason": "guest scan limit reached before the first score",
        },
        {
            "service": "scribbr",
            "scope": "all preregistered cells",
            "reason": (
                "first technical fill failed before submission; no result was "
                "transmitted or inferred"
            ),
        },
        {
            "service": "sapling",
            "scope": "all preregistered cells",
            "reason": (
                "user reprioritized the work after the confirmatory factor had "
                "already failed all three ZeroGPT effect tests"
            ),
        },
    ]
    if data.get("not_run") != expected_not_run:
        raise ValueError("partial holdout not-run scope changed")
    if len(str(data.get("stop_reason", "")).strip()) < 80:
        raise ValueError("partial holdout stop reason is missing")
    computed = recompute_partial_analysis(data, prereg)
    if data.get("analysis") != computed:
        raise ValueError("declared partial holdout analysis does not recompute")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--result", type=Path)
    group.add_argument("--partial-result", type=Path)
    group.add_argument("--preregistration", type=Path)
    args = parser.parse_args()
    if args.preregistration:
        data = validate_preregistration(args.preregistration)
        print(
            json.dumps(
                {
                    "experiment_id": data["experiment_id"],
                    "status": data["status"],
                    "samples": [plan["sample"] for plan in data["plans"]],
                    "primary_services": [
                        service["id"]
                        for service in data["services"]["primary_effect"]
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    data = (
        load_partial_result(args.partial_result)
        if args.partial_result
        else load_result(args.result)
    )
    print(
        json.dumps(
            {
                "experiment_id": data["experiment_id"],
                "analysis": data["analysis"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
