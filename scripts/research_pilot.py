#!/usr/bin/env python3
"""Validate live research pilots and recompute their declared Pareto evidence."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


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
