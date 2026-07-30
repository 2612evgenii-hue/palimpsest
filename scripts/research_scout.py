#!/usr/bin/env python3
"""Validate a preregistered detector baseline scout.

The scout may select calibration instrumentation targets, but it cannot admit
an editing rule. This validator recomputes the frozen resolvability rule from
the first human/AI baseline in every primary service and checks that only
passing cells were repeated.
"""
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
        raise ValueError("scout result needs preregistration binding")
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
    prereg_path = (result_path.parent / relative).resolve()
    if root != prereg_path.parent and root not in prereg_path.parents:
        raise ValueError("preregistration path escapes result directory")
    if not prereg_path.is_file() or file_sha256(prereg_path) != expected_sha:
        raise ValueError("preregistration hash mismatch")
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    if prereg.get("status") != "frozen_before_live_scores":
        raise ValueError("referenced scout was not frozen before live scores")
    if prereg.get("experiment_id") != data.get("experiment_id"):
        raise ValueError("preregistration experiment mismatch")
    return prereg


def observation_map(data: dict, prereg: dict) -> dict[tuple[str, str, str], dict]:
    pairs = {item["pair"]: item for item in prereg["ordered_pairs"]}
    services = {
        item["id"]
        for item in prereg["services"]["primary_accessible"]
        + prereg["services"].get("diagnostic_if_guest_ui_is_terminal", [])
    }
    mapped: dict[tuple[str, str, str], dict] = {}
    for observation in data.get("observations", []):
        pair = observation.get("pair")
        role = observation.get("role")
        service = observation.get("service")
        if pair not in pairs or role not in {"human", "ai"} or service not in services:
            raise ValueError("observation references unknown pair, role, or service")
        key = (pair, role, service)
        if key in mapped:
            raise ValueError("duplicate scout pair/role/service observation")
        expected_sha = pairs[pair][f"{role}_sha256"]
        if (
            observation.get("candidate_sha256") != expected_sha
            or observation.get("post_visible_text_sha256") != expected_sha
        ):
            raise ValueError("scout observation is not bound to frozen text")
        scores = observation.get("scores_pct")
        states = observation.get("terminal_states")
        times = observation.get("observed_at")
        if not isinstance(scores, list) or any(
            not isinstance(score, (int, float)) or not 0 <= score <= 100
            for score in scores
        ):
            raise ValueError("scores_pct must contain only percentages")
        if (
            not isinstance(states, list)
            or not states
            or any(state not in {"complete", "blocked", "error"} for state in states)
        ):
            raise ValueError("terminal_states are required")
        if not isinstance(times, list) or len(times) != len(states):
            raise ValueError("every terminal state needs a timestamp")
        if prereg.get("schema") == "palimpsest.baseline-scout-preregistration.v2":
            transitions = observation.get("transition_signals")
            if (
                not isinstance(transitions, list)
                or len(transitions) != len(states)
                or any(signal not in ALLOWED_TRANSITIONS for signal in transitions)
            ):
                raise ValueError("scout v2 requires a transition signal per scan")
        if all(state == "complete" for state in states):
            if len(scores) != len(states):
                raise ValueError("complete observations need one score per repeat")
        elif scores:
            raise ValueError("blocked/error observation cannot declare a score")
        if service == "scribbr":
            for field in ("ai_generated_pct", "ai_refined_pct", "human_pct"):
                values = observation.get(field)
                if not isinstance(values, list) or len(values) != len(scores):
                    raise ValueError("Scribbr components must match score repeats")
            for generated, refined, human in zip(
                observation["ai_generated_pct"],
                observation["ai_refined_pct"],
                observation["human_pct"],
            ):
                if round(generated + refined + human, 6) != 100:
                    raise ValueError("Scribbr components must total 100")
        mapped[key] = observation
    return mapped


def recompute_selection_v1(data: dict, prereg: dict) -> dict:
    mapped = observation_map(data, prereg)
    ordered_pairs = [item["pair"] for item in prereg["ordered_pairs"]]
    primary = [item["id"] for item in prereg["services"]["primary_accessible"]]
    rule = prereg["resolvability_rule"]
    passing_cells = []
    for pair in ordered_pairs:
        for service in primary:
            human = mapped.get((pair, "human", service))
            ai = mapped.get((pair, "ai", service))
            if human is None or ai is None:
                raise ValueError("every frozen primary cell must be scanned")
            if (
                human["terminal_states"][0] != "complete"
                or ai["terminal_states"][0] != "complete"
                or not human["scores_pct"]
                or not ai["scores_pct"]
            ):
                raise ValueError("primary baseline needs a complete first scan")
            human_first = float(human["scores_pct"][0])
            ai_first = float(ai["scores_pct"][0])
            passes = (
                rule["ai_score_min_inclusive"]
                <= ai_first
                <= rule["ai_score_max_inclusive"]
                and human_first <= rule["human_score_max_inclusive"]
                and ai_first - human_first >= rule["minimum_ai_minus_human_gap"]
            )
            expected_repeats = 3 if passes else 1
            if (
                len(human["scores_pct"]) != expected_repeats
                or len(ai["scores_pct"]) != expected_repeats
            ):
                raise ValueError("repeat policy differs from frozen cell result")
            if passes:
                human_scores = [float(value) for value in human["scores_pct"]]
                ai_scores = [float(value) for value in ai["scores_pct"]]
                passing_cells.append(
                    {
                        "pair": pair,
                        "service": service,
                        "human_scores_pct": human["scores_pct"],
                        "ai_scores_pct": ai["scores_pct"],
                        "human_median_pct": round(
                            statistics.median(human_scores), 3
                        ),
                        "ai_median_pct": round(statistics.median(ai_scores), 3),
                        "ai_noise_range_pct": round(
                            max(ai_scores) - min(ai_scores), 3
                        ),
                        "gap_pct": round(
                            statistics.median(ai_scores)
                            - statistics.median(human_scores),
                            3,
                        ),
                    }
                )
    passing_pairs = []
    for pair in ordered_pairs:
        if any(cell["pair"] == pair for cell in passing_cells):
            passing_pairs.append(pair)
    selected_pairs = passing_pairs[: rule["maximum_selected_pairs"]]

    diagnostic = [
        item["id"]
        for item in prereg["services"]["diagnostic_if_guest_ui_is_terminal"]
    ]
    for service in diagnostic:
        for key, observation in mapped.items():
            pair, role, observed_service = key
            if observed_service != service:
                continue
            if pair not in selected_pairs or role != "ai":
                raise ValueError("diagnostic scan escaped frozen selected AI scope")
            if len(observation["terminal_states"]) != 1:
                raise ValueError("diagnostic scout permits only one attempt per AI")

    return {
        "passing_cells": passing_cells,
        "selected_pairs": selected_pairs,
        "maximum_selected_pairs": rule["maximum_selected_pairs"],
    }


def recompute_selection_v2(data: dict, prereg: dict) -> dict:
    mapped = observation_map(data, prereg)
    ordered_pairs = [item["pair"] for item in prereg["ordered_pairs"]]
    primary = [item["id"] for item in prereg["services"]["primary_accessible"]]
    rule = prereg["usable_cell_rule"]
    selection_rule = prereg["selection_rule"]
    expected = {
        (pair, role, service)
        for pair in ordered_pairs
        for role in ("human", "ai")
        for service in primary
    }
    if set(mapped) != expected:
        raise ValueError("scout v2 observation matrix is incomplete or out of scope")

    first_transitions = {service: 0 for service in primary}
    pair_results = []
    for pair in ordered_pairs:
        raw_cells = []
        usable_count = 0
        for service in primary:
            human = mapped[(pair, "human", service)]
            ai = mapped[(pair, "ai", service)]
            if (
                human["terminal_states"][0] != "complete"
                or ai["terminal_states"][0] != "complete"
                or not human["scores_pct"]
                or not ai["scores_pct"]
            ):
                raise ValueError("scout v2 first baselines must complete")
            human_first = float(human["scores_pct"][0])
            ai_first = float(ai["scores_pct"][0])
            usable = (
                rule["ai_score_min_inclusive"]
                <= ai_first
                <= rule["ai_score_max_inclusive"]
                and human_first <= rule["human_score_max_inclusive"]
                and ai_first - human_first >= rule["minimum_ai_minus_human_gap"]
            )
            usable_count += int(usable)
            raw_cells.append((service, human, ai, usable))

        expected_repeats = 3 if usable_count else 1
        cells = []
        for service, human, ai, usable in raw_cells:
            if (
                len(human["scores_pct"]) != expected_repeats
                or len(ai["scores_pct"]) != expected_repeats
            ):
                raise ValueError("scout v2 repeat policy differs from frozen rule")
            human_values = [float(value) for value in human["scores_pct"]]
            ai_values = [float(value) for value in ai["scores_pct"]]
            first_transitions[service] += human["transition_signals"].count(
                "first_scan_no_prior_result"
            )
            first_transitions[service] += ai["transition_signals"].count(
                "first_scan_no_prior_result"
            )
            cells.append(
                {
                    "service": service,
                    "usable": usable,
                    "human_scores_pct": human["scores_pct"],
                    "ai_scores_pct": ai["scores_pct"],
                    "human_median_pct": round(
                        statistics.median(human_values), 3
                    ),
                    "ai_median_pct": round(statistics.median(ai_values), 3),
                    "ai_noise_range_pct": round(
                        max(ai_values) - min(ai_values), 3
                    ),
                    "gap_pct": round(
                        statistics.median(ai_values)
                        - statistics.median(human_values),
                        3,
                    ),
                }
            )
        if usable_count == len(primary):
            status = "cross_family_window"
        elif usable_count == 1:
            status = "single_family_window"
        else:
            status = "unusable"
        pair_results.append({"pair": pair, "status": status, "cells": cells})

    if any(count != 1 for count in first_transitions.values()):
        raise ValueError("each fresh service needs exactly one first-scan transition")
    selected = [
        item["pair"]
        for item in pair_results
        if item["status"] == "cross_family_window"
    ][: selection_rule["maximum_selected_pairs"]]
    diagnostic = [
        item["pair"]
        for item in pair_results
        if item["status"] == "single_family_window"
    ]
    return {
        "pair_results": pair_results,
        "selected_pairs": selected,
        "diagnostic_pairs": diagnostic,
        "maximum_selected_pairs": selection_rule["maximum_selected_pairs"],
        "edit_variants_allowed": bool(selected),
    }


def recompute_selection(data: dict, prereg: dict) -> dict:
    schema = prereg.get("schema")
    if schema == "palimpsest.baseline-scout-preregistration.v1":
        return recompute_selection_v1(data, prereg)
    if schema == "palimpsest.baseline-scout-preregistration.v2":
        return recompute_selection_v2(data, prereg)
    raise ValueError("unsupported baseline scout preregistration schema")


def load_result(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") not in {
        "palimpsest.baseline-scout-result.v1",
        "palimpsest.baseline-scout-result.v2",
    }:
        raise ValueError("unsupported baseline scout result schema")
    if data.get("status") != "completed":
        raise ValueError("baseline scout result is not completed")
    prereg = load_preregistration(path, data)
    expected_result_schema = {
        "palimpsest.baseline-scout-preregistration.v1": (
            "palimpsest.baseline-scout-result.v1"
        ),
        "palimpsest.baseline-scout-preregistration.v2": (
            "palimpsest.baseline-scout-result.v2"
        ),
    }.get(prereg.get("schema"))
    if data.get("schema") != expected_result_schema:
        raise ValueError("scout result/preregistration schema mismatch")
    computed = recompute_selection(data, prereg)
    if data.get("selection") != computed:
        raise ValueError("declared baseline scout selection does not recompute")
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
                "selection": data["selection"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
