#!/usr/bin/env python3
"""Validate a preregistered Palimpsest micro-edit experiment.

The validator binds every observation to a frozen candidate, recomputes the
advance/repeat policy from the first scores, and rebuilds the declared effect
summary. A screen success is calibration evidence only; it cannot admit a
production editing rule without a new holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

PREREGISTRATION_SCHEMAS = {
    "palimpsest.micro-edit-preregistration.v1",
    "palimpsest.micro-edit-preregistration.v2",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound_json(
    result_path: Path,
    binding: dict,
    *,
    label: str,
    require_commit: bool = False,
) -> dict:
    relative = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} path is required")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError(f"{label} sha256 is required")
    if require_commit:
        commit = binding.get("git_commit")
        if not isinstance(commit, str) or len(commit) != 40:
            raise ValueError(f"{label} needs a full pre-score git commit")
    root = result_path.parent.resolve()
    path = (result_path.parent / relative).resolve()
    if root != path.parent and root not in path.parents:
        raise ValueError(f"{label} path escapes result directory")
    if not path.is_file() or file_sha256(path) != expected_sha:
        raise ValueError(f"{label} hash mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_preregistration_data(path: Path, prereg: dict) -> dict:
    schema = prereg.get("schema")
    if schema not in PREREGISTRATION_SCHEMAS:
        raise ValueError("unsupported micro preregistration schema")
    if prereg.get("status") != "frozen_before_live_scores":
        raise ValueError("micro experiment was not frozen before live scores")
    if schema == "palimpsest.micro-edit-preregistration.v1":
        return prereg

    baseline = _bound_json(
        path,
        prereg.get("baseline_binding", {}),
        label="baseline result",
        require_commit=True,
    )
    selected = prereg["baseline_binding"].get("selected_pairs")
    if (
        not isinstance(selected, list)
        or not selected
        or selected != baseline.get("selection", {}).get("stable_selected_pairs")
    ):
        raise ValueError("micro v2 scope is not the stable baseline selection")
    _bound_json(path, prereg.get("corpus_binding", {}), label="corpus manifest")

    plan_operations: dict[tuple[str, str], dict] = {}
    for binding in prereg.get("plans", []):
        plan = _bound_json(path, binding, label="variant plan")
        sample = binding.get("sample")
        if (
            plan.get("original_sha256") != binding.get("original_sha256")
            or plan.get("reference_sha256") != binding.get("reference_sha256")
        ):
            raise ValueError("variant plan source binding mismatch")
        for operation in plan.get("operations", []):
            key = (sample, operation.get("id"))
            if key in plan_operations or not all(
                isinstance(item, str) for item in key
            ):
                raise ValueError("duplicate or malformed plan operation")
            evidence = operation.get("source_evidence")
            if (
                not isinstance(evidence, dict)
                or not isinstance(evidence.get("relation"), str)
                or len(evidence["relation"].strip()) < 12
                or not isinstance(evidence.get("reference_excerpt"), str)
                or not evidence["reference_excerpt"]
            ):
                raise ValueError("micro v2 operation lacks bound source evidence")
            plan_operations[key] = operation

    candidates: dict[tuple[str, str], dict] = {}
    for candidate in prereg.get("candidates", []):
        key = (candidate.get("sample"), candidate.get("id"))
        if key in candidates or not all(isinstance(item, str) for item in key):
            raise ValueError("duplicate or malformed frozen candidate")
        operation = plan_operations.get(key)
        if (
            operation is None
            or operation.get("factor") != candidate.get("factor")
            or operation.get("candidate_sha256") != candidate.get("sha256")
        ):
            raise ValueError("candidate does not match frozen plan operation")
        eligible = candidate.get("eligible_for_live")
        if not isinstance(eligible, bool):
            raise ValueError("micro v2 candidate needs live eligibility")
        if not eligible and not isinstance(candidate.get("exclusion_reason"), str):
            raise ValueError("excluded candidate needs a frozen reason")
        candidates[key] = candidate
    if set(candidates) != set(plan_operations):
        raise ValueError("micro v2 candidates do not cover every plan operation")

    eligible = [
        candidate
        for candidate in candidates.values()
        if candidate["eligible_for_live"]
    ]
    expected_order = [
        candidate["id"]
        for candidate in sorted(
            eligible,
            key=lambda item: (float(item["edit_cost"]), item["id"]),
        )
    ]
    if prereg.get("live_order") != expected_order:
        raise ValueError("micro v2 live order is not minimal-first")

    services = prereg.get("services", {}).get("primary_screen", [])
    if [item.get("id") for item in services] != ["zerogpt", "scribbr"]:
        raise ValueError("micro v2 requires the frozen cross-family pair")
    for service in services:
        if (
            float(service.get("minimum_effect_pct", 0)) <= 0
            or float(service.get("maximum_same_sha_range_pct", 0)) <= 0
        ):
            raise ValueError("micro v2 service thresholds must be positive")
    return prereg


def validate_preregistration(path: Path) -> dict:
    prereg = json.loads(path.read_text(encoding="utf-8"))
    return _validate_preregistration_data(path, prereg)


def load_preregistration(result_path: Path, data: dict) -> dict:
    binding = data.get("preregistration")
    if not isinstance(binding, dict):
        raise ValueError("micro result needs preregistration binding")
    prereg = _bound_json(
        result_path,
        binding,
        label="preregistration",
        require_commit=True,
    )
    prereg_path = (result_path.parent / binding["path"]).resolve()
    _validate_preregistration_data(prereg_path, prereg)
    if prereg.get("experiment_id") != data.get("experiment_id"):
        raise ValueError("preregistration experiment mismatch")
    return prereg


def _baseline_medians(result_path: Path, prereg: dict) -> dict[tuple[str, str], float]:
    baseline = _bound_json(
        result_path,
        prereg["baseline_binding"],
        label="baseline result",
    )
    medians: dict[tuple[str, str], float] = {}
    selected = set(prereg["baseline_binding"]["selected_pairs"])
    for observation in baseline.get("observations", []):
        if (
            observation.get("pair") in selected
            and observation.get("role") == "ai"
            and observation.get("service") in {"zerogpt", "scribbr"}
        ):
            scores = observation.get("scores_pct")
            if not isinstance(scores, list) or not scores:
                raise ValueError("selected baseline is missing scores")
            medians[(observation["pair"], observation["service"])] = float(
                statistics.median(scores)
            )
    expected = {
        (sample, service)
        for sample in selected
        for service in ("zerogpt", "scribbr")
    }
    if set(medians) != expected:
        raise ValueError("selected baseline medians are incomplete")
    return medians


def _candidate_map(prereg: dict) -> dict[tuple[str, str], dict]:
    candidates: dict[tuple[str, str], dict] = {}
    for candidate in prereg.get("candidates", []):
        if candidate.get("eligible_for_live") is False:
            continue
        key = (candidate.get("sample"), candidate.get("id"))
        if key in candidates or not all(isinstance(item, str) for item in key):
            raise ValueError("duplicate or malformed frozen candidate")
        candidates[key] = candidate
    if not candidates:
        raise ValueError("no frozen candidates")
    return candidates


def _validate_scores(observation: dict, *, require_transition: bool = False) -> None:
    scores = observation.get("scores_pct")
    states = observation.get("terminal_states")
    times = observation.get("observed_at")
    if not isinstance(scores, list) or any(
        not isinstance(score, (int, float)) or not 0 <= score <= 100
        for score in scores
    ):
        raise ValueError("scores_pct must contain percentages")
    if (
        not isinstance(states, list)
        or not states
        or any(state not in {"complete", "blocked", "error"} for state in states)
    ):
        raise ValueError("terminal_states are required")
    if not isinstance(times, list) or len(times) != len(states):
        raise ValueError("every terminal state needs a timestamp")
    if all(state == "complete" for state in states):
        if len(scores) != len(states):
            raise ValueError("complete observations need one score per repeat")
    elif scores:
        raise ValueError("blocked/error observations cannot declare a score")
    if require_transition:
        transitions = observation.get("transition_signals")
        if (
            not isinstance(transitions, list)
            or len(transitions) != len(states)
            or any(
                not isinstance(signal, str)
                or signal in {"", "missing", "none", "not_observed"}
                for signal in transitions
            )
        ):
            raise ValueError("micro v2 observation needs a transition signal")


def observation_map(
    data: dict,
    prereg: dict,
) -> dict[tuple[str, str, str], dict]:
    candidates = _candidate_map(prereg)
    require_transition = (
        prereg.get("schema") == "palimpsest.micro-edit-preregistration.v2"
    )
    services = {"zerogpt", "scribbr", "copyleaks"}
    mapped: dict[tuple[str, str, str], dict] = {}
    for observation in data.get("observations", []):
        sample = observation.get("sample")
        candidate_id = observation.get("id")
        service = observation.get("service")
        key = (sample, candidate_id)
        if key not in candidates or service not in services:
            raise ValueError("observation references unknown candidate or service")
        mapped_key = (sample, candidate_id, service)
        if mapped_key in mapped:
            raise ValueError("duplicate micro candidate/service observation")
        expected_sha = candidates[key]["sha256"]
        if (
            observation.get("candidate_sha256") != expected_sha
            or observation.get("post_visible_text_sha256") != expected_sha
        ):
            raise ValueError("micro observation is not bound to frozen text")
        _validate_scores(observation, require_transition=require_transition)
        if service == "scribbr":
            for field in ("ai_generated_pct", "ai_refined_pct", "human_pct"):
                values = observation.get(field)
                if not isinstance(values, list) or len(values) != len(
                    observation["scores_pct"]
                ):
                    raise ValueError("Scribbr components must match repeats")
            for generated, refined, human in zip(
                observation["ai_generated_pct"],
                observation["ai_refined_pct"],
                observation["human_pct"],
            ):
                if round(generated + refined + human, 6) != 100:
                    raise ValueError("Scribbr components must total 100")
        mapped[mapped_key] = observation
    return mapped


def _round(value: float) -> float:
    return round(value, 6)


def _service_rules(prereg: dict) -> dict[str, dict]:
    return {
        item["id"]: item
        for item in prereg.get("services", {}).get("primary_screen", [])
    }


def _validate_v2_controls(
    data: dict,
    prereg: dict,
    result_path: Path,
) -> list[dict]:
    baseline = _bound_json(
        result_path,
        prereg["baseline_binding"],
        label="baseline result",
    )
    sample = prereg["baseline_binding"]["selected_pairs"][0]
    frozen: dict[tuple[str, str], dict] = {}
    for observation in baseline.get("observations", []):
        if (
            observation.get("pair") == sample
            and observation.get("role") in {"human", "ai"}
            and observation.get("service") in {"zerogpt", "scribbr"}
        ):
            frozen[(observation["role"], observation["service"])] = observation
    expected = {
        (role, service)
        for role in ("human", "ai")
        for service in ("zerogpt", "scribbr")
    }
    if set(frozen) != expected:
        raise ValueError("micro v2 frozen controls are incomplete")

    controls: dict[tuple[str, str], dict] = {}
    for observation in data.get("controls", []):
        key = (observation.get("role"), observation.get("service"))
        if key not in expected or key in controls:
            raise ValueError("duplicate or unknown micro v2 control")
        if (
            observation.get("sample") != sample
            or observation.get("candidate_sha256")
            != frozen[key]["candidate_sha256"]
            or observation.get("post_visible_text_sha256")
            != frozen[key]["candidate_sha256"]
        ):
            raise ValueError("micro v2 control is not bound to frozen text")
        _validate_scores(observation, require_transition=True)
        if len(observation["scores_pct"]) != 1:
            raise ValueError("micro v2 start control needs exactly one score")
        controls[key] = observation
    if set(controls) != expected:
        raise ValueError("micro v2 start controls are incomplete")

    maximum_drift = float(
        prereg["services"]["start_controls"][
            "maximum_drift_from_frozen_median_pct"
        ]
    )
    rows = []
    for key in sorted(expected):
        role, service = key
        frozen_median = float(statistics.median(frozen[key]["scores_pct"]))
        current = float(controls[key]["scores_pct"][0])
        drift = current - frozen_median
        if abs(drift) > maximum_drift:
            raise ValueError("micro v2 start control exceeded frozen drift limit")
        rows.append(
            {
                "role": role,
                "service": service,
                "frozen_median_pct": _round(frozen_median),
                "current_pct": _round(current),
                "drift_pct": _round(drift),
            }
        )
    return rows


def recompute_analysis(data: dict, prereg: dict, result_path: Path) -> dict:
    mapped = observation_map(data, prereg)
    candidates = _candidate_map(prereg)
    baseline = _baseline_medians(result_path, prereg)
    is_v2 = prereg.get("schema") == "palimpsest.micro-edit-preregistration.v2"
    service_rules = _service_rules(prereg)
    zero_noise = (
        {}
        if is_v2
        else prereg["services"]["primary_screen"][0]["baseline_noise"]
    )

    advancing: set[tuple[str, str]] = set()
    for key, candidate in candidates.items():
        sample, candidate_id = key
        zero = mapped.get((sample, candidate_id, "zerogpt"))
        scribbr = mapped.get((sample, candidate_id, "scribbr"))
        if zero is None or scribbr is None:
            raise ValueError("every frozen candidate needs both primary services")
        if not zero["scores_pct"] or not scribbr["scores_pct"]:
            raise ValueError("primary micro screen must return a first score")
        if is_v2:
            observations = {"zerogpt": zero, "scribbr": scribbr}
            improvements = {
                service: (
                    baseline[(sample, service)]
                    - float(observations[service]["scores_pct"][0])
                    > float(service_rules[service]["minimum_effect_pct"])
                )
                for service in observations
            }
            no_cross_regression = all(
                float(observations[service]["scores_pct"][0])
                - baseline[(sample, service)]
                <= float(service_rules[service]["minimum_effect_pct"])
                for service in observations
            )
            improves = any(improvements.values())
        else:
            improves = (
                baseline[(sample, "zerogpt")] - float(zero["scores_pct"][0])
                > float(zero_noise[sample])
            )
            no_cross_regression = (
                float(scribbr["scores_pct"][0]) - baseline[(sample, "scribbr")]
                <= 5
            )
        if improves and no_cross_regression:
            advancing.add(key)
        expected_repeats = 3 if key in advancing else 1
        if (
            len(zero["scores_pct"]) != expected_repeats
            or len(scribbr["scores_pct"]) != expected_repeats
        ):
            raise ValueError("micro repeat policy differs from frozen result")

    diagnostic = [
        observation
        for key, observation in mapped.items()
        if key[2] == "copyleaks"
    ]
    if is_v2 and diagnostic:
        raise ValueError("micro v2 has no frozen diagnostic service")
    if advancing and not is_v2:
        lowest = min(
            advancing,
            key=lambda key: (
                float(candidates[key]["edit_cost"]),
                key[0],
                key[1],
            ),
        )
        if len(diagnostic) != 1:
            raise ValueError("micro diagnostic needs exactly one Copyleaks attempt")
        diagnostic_key = (diagnostic[0]["sample"], diagnostic[0]["id"])
        if diagnostic_key != lowest or len(diagnostic[0]["terminal_states"]) != 1:
            raise ValueError("Copyleaks attempt is not the frozen lowest-cost candidate")
    elif diagnostic and not is_v2:
        raise ValueError("Copyleaks cannot run without an advancing candidate")

    factor_order = [item["id"] for item in prereg["factors"]]
    factor_results = []
    for factor in factor_order:
        rows = []
        factor_keys = [
            key for key, candidate in candidates.items() if candidate["factor"] == factor
        ]
        for sample, candidate_id in sorted(factor_keys):
            candidate = candidates[(sample, candidate_id)]
            services = []
            service_successes = []
            for service in ("zerogpt", "scribbr"):
                observation = mapped[(sample, candidate_id, service)]
                scores = [float(score) for score in observation["scores_pct"]]
                median = float(statistics.median(scores))
                baseline_score = baseline[(sample, service)]
                delta = median - baseline_score
                changed_percent = float(candidate["edit_cost"]) * 100
                if is_v2:
                    service_successes.append(
                        len(scores) == 3
                        and -delta
                        > float(service_rules[service]["minimum_effect_pct"])
                        and max(scores) - min(scores)
                        <= float(
                            service_rules[service][
                                "maximum_same_sha_range_pct"
                            ]
                        )
                    )
                services.append(
                    {
                        "service": service,
                        "baseline_median_pct": _round(baseline_score),
                        "scores_pct": observation["scores_pct"],
                        "median_pct": _round(median),
                        "range_pct": _round(max(scores) - min(scores)),
                        "score_delta_pct": _round(delta),
                        "reduction_per_changed_percent": _round(
                            -delta / changed_percent
                        ),
                    }
                )
            rows.append(
                {
                    "sample": sample,
                    "id": candidate_id,
                    "edit_cost": candidate["edit_cost"],
                    "advanced": (sample, candidate_id) in advancing,
                    **(
                        {"cross_family_success": all(service_successes)}
                        if is_v2
                        else {}
                    ),
                    "services": services,
                }
            )
        factor_results.append(
            {
                "factor": factor,
                "screen_success": bool(rows)
                and all(
                    row.get("cross_family_success", row["advanced"])
                    for row in rows
                ),
                "samples": rows,
            }
        )

    for attempt in data.get("excluded_technical_attempts", []):
        if attempt.get("included_in_analysis") is not False:
            raise ValueError("technical attempt must be excluded from analysis")

    analysis = {
        "advancing_candidates": [
            {"sample": sample, "id": candidate_id}
            for sample, candidate_id in sorted(advancing)
        ],
        "factor_results": factor_results,
        "rule_admission": "none_holdout_required",
    }
    if is_v2:
        successes = [
            {
                "sample": row["sample"],
                "id": row["id"],
                "edit_cost": row["edit_cost"],
                "worst_service_reduction_pct": _round(
                    min(-service["score_delta_pct"] for service in row["services"])
                ),
            }
            for factor in factor_results
            for row in factor["samples"]
            if row["cross_family_success"]
        ]
        successes.sort(
            key=lambda item: (
                float(item["edit_cost"]),
                -float(item["worst_service_reduction_pct"]),
                item["sample"],
                item["id"],
            )
        )
        analysis["start_controls"] = _validate_v2_controls(
            data,
            prereg,
            result_path,
        )
        analysis["cross_family_successes"] = successes
        analysis["selected_minimal_candidate"] = successes[0] if successes else None
    return analysis


def load_result(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "palimpsest.micro-edit-result.v1":
        raise ValueError("unsupported micro-edit result schema")
    if data.get("status") != "completed_calibration_only":
        raise ValueError("micro-edit result is not completed")
    prereg = load_preregistration(path, data)
    computed = recompute_analysis(data, prereg, path)
    if data.get("analysis") != computed:
        raise ValueError("declared micro analysis does not recompute")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--result", type=Path)
    group.add_argument("--preregistration", type=Path)
    args = parser.parse_args()
    if args.preregistration is not None:
        data = validate_preregistration(args.preregistration)
        print(
            json.dumps(
                {
                    "experiment_id": data["experiment_id"],
                    "schema": data["schema"],
                    "eligible_candidates": [
                        item["id"]
                        for item in data["candidates"]
                        if item.get("eligible_for_live") is not False
                    ],
                    "live_order": data.get("live_order"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
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
