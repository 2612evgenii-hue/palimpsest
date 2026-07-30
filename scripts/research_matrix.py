#!/usr/bin/env python3
"""Validate detector-research observations and compute a Pareto frontier."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import minimality  # noqa: E402
import research_variants  # noqa: E402
import _textlib as T  # noqa: E402


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_experiment(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "palimpsest.detector-research.v1":
        raise ValueError("unsupported experiment schema")
    root = path.parent
    original_path = root / data["original"]["path"]
    if file_sha256(original_path) != data["original"]["sha256"]:
        raise ValueError("original hash mismatch")

    candidate_ids = set()
    candidate_hashes = {}
    for candidate in data["candidates"]:
        cid = candidate["id"]
        if cid in candidate_ids:
            raise ValueError(f"duplicate candidate id: {cid}")
        candidate_ids.add(cid)
        candidate_path = root / candidate["path"]
        if file_sha256(candidate_path) != candidate["sha256"]:
            raise ValueError(f"candidate hash mismatch: {cid}")
        candidate_hashes[cid] = candidate["sha256"]
    for observation in data["observations"]:
        candidate_id = observation["candidate_id"]
        if candidate_id not in candidate_ids:
            raise ValueError("observation references unknown candidate")
        status = observation["status"]
        if status == "scored":
            score = observation.get("score_pct")
            if not isinstance(score, (int, float)) or not 0 <= score <= 100:
                raise ValueError("scored observation needs score_pct in [0,100]")
            if observation.get("terminal_state") != "complete":
                raise ValueError("scored observation needs terminal_state=complete")
            if observation.get("visible_text_sha256") != candidate_hashes[candidate_id]:
                raise ValueError("visible text hash does not bind the scored candidate")
        elif status not in {"blocked", "missing"}:
            raise ValueError(f"unsupported observation status: {status}")
        capture = observation.get("capture")
        if capture:
            capture_path = root / capture["path"]
            if file_sha256(capture_path) != capture["sha256"]:
                raise ValueError("capture hash mismatch")
    return data


def summarize(experiment_path: Path) -> dict:
    data = load_experiment(experiment_path)
    root = experiment_path.parent
    original = T.read_text(root / data["original"]["path"])
    mandatory = set(data["policy"]["mandatory_services"])
    by_candidate_service: dict[tuple[str, str], list[float]] = defaultdict(list)
    blocked: dict[str, set[str]] = defaultdict(set)
    for observation in data["observations"]:
        service = observation["service"]
        if service not in mandatory:
            continue
        cid = observation["candidate_id"]
        if observation["status"] == "scored":
            by_candidate_service[(cid, service)].append(float(observation["score_pct"]))
        else:
            blocked[cid].add(service)

    rows = []
    for candidate in data["candidates"]:
        cid = candidate["id"]
        current = T.read_text(root / candidate["path"])
        ratio = minimality.analyze(original, current, 1.0, 1.0)["doc_change_ratio"]
        character_metrics = research_variants.character_change_metrics(original, current)
        edit_cost = max(ratio, character_metrics["char_change_ratio"])
        services = {}
        missing = []
        for service in sorted(mandatory):
            scores = by_candidate_service.get((cid, service), [])
            if not scores:
                missing.append(service)
                continue
            services[service] = {
                "n": len(scores),
                "median": round(statistics.median(scores), 3),
                "min": min(scores),
                "max": max(scores),
                "noise_range": round(max(scores) - min(scores), 3),
            }
        complete = not missing and not blocked[cid]
        worst = max((entry["median"] for entry in services.values()), default=None)
        rows.append(
            {
                "id": cid,
                "operation": candidate["operation"],
                "doc_change_ratio": ratio,
                **character_metrics,
                "edit_cost": edit_cost,
                "services": services,
                "missing": missing,
                "blocked": sorted(blocked[cid]),
                "worst_core_score": worst,
                "hard_pass": bool(complete and worst is not None and worst < data["policy"]["hard_threshold_pct"]),
            }
        )

    comparable = [row for row in rows if row["worst_core_score"] is not None and not row["missing"] and not row["blocked"]]
    frontier = []
    for row in comparable:
        dominated = any(
            other["id"] != row["id"]
            and other["edit_cost"] <= row["edit_cost"]
            and other["worst_core_score"] <= row["worst_core_score"]
            and (
                other["edit_cost"] < row["edit_cost"]
                or other["worst_core_score"] < row["worst_core_score"]
            )
            for other in comparable
        )
        if not dominated:
            frontier.append(row["id"])

    passing = sorted(
        (row for row in comparable if row["hard_pass"]),
        key=lambda row: (
            row["edit_cost"],
            row["changed_spans"],
            row["worst_core_score"],
            row["id"],
        ),
    )
    return {
        "experiment_id": data["experiment_id"],
        "hard_threshold_pct": data["policy"]["hard_threshold_pct"],
        "rows": rows,
        "pareto_frontier": sorted(frontier),
        "least_changed_hard_pass": passing[0]["id"] if passing else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = summarize(args.experiment)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"EXPERIMENT: {result['experiment_id']}")
        for row in result["rows"]:
            print(
                f"{row['id']}: change={row['edit_cost']:.4f} "
                f"worst={row['worst_core_score']} pass={row['hard_pass']}"
            )
        print("PARETO:", ", ".join(result["pareto_frontier"]) or "none")
        print("LEAST CHANGED PASS:", result["least_changed_hard_pass"] or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
