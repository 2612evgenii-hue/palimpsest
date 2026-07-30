#!/usr/bin/env python3
"""Validate live research pilots and recompute their declared Pareto evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_bound_preregistration(path: Path, data: dict) -> dict | None:
    binding = data.get("preregistration")
    if binding is None:
        return None
    if not isinstance(binding, dict):
        raise ValueError("preregistration binding must be an object")
    relative = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(relative, str) or not relative or not isinstance(
        expected_sha, str
    ):
        raise ValueError("preregistration binding needs path and sha256")
    root = path.parent.resolve()
    prereg_path = (path.parent / relative).resolve()
    if root != prereg_path.parent and root not in prereg_path.parents:
        raise ValueError("preregistration path escapes pilot directory")
    if not prereg_path.is_file() or _file_sha256(prereg_path) != expected_sha:
        raise ValueError("preregistration hash mismatch")
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    if prereg.get("experiment_id") != data.get("experiment_id"):
        raise ValueError("preregistration experiment mismatch")
    if binding.get("status_at_commit") != "frozen_before_live_scores":
        raise ValueError("pilot needs frozen-before-scores preregistration")
    if prereg.get("status") != "frozen_before_live_scores":
        raise ValueError("referenced preregistration was not frozen")
    commit = binding.get("git_commit_before_live_scores")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("preregistration binding needs full git commit")
    return prereg


def recompute_holdout_transfer(data: dict) -> dict | None:
    declared = data.get("holdout_transfer")
    if declared is None:
        return None
    if not isinstance(declared, dict):
        raise ValueError("holdout_transfer must be an object")
    candidates = data["candidates"]
    confirmatory = {
        candidate_id: candidate
        for candidate_id, candidate in candidates.items()
        if candidate.get("role") == "confirmatory"
    }
    if not confirmatory:
        raise ValueError("holdout_transfer needs confirmatory candidates")
    factors = {candidate.get("factor") for candidate in confirmatory.values()}
    if factors != {declared.get("confirmatory_factor")}:
        raise ValueError("holdout confirmatory factor mismatch")
    services = data["pareto"]["primary_repeated_services"]
    minimum_repeats = data["pareto"]["minimum_repeats"]
    observations = _observation_map(data)
    results = {}
    successes = 0
    for candidate_id, candidate in sorted(
        confirmatory.items(), key=lambda item: item[1].get("sample", "")
    ):
        sample = candidate.get("sample")
        if not isinstance(sample, str) or not sample:
            raise ValueError("confirmatory candidate needs sample")
        if candidate.get("quality", {}).get("status") == "rejected":
            if any(
                observation.get("candidate") == candidate_id
                for observation in data["observations"]
            ):
                raise ValueError("quality-rejected confirmatory candidate was scanned")
            results[sample] = {"status": "failed_before_live_scan"}
            continue
        baselines = [
            baseline_id
            for baseline_id, baseline in candidates.items()
            if baseline.get("sample") == sample
            and baseline.get("authorship") == "ai"
            and "factor" not in baseline
        ]
        if len(baselines) != 1:
            raise ValueError("holdout sample needs one AI baseline")
        baseline_id = baselines[0]
        effects = []
        insufficient_candidate_repeats = False
        for service in services:
            baseline_scores = observations.get((baseline_id, service), [])
            candidate_scores = observations.get((candidate_id, service), [])
            if len(baseline_scores) < minimum_repeats or not candidate_scores:
                effects.append(False)
                continue
            baseline_noise = max(baseline_scores) - min(baseline_scores)
            improves = statistics.median(candidate_scores) < (
                statistics.median(baseline_scores) - baseline_noise
            )
            effects.append(improves)
            if improves and len(candidate_scores) < minimum_repeats:
                insufficient_candidate_repeats = True
        if effects and all(effects) and not insufficient_candidate_repeats:
            status = "success"
            successes += 1
        elif effects and all(effects):
            status = "insufficient_repeats"
        else:
            status = "failed_detector_response"
        results[sample] = {"status": status}
    required = declared.get("required_successes")
    if not isinstance(required, int) or required < 1:
        raise ValueError("holdout required_successes must be positive")
    return {
        "confirmatory_factor": declared.get("confirmatory_factor"),
        "required_successes": required,
        "successful_samples": successes,
        "sample_results": results,
        "transfer_confirmed": successes >= required,
    }


def load_pilot(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "palimpsest.live-research-pilot.v2":
        raise ValueError("unsupported live research pilot schema")
    candidates = data.get("candidates")
    if not isinstance(candidates, dict) or not candidates:
        raise ValueError("pilot needs candidates")
    for candidate_id, candidate in candidates.items():
        if "factor" not in candidate:
            continue
        quality = candidate.get("quality")
        if not isinstance(quality, dict):
            raise ValueError(f"edited candidate needs quality evidence: {candidate_id}")
        if quality.get("status") == "rejected":
            continue
        if (
            not str(quality.get("cefr", "")).startswith("pass_")
            or quality.get("fidelity") != "pass"
            or not isinstance(quality.get("style_distance"), (int, float))
        ):
            raise ValueError(f"edited candidate did not pass quality: {candidate_id}")

    seen: set[tuple[str, str]] = set()
    for observation in data.get("observations", []):
        candidate_id = observation.get("candidate")
        service = observation.get("service")
        key = (candidate_id, service)
        if candidate_id not in candidates:
            raise ValueError("observation references unknown candidate")
        if not isinstance(service, str) or not service:
            raise ValueError("observation needs service")
        if key in seen:
            raise ValueError("duplicate candidate/service observation")
        seen.add(key)
        scores = observation.get("scores_pct")
        if (
            not isinstance(scores, list)
            or not scores
            or any(
                not isinstance(score, (int, float)) or not 0 <= score <= 100
                for score in scores
            )
        ):
            raise ValueError("observation needs scores_pct in [0,100]")
        if observation.get("terminal_state") != "complete":
            raise ValueError("observation needs terminal_state=complete")
        if (
            observation.get("post_visible_text_sha256")
            != candidates[candidate_id].get("canonical_sha256")
        ):
            raise ValueError("post-terminal hash does not bind candidate")
    prereg = _load_bound_preregistration(path, data)
    computed_transfer = recompute_holdout_transfer(data)
    if computed_transfer is not None:
        if prereg is None:
            raise ValueError("holdout result needs bound preregistration")
        prereg_required = prereg.get("confirmatory_success", {}).get(
            "effective_required_successes"
        )
        if prereg_required != computed_transfer["required_successes"]:
            raise ValueError("holdout success threshold differs from preregistration")
        declared = data["holdout_transfer"]
        for key in (
            "confirmatory_factor",
            "required_successes",
            "successful_samples",
            "transfer_confirmed",
        ):
            if declared.get(key) != computed_transfer[key]:
                raise ValueError(f"declared holdout transfer mismatch: {key}")
        declared_statuses = {
            sample: result.get("status")
            for sample, result in declared.get("sample_results", {}).items()
        }
        computed_statuses = {
            sample: result["status"]
            for sample, result in computed_transfer["sample_results"].items()
        }
        if declared_statuses != computed_statuses:
            raise ValueError("declared holdout transfer mismatch: sample_results")
    return data


def _observation_map(data: dict) -> dict[tuple[str, str], list[float]]:
    return {
        (observation["candidate"], observation["service"]): [
            float(score) for score in observation["scores_pct"]
        ]
        for observation in data["observations"]
    }


def recompute_pareto(data: dict) -> dict:
    declared = data.get("pareto")
    if not isinstance(declared, dict):
        raise ValueError("pilot has no declared pareto")
    services = declared.get("primary_repeated_services")
    if (
        not isinstance(services, list)
        or not services
        or any(not isinstance(service, str) or not service for service in services)
    ):
        raise ValueError("pareto needs primary_repeated_services")
    minimum_repeats = declared.get("minimum_repeats")
    if not isinstance(minimum_repeats, int) or minimum_repeats < 1:
        raise ValueError("pareto.minimum_repeats must be positive")

    observations = _observation_map(data)
    threshold = data["admission"]["hard_threshold_pct"]
    rows = []
    for candidate_id, candidate in data["candidates"].items():
        if candidate.get("authorship") == "human":
            continue
        if candidate.get("quality", {}).get("status") == "rejected":
            continue
        scores_by_service = {
            service: observations.get((candidate_id, service), [])
            for service in services
        }
        if any(len(scores) < minimum_repeats for scores in scores_by_service.values()):
            continue
        medians = {
            service: round(statistics.median(scores), 3)
            for service, scores in scores_by_service.items()
        }
        worst = max(medians.values())
        rows.append(
            {
                "candidate": candidate_id,
                "edit_cost": candidate.get("edit_cost", 0.0),
                "median_scores_pct": medians,
                "worst_score_pct": worst,
                "hard_pass": worst < threshold,
            }
        )

    frontier = []
    for row in rows:
        dominated = any(
            other["candidate"] != row["candidate"]
            and other["edit_cost"] <= row["edit_cost"]
            and other["worst_score_pct"] <= row["worst_score_pct"]
            and (
                other["edit_cost"] < row["edit_cost"]
                or other["worst_score_pct"] < row["worst_score_pct"]
            )
            for other in rows
        )
        if not dominated:
            frontier.append(row["candidate"])
    return {
        "primary_repeated_services": services,
        "minimum_repeats": minimum_repeats,
        "eligible_candidates": [row["candidate"] for row in rows],
        "frontier": frontier,
        "rows": rows,
    }


def validate_declared_pareto(path: Path) -> dict:
    data = load_pilot(path)
    computed = recompute_pareto(data)
    declared = data["pareto"]
    for key in (
        "primary_repeated_services",
        "minimum_repeats",
        "eligible_candidates",
        "frontier",
        "rows",
    ):
        if declared.get(key) != computed[key]:
            raise ValueError(f"declared pareto mismatch: {key}")
    return computed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate_declared_pareto(args.pilot)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("ELIGIBLE:", ", ".join(result["eligible_candidates"]) or "none")
        print("PARETO:", ", ".join(result["frontier"]) or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
