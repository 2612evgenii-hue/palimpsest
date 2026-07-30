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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    data = load_result(args.result)
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
