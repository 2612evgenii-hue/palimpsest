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
    if prereg.get("status") != "frozen_before_live_scores":
        raise ValueError("referenced micro experiment was not frozen")
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
        key = (candidate.get("sample"), candidate.get("id"))
        if key in candidates or not all(isinstance(item, str) for item in key):
            raise ValueError("duplicate or malformed frozen candidate")
        candidates[key] = candidate
    if not candidates:
        raise ValueError("no frozen candidates")
    return candidates


def _validate_scores(observation: dict) -> None:
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


def observation_map(
    data: dict,
    prereg: dict,
) -> dict[tuple[str, str, str], dict]:
    candidates = _candidate_map(prereg)
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
        _validate_scores(observation)
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


def recompute_analysis(data: dict, prereg: dict, result_path: Path) -> dict:
    mapped = observation_map(data, prereg)
    candidates = _candidate_map(prereg)
    baseline = _baseline_medians(result_path, prereg)
    zero_noise = prereg["services"]["primary_screen"][0]["baseline_noise"]

    advancing: set[tuple[str, str]] = set()
    for key, candidate in candidates.items():
        sample, candidate_id = key
        zero = mapped.get((sample, candidate_id, "zerogpt"))
        scribbr = mapped.get((sample, candidate_id, "scribbr"))
        if zero is None or scribbr is None:
            raise ValueError("every frozen candidate needs both primary services")
        if not zero["scores_pct"] or not scribbr["scores_pct"]:
            raise ValueError("primary micro screen must return a first score")
        improves = (
            baseline[(sample, "zerogpt")] - float(zero["scores_pct"][0])
            > float(zero_noise[sample])
        )
        no_cross_regression = (
            float(scribbr["scores_pct"][0]) - baseline[(sample, "scribbr")] <= 5
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
    if advancing:
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
    elif diagnostic:
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
            for service in ("zerogpt", "scribbr"):
                observation = mapped[(sample, candidate_id, service)]
                scores = [float(score) for score in observation["scores_pct"]]
                median = float(statistics.median(scores))
                baseline_score = baseline[(sample, service)]
                delta = median - baseline_score
                changed_percent = float(candidate["edit_cost"]) * 100
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
                    "services": services,
                }
            )
        factor_results.append(
            {
                "factor": factor,
                "screen_success": bool(rows)
                and all(row["advanced"] for row in rows),
                "samples": rows,
            }
        )

    for attempt in data.get("excluded_technical_attempts", []):
        if attempt.get("included_in_analysis") is not False:
            raise ValueError("technical attempt must be excluded from analysis")

    return {
        "advancing_candidates": [
            {"sample": sample, "id": candidate_id}
            for sample, candidate_id in sorted(advancing)
        ],
        "factor_results": factor_results,
        "rule_admission": "none_holdout_required",
    }


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
