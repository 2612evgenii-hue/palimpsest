#!/usr/bin/env python3
"""Regression tests for the Palimpsest 4.0 research harness."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import research_matrix  # noqa: E402
import research_micro  # noqa: E402
import research_corpus  # noqa: E402
import research_holdout  # noqa: E402
import research_pilot  # noqa: E402
import research_scout  # noqa: E402
import research_variants  # noqa: E402
import shadow_case  # noqa: E402


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ResearchCorpusTests(unittest.TestCase):
    def test_manifest_has_pinned_balanced_pairs_and_real_holdout(self) -> None:
        manifest = json.loads(
            (ROOT / "evals/research-v4/corpus-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema"], "palimpsest.research-corpus.v3")
        self.assertEqual(
            manifest["canonicalization"]["id"],
            "plain_text_v1",
        )
        self.assertEqual(
            manifest["datasets"]["mage"]["revision"],
            "342663f0a2b775455c023f5d36a1341ff0ec5402",
        )
        self.assertEqual(
            manifest["datasets"]["aigc-text-bank-deepseek"]["revision"],
            "38d3e0e23fc9997d26929f1fecf9b46eeae567be",
        )
        samples = manifest["samples"]
        self.assertEqual(len({sample["id"] for sample in samples}), len(samples))
        self.assertTrue(
            all(sample["dataset"] in manifest["datasets"] for sample in samples)
        )
        pairs = {}
        for sample in samples:
            pairs.setdefault(sample["topic_pair"], set()).add(sample["authorship"])
        self.assertTrue(all(authorship == {"human", "ai"} for authorship in pairs.values()))
        self.assertTrue(any(sample["partition"] == "holdout" for sample in samples))
        self.assertTrue(any(sample["partition"] == "calibration" for sample in samples))
        self.assertTrue(
            any(
                sample.get("genre") == "nonnative_essay"
                and sample.get("cefr_level") == "B1"
                for sample in samples
            )
        )
        genres = {sample.get("genre") for sample in samples if sample.get("genre")}
        self.assertGreaterEqual(len(genres), 3)

    def test_baseline_scout_is_frozen_and_bound_before_live_scores(self) -> None:
        manifest_path = ROOT / "evals/research-v4/corpus-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        prereg = json.loads(
            (
                ROOT
                / "evals/research-v4/baseline-scout-01-preregistration.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            prereg["schema"],
            "palimpsest.baseline-scout-preregistration.v1",
        )
        self.assertEqual(prereg["status"], "frozen_before_live_scores")
        self.assertEqual(
            prereg["corpus_binding"]["sha256"],
            hashlib.sha256(manifest_bytes).hexdigest(),
        )
        samples = {sample["id"]: sample for sample in manifest["samples"]}
        self.assertEqual(len(prereg["ordered_pairs"]), 5)
        self.assertEqual(
            [pair["pair"] for pair in prereg["ordered_pairs"]],
            [
                "essay-b2-01",
                "arxiv-polish-01",
                "news-polish-01",
                "pubmed-02",
                "pubmed-05",
            ],
        )
        for pair in prereg["ordered_pairs"]:
            for role in ("human", "ai"):
                sample = samples[f"{pair['pair']}-{role}"]
                expected = sample.get("canonical_sha256", sample["sha256"])
                self.assertEqual(pair[f"{role}_sha256"], expected)
                self.assertEqual(sample["partition"], "calibration")
        rule = prereg["resolvability_rule"]
        self.assertEqual(rule["ai_score_min_inclusive"], 20)
        self.assertEqual(rule["ai_score_max_inclusive"], 90)
        self.assertEqual(rule["human_score_max_inclusive"], 40)
        self.assertEqual(rule["minimum_ai_minus_human_gap"], 20)
        self.assertEqual(rule["maximum_selected_pairs"], 3)

    def test_cross_family_scout_two_is_frozen_on_new_strict_pairs(self) -> None:
        research_dir = ROOT / "evals/research-v4"
        manifest_path = research_dir / "scout-02-corpus-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        prereg = json.loads(
            (research_dir / "baseline-scout-02-preregistration.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            prereg["schema"],
            "palimpsest.baseline-scout-preregistration.v2",
        )
        self.assertEqual(prereg["status"], "frozen_before_live_scores")
        self.assertEqual(
            prereg["corpus_binding"]["sha256"],
            hashlib.sha256(manifest_bytes).hexdigest(),
        )
        samples = {sample["id"]: sample for sample in manifest["samples"]}
        self.assertEqual(len(prereg["ordered_pairs"]), 6)
        self.assertGreaterEqual(
            sum(
                pair["genre"] in {"scientific_abstract", "formal_news"}
                for pair in prereg["ordered_pairs"]
            ),
            4,
        )
        for pair in prereg["ordered_pairs"]:
            for role in ("human", "ai"):
                sample = samples[f"{pair['pair']}-{role}"]
                self.assertEqual(
                    pair[f"{role}_sha256"],
                    sample.get("canonical_sha256", sample["sha256"]),
                )
        self.assertEqual(
            prereg["selection_rule"]["cross_family_window"],
            "both primary service cells pass",
        )
        self.assertIn(
            "stop without edit variants",
            prereg["selection_rule"]["no_cross_family_window"],
        )

    def test_partial_jsonl_range_finds_one_complete_pinned_row(self) -> None:
        payload = (
            b'partial-prefix\n'
            b'{"id":"other","model":"DeepSeek","text":"x"}\n'
            b'{"id":"wanted","model":"DeepSeek","text":"human","text_ai":"ai"}\n'
            b'{"id":"cut'
        )
        row = research_corpus.find_jsonl_row(payload, "wanted")
        self.assertEqual(row["text"], "human")
        self.assertEqual(row["text_ai"], "ai")

    def test_plain_text_canonicalization_removes_only_transport_artifacts(self) -> None:
        self.assertEqual(
            research_corpus.canonicalize_text("Alpha \t\r\n\r\nBeta  "),
            "Alpha\n\nBeta",
        )
        self.assertEqual(
            research_corpus.canonicalize_text("Alpha\n\nBeta\n"),
            "Alpha\n\nBeta\n",
        )

    def test_b1_pilot_is_bound_and_rejects_cross_detector_regression(self) -> None:
        pilot = json.loads(
            (ROOT / "evals/research-v4/pilot-02-b1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(pilot["status"], "superseded")
        self.assertEqual(pilot["superseded_by"], "pilot-04-b1-canonical.json")
        for observation in pilot["observations"]:
            self.assertEqual(
                observation["candidate_sha256"],
                observation["visible_text_sha256"],
            )
            self.assertEqual(observation["terminal_state"], "complete")

        def scores(candidate: str, service: str) -> list[float]:
            matches = [
                observation["scores_pct"]
                for observation in pilot["observations"]
                if observation["candidate"] == candidate
                and observation["service"] == service
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        self.assertEqual(scores("human-control", "zerogpt"), [25.5, 25.5, 25.5])
        self.assertLess(
            scores("s4-merge-smell-frame", "zerogpt")[0],
            scores("baseline", "zerogpt")[0],
        )
        self.assertGreater(
            scores("s4-merge-smell-frame", "scribbr")[0],
            scores("baseline", "scribbr")[0],
        )
        self.assertEqual(
            pilot["quality_screen"]["s3-rhetorical-to-declarative"]["disposition"],
            "not_scanned",
        )

    def test_canonical_pilot_rejects_two_service_success_after_sapling_failure(self) -> None:
        pilot = json.loads(
            (ROOT / "evals/research-v4/pilot-03-canonical.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(pilot["status"], "current_calibration")
        candidates = pilot["candidates"]
        for observation in pilot["observations"]:
            expected_sha = candidates[observation["candidate"]]["canonical_sha256"]
            self.assertEqual(observation["post_visible_text_sha256"], expected_sha)
            self.assertEqual(observation["terminal_state"], "complete")

        def scores(candidate: str, service: str) -> list[float]:
            matches = [
                observation["scores_pct"]
                for observation in pilot["observations"]
                if observation["candidate"] == candidate
                and observation["service"] == service
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        self.assertEqual(scores("s2-split-mechanism", "zerogpt"), [0, 0, 0])
        self.assertEqual(scores("s2-split-mechanism", "scribbr"), [19, 19, 19])
        self.assertEqual(scores("s2-split-mechanism", "sapling"), [99.6])
        self.assertEqual(scores("human-control", "sapling"), [100])
        self.assertFalse(pilot["admission"]["passes_all_observed_services"])
        self.assertFalse(pilot["admission"]["rule_admitted"])

    def test_canonical_b1_pilot_rejects_highlight_map_and_small_score_gain(
        self,
    ) -> None:
        pilot = json.loads(
            (ROOT / "evals/research-v4/pilot-04-b1-canonical.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(pilot["status"], "current_calibration")
        candidates = pilot["candidates"]
        plan = json.loads(
            (
                ROOT / "evals/research-v4/essay-b1-01-variant-plan.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            plan["original_sha256"],
            candidates["baseline"]["canonical_sha256"],
        )
        self.assertEqual(
            {operation["id"] for operation in plan["operations"]},
            set(candidates) - {"human-control", "baseline"},
        )
        for observation in pilot["observations"]:
            expected_sha = candidates[observation["candidate"]]["canonical_sha256"]
            self.assertEqual(observation["post_visible_text_sha256"], expected_sha)
            self.assertEqual(observation["terminal_state"], "complete")

        def scores(candidate: str, service: str) -> list[float]:
            matches = [
                observation["scores_pct"]
                for observation in pilot["observations"]
                if observation["candidate"] == candidate
                and observation["service"] == service
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        self.assertEqual(scores("human-control", "zerogpt"), [25.5, 25.5, 25.5])
        self.assertEqual(scores("human-control", "scribbr"), [0, 0, 0])
        self.assertEqual(scores("human-control", "sapling"), [99.5])
        self.assertGreater(
            scores("s4-merge-smell-frame", "scribbr")[0],
            scores("baseline", "scribbr")[0],
        )
        self.assertLess(
            max(scores("s10-unhighlighted-control", "zerogpt")),
            min(scores("baseline", "zerogpt")),
        )
        self.assertLess(
            max(scores("s10-unhighlighted-control", "scribbr")),
            min(scores("baseline", "scribbr")),
        )
        self.assertEqual(
            scores("s10-unhighlighted-control", "sapling"),
            scores("baseline", "sapling"),
        )
        highlighted_new = {
            "s6-split-health-example",
            "s7-active-passive-smoke-claim",
            "s8-expand-balanced-frame",
            "s9-expand-imagined-scene",
        }
        baseline_score = scores("baseline", "zerogpt")[0]
        self.assertTrue(
            all(
                scores(candidate, "zerogpt")[0] > baseline_score
                for candidate in highlighted_new
            )
        )
        rejected = candidates["s3-rhetorical-to-declarative"]
        self.assertEqual(rejected["quality"]["status"], "rejected")
        self.assertNotIn(
            "s3-rhetorical-to-declarative",
            pilot["pareto"]["eligible_candidates"],
        )
        self.assertFalse(
            pilot["admission"]["highlight_map_supported_as_causal_edit_guide"]
        )
        self.assertFalse(pilot["admission"]["rule_admitted"])
        computed = research_pilot.validate_declared_pareto(
            ROOT / "evals/research-v4/pilot-04-b1-canonical.json"
        )
        self.assertEqual(
            computed["eligible_candidates"],
            ["baseline", "s4-merge-smell-frame", "s10-unhighlighted-control"],
        )
        self.assertFalse(any(row["hard_pass"] for row in computed["rows"]))

    def test_technical_pilot_records_saturation_and_quality_cliff(self) -> None:
        pilot_path = ROOT / "evals/research-v4/pilot-05-tech-canonical.json"
        pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
        self.assertEqual(pilot["status"], "current_calibration")
        self.assertEqual(pilot["genre"], "technical_explanation")
        self.assertTrue(pilot["source_as_reference"])
        candidates = pilot["candidates"]

        def scores(candidate: str, service: str) -> list[float]:
            matches = [
                observation["scores_pct"]
                for observation in pilot["observations"]
                if observation["candidate"] == candidate
                and observation["service"] == service
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        self.assertEqual(scores("human-control", "zerogpt"), [38, 38, 38])
        self.assertEqual(scores("human-control", "scribbr"), [0, 0, 0])
        self.assertEqual(scores("human-control", "sapling"), [99.1])
        self.assertEqual(scores("baseline", "zerogpt"), [100, 100, 100])
        self.assertEqual(scores("baseline", "scribbr"), [100, 100, 100])
        self.assertEqual(
            scores("p2-punctuation-and-verb", "zerogpt"),
            [100, 100, 100],
        )
        self.assertEqual(
            scores("p2-punctuation-and-verb", "scribbr"),
            [100, 100, 100],
        )
        self.assertEqual(
            pilot["zerogpt_highlight_map"]["baseline_marked_sentences"],
            pilot["zerogpt_highlight_map"]["baseline_total_sentences"],
        )
        self.assertEqual(
            candidates["p4-plus-two-splits"]["quality"]["status"],
            "rejected",
        )
        self.assertGreater(
            candidates["p6-plus-frame-removals"]["quality"]["style_distance"],
            30,
        )
        self.assertEqual(pilot["blocked_services"][0]["service"], "copyleaks")
        self.assertFalse(pilot["admission"]["rule_admitted"])
        computed = research_pilot.validate_declared_pareto(pilot_path)
        self.assertEqual(
            computed["eligible_candidates"],
            ["baseline", "p2-punctuation-and-verb"],
        )
        self.assertEqual(computed["frontier"], ["baseline"])
        self.assertFalse(any(row["hard_pass"] for row in computed["rows"]))

    def test_live_pilot_validator_rejects_declared_pareto_theater(self) -> None:
        pilot_path = ROOT / "evals/research-v4/pilot-04-b1-canonical.json"
        pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
        pilot["pareto"]["rows"][-1]["hard_pass"] = True
        with tempfile.TemporaryDirectory() as temp:
            tampered = Path(temp) / "pilot.json"
            tampered.write_text(json.dumps(pilot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "declared pareto mismatch"):
                research_pilot.validate_declared_pareto(tampered)


class ResearchScoutTests(unittest.TestCase):
    def result_path(self) -> Path:
        return ROOT / "evals/research-v4/baseline-scout-01-result.json"

    def result_path_two(self) -> Path:
        return ROOT / "evals/research-v4/baseline-scout-02-result.json"

    def copied_result_two(self, root: Path, data: dict) -> Path:
        prereg = ROOT / "evals/research-v4/baseline-scout-02-preregistration.json"
        (root / prereg.name).write_bytes(prereg.read_bytes())
        result = root / "result.json"
        result.write_text(json.dumps(data), encoding="utf-8")
        return result

    def test_baseline_scout_recomputes_frozen_selection(self) -> None:
        data = research_scout.load_result(self.result_path())
        self.assertEqual(
            data["selection"]["selected_pairs"],
            ["arxiv-polish-01", "news-polish-01"],
        )
        cells = {
            (cell["pair"], cell["service"]): cell
            for cell in data["selection"]["passing_cells"]
        }
        self.assertEqual(
            cells[("arxiv-polish-01", "zerogpt")]["ai_scores_pct"],
            [63.7, 63.8, 63.7],
        )
        self.assertEqual(
            cells[("news-polish-01", "zerogpt")]["ai_scores_pct"],
            [76.3, 76.3, 76.3],
        )

    def test_baseline_scout_rejects_forged_selection(self) -> None:
        data = json.loads(self.result_path().read_text(encoding="utf-8"))
        data["selection"]["selected_pairs"] = ["essay-b2-01"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prereg = ROOT / "evals/research-v4/baseline-scout-01-preregistration.json"
            (root / prereg.name).write_bytes(prereg.read_bytes())
            path = root / "result.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not recompute"):
                research_scout.load_result(path)

    def test_baseline_scout_rejects_unfrozen_extra_repeats(self) -> None:
        data = json.loads(self.result_path().read_text(encoding="utf-8"))
        observation = next(
            item
            for item in data["observations"]
            if item["pair"] == "essay-b2-01"
            and item["role"] == "ai"
            and item["service"] == "zerogpt"
        )
        observation["scores_pct"].append(10.6)
        observation["terminal_states"].append("complete")
        observation["observed_at"].append("2026-07-30T17:00:00Z")
        prereg = json.loads(
            (
                ROOT
                / "evals/research-v4/baseline-scout-01-preregistration.json"
            ).read_text(encoding="utf-8")
        )
        with self.assertRaisesRegex(ValueError, "repeat policy"):
            research_scout.recompute_selection(data, prereg)

    def test_cross_family_scout_v2_selects_only_two_service_window(self) -> None:
        prereg = {
            "schema": "palimpsest.baseline-scout-preregistration.v2",
            "ordered_pairs": [
                {
                    "pair": "p1",
                    "human_sha256": "1" * 64,
                    "ai_sha256": "2" * 64,
                },
                {
                    "pair": "p2",
                    "human_sha256": "3" * 64,
                    "ai_sha256": "4" * 64,
                },
            ],
            "services": {
                "primary_accessible": [{"id": "zerogpt"}, {"id": "scribbr"}]
            },
            "usable_cell_rule": {
                "ai_score_min_inclusive": 20,
                "ai_score_max_inclusive": 90,
                "human_score_max_inclusive": 50,
                "minimum_ai_minus_human_gap": 10,
            },
            "selection_rule": {"maximum_selected_pairs": 2},
        }
        scores = {
            ("p1", "human", "zerogpt"): [0, 0, 0],
            ("p1", "ai", "zerogpt"): [50, 50, 50],
            ("p1", "human", "scribbr"): [0, 0, 0],
            ("p1", "ai", "scribbr"): [40, 40, 40],
            ("p2", "human", "zerogpt"): [10, 10, 10],
            ("p2", "ai", "zerogpt"): [30, 30, 30],
            ("p2", "human", "scribbr"): [0, 0, 0],
            ("p2", "ai", "scribbr"): [0, 0, 0],
        }
        observations = []
        first = {"zerogpt": True, "scribbr": True}
        hashes = {
            ("p1", "human"): "1" * 64,
            ("p1", "ai"): "2" * 64,
            ("p2", "human"): "3" * 64,
            ("p2", "ai"): "4" * 64,
        }
        for (pair, role, service), values in scores.items():
            transitions = ["loading_or_disabled_observed"] * 3
            if first[service]:
                transitions[0] = "first_scan_no_prior_result"
                first[service] = False
            observation = {
                "pair": pair,
                "role": role,
                "service": service,
                "scores_pct": values,
                "candidate_sha256": hashes[(pair, role)],
                "post_visible_text_sha256": hashes[(pair, role)],
                "terminal_states": ["complete"] * 3,
                "transition_signals": transitions,
                "observed_at": ["2026-07-30T18:00:00Z"] * 3,
            }
            if service == "scribbr":
                observation.update(
                    {
                        "ai_generated_pct": values,
                        "ai_refined_pct": [0, 0, 0],
                        "human_pct": [100 - value for value in values],
                    }
                )
            observations.append(observation)
        selection = research_scout.recompute_selection(
            {"observations": observations},
            prereg,
        )
        self.assertEqual(selection["selected_pairs"], ["p1"])
        self.assertEqual(selection["stable_selected_pairs"], ["p1"])
        self.assertEqual(selection["unstable_selected_pairs"], [])
        self.assertEqual(selection["diagnostic_pairs"], ["p2"])
        self.assertTrue(selection["edit_variants_allowed"])
        tampered = json.loads(json.dumps({"observations": observations}))
        first_observation = tampered["observations"][0]
        first_observation["transition_signals"][0] = "loading_or_disabled_observed"
        with self.assertRaisesRegex(ValueError, "first-scan transition"):
            research_scout.recompute_selection(tampered, prereg)

    def test_cross_family_scout_two_keeps_only_stable_news_scope(self) -> None:
        data = research_scout.load_result(self.result_path_two())
        self.assertEqual(
            data["selection"]["selected_pairs"],
            ["news-polish-04", "qa-polish-02"],
        )
        self.assertEqual(
            data["selection"]["stable_selected_pairs"],
            ["news-polish-04"],
        )
        self.assertEqual(
            data["selection"]["unstable_selected_pairs"],
            ["qa-polish-02"],
        )
        self.assertEqual(
            data["interpretation"]["next_experiment_scope"],
            ["news-polish-04"],
        )

    def test_cross_family_scout_two_rejects_forged_stable_scope(self) -> None:
        data = json.loads(self.result_path_two().read_text(encoding="utf-8"))
        data["interpretation"]["next_experiment_scope"] = ["qa-polish-02"]
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "ignores stability"):
                research_scout.load_result(path)

    def test_cross_family_scout_two_rejects_missing_transition(self) -> None:
        data = json.loads(self.result_path_two().read_text(encoding="utf-8"))
        data["observations"][0]["transition_signals"][1] = "missing"
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "transition signal"):
                research_scout.load_result(path)


class ResearchMicroEditTests(unittest.TestCase):
    def result_path(self) -> Path:
        return ROOT / "evals/research-v4/micro-01-result.json"

    def result_path_two(self) -> Path:
        return ROOT / "evals/research-v4/micro-02-result.json"

    def copied_result(self, root: Path, data: dict) -> Path:
        research_dir = ROOT / "evals/research-v4"
        for name in (
            "micro-01-preregistration.json",
            "baseline-scout-01-result.json",
        ):
            (root / name).write_bytes((research_dir / name).read_bytes())
        result = root / "result.json"
        result.write_text(json.dumps(data), encoding="utf-8")
        return result

    def copied_result_two(self, root: Path, data: dict) -> Path:
        research_dir = ROOT / "evals/research-v4"
        for name in (
            "micro-02-preregistration.json",
            "baseline-scout-02-result.json",
            "scout-02-corpus-manifest.json",
            "news-polish-04-micro-plan.json",
        ):
            (root / name).write_bytes((research_dir / name).read_bytes())
        result = root / "result.json"
        result.write_text(json.dumps(data), encoding="utf-8")
        return result

    def test_micro_edit_experiment_is_frozen_and_rebuilds_exact_candidates(
        self,
    ) -> None:
        research_dir = ROOT / "evals/research-v4"
        prereg = json.loads(
            (research_dir / "micro-01-preregistration.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            prereg["schema"],
            "palimpsest.micro-edit-preregistration.v1",
        )
        self.assertEqual(prereg["status"], "frozen_before_live_scores")
        baseline = research_dir / prereg["baseline_binding"]["path"]
        self.assertEqual(
            hashlib.sha256(baseline.read_bytes()).hexdigest(),
            prereg["baseline_binding"]["sha256"],
        )
        self.assertEqual(
            prereg["baseline_binding"]["git_commit"],
            "1d76a44a7123a22cd5ecefd47abd13129659c5fe",
        )
        declared = {
            (candidate["sample"], candidate["id"]): candidate
            for candidate in prereg["candidates"]
        }
        self.assertEqual(len(declared), 6)
        self.assertEqual(
            {candidate["factor"] for candidate in prereg["candidates"]},
            {
                "evaluative_framing_removal",
                "direct_subject_restoration",
                "direct_claim_restoration",
            },
        )
        for plan_binding in prereg["plans"]:
            plan_path = research_dir / plan_binding["path"]
            self.assertEqual(
                hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                plan_binding["sha256"],
            )
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(
                plan["original_sha256"],
                plan_binding["original_sha256"],
            )
            self.assertEqual(
                plan["reference_sha256"],
                plan_binding["reference_sha256"],
            )
            operations = {
                operation["id"]: operation for operation in plan["operations"]
            }
            self.assertEqual(set(operations), {"f1-evaluative-framing", "f2-direct-subject", "f3-direct-claim"})
            for operation_id, operation in operations.items():
                candidate = declared[(plan_binding["sample"], operation_id)]
                self.assertEqual(candidate["factor"], operation["factor"])
                self.assertEqual(candidate["quality"]["fidelity_screen"], "pass")
                self.assertTrue(
                    candidate["quality"]["english_level"].startswith("pass_")
                )
                self.assertTrue(
                    candidate["quality"]["semantic_review"].startswith("pass_")
                )

    def test_micro_result_recomputes_screen_without_admitting_rule(self) -> None:
        data = research_micro.load_result(self.result_path())
        results = {
            row["factor"]: row for row in data["analysis"]["factor_results"]
        }
        self.assertFalse(
            results["evaluative_framing_removal"]["screen_success"]
        )
        self.assertTrue(results["direct_subject_restoration"]["screen_success"])
        self.assertTrue(results["direct_claim_restoration"]["screen_success"])
        news_subject = next(
            sample
            for sample in results["direct_subject_restoration"]["samples"]
            if sample["sample"] == "news-polish-01"
        )
        zero = next(
            service
            for service in news_subject["services"]
            if service["service"] == "zerogpt"
        )
        self.assertEqual(zero["scores_pct"], [76.2, 0, 0])
        self.assertEqual(zero["range_pct"], 76.2)
        self.assertEqual(
            data["analysis"]["rule_admission"],
            "none_holdout_required",
        )

    def test_micro_result_rejects_forged_candidate_binding(self) -> None:
        data = json.loads(self.result_path().read_text(encoding="utf-8"))
        data["observations"][0]["candidate_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "not bound"):
                research_micro.load_result(path)

    def test_micro_result_rejects_unfrozen_extra_repeat(self) -> None:
        data = json.loads(self.result_path().read_text(encoding="utf-8"))
        observation = next(
            item
            for item in data["observations"]
            if item["sample"] == "arxiv-polish-01"
            and item["id"] == "f1-evaluative-framing"
            and item["service"] == "zerogpt"
        )
        observation["scores_pct"].append(64.0)
        observation["terminal_states"].append("complete")
        observation["observed_at"].append("2026-07-30T18:00:00Z")
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "repeat policy"):
                research_micro.load_result(path)

    def test_micro_result_rejects_score_summary_theater(self) -> None:
        data = json.loads(self.result_path().read_text(encoding="utf-8"))
        data["analysis"]["factor_results"][0]["screen_success"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "does not recompute"):
                research_micro.load_result(path)

    def test_micro_result_rejects_included_timeout_attempt(self) -> None:
        data = json.loads(self.result_path().read_text(encoding="utf-8"))
        data["excluded_technical_attempts"][0]["included_in_analysis"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "excluded"):
                research_micro.load_result(path)

    def test_micro_two_preregistration_is_minimal_first_and_source_bound(self) -> None:
        path = ROOT / "evals/research-v4/micro-02-preregistration.json"
        prereg = research_micro.validate_preregistration(path)
        self.assertEqual(
            prereg["schema"],
            "palimpsest.micro-edit-preregistration.v2",
        )
        costs = {
            item["id"]: item["edit_cost"]
            for item in prereg["candidates"]
            if item["eligible_for_live"]
        }
        self.assertEqual(
            prereg["live_order"],
            sorted(costs, key=lambda item: (costs[item], item)),
        )
        excluded = next(
            item
            for item in prereg["candidates"]
            if item["id"] == "f3-metaphor-removal"
        )
        self.assertFalse(excluded["eligible_for_live"])
        self.assertEqual(
            excluded["exclusion_reason"],
            "quality_first_style_non_improvement",
        )

    def test_micro_two_rejects_excluded_candidate_and_missing_transition(self) -> None:
        prereg = json.loads(
            (
                ROOT / "evals/research-v4/micro-02-preregistration.json"
            ).read_text(encoding="utf-8")
        )
        excluded = next(
            item
            for item in prereg["candidates"]
            if item["id"] == "f3-metaphor-removal"
        )
        observation = {
            "sample": excluded["sample"],
            "id": excluded["id"],
            "service": "zerogpt",
            "scores_pct": [40],
            "candidate_sha256": excluded["sha256"],
            "post_visible_text_sha256": excluded["sha256"],
            "terminal_states": ["complete"],
            "transition_signals": ["loading_or_disabled_observed"],
            "observed_at": ["2026-07-30T18:00:00Z"],
        }
        with self.assertRaisesRegex(ValueError, "unknown candidate"):
            research_micro.observation_map(
                {"observations": [observation]},
                prereg,
            )
        eligible = next(
            item for item in prereg["candidates"] if item["eligible_for_live"]
        )
        observation.update(
            {
                "sample": eligible["sample"],
                "id": eligible["id"],
                "candidate_sha256": eligible["sha256"],
                "post_visible_text_sha256": eligible["sha256"],
                "transition_signals": ["missing"],
            }
        )
        with self.assertRaisesRegex(ValueError, "transition signal"):
            research_micro.observation_map(
                {"observations": [observation]},
                prereg,
            )

    def test_micro_two_recomputes_cross_family_minimal_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            human_sha = "1" * 64
            ai_sha = "2" * 64
            candidate_sha = "3" * 64
            baseline = {
                "observations": [
                    {
                        "pair": "p1",
                        "role": role,
                        "service": service,
                        "scores_pct": scores,
                        "candidate_sha256": human_sha if role == "human" else ai_sha,
                    }
                    for role, service, scores in (
                        ("human", "zerogpt", [10, 10, 10]),
                        ("ai", "zerogpt", [50, 50, 50]),
                        ("human", "scribbr", [0, 0, 0]),
                        ("ai", "scribbr", [40, 40, 40]),
                    )
                ]
            }
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            prereg = {
                "schema": "palimpsest.micro-edit-preregistration.v2",
                "baseline_binding": {
                    "path": baseline_path.name,
                    "sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                    "selected_pairs": ["p1"],
                },
                "candidates": [
                    {
                        "sample": "p1",
                        "id": "c1",
                        "factor": "safe_factor",
                        "sha256": candidate_sha,
                        "edit_cost": 0.01,
                        "eligible_for_live": True,
                    }
                ],
                "factors": [{"id": "safe_factor"}],
                "services": {
                    "primary_screen": [
                        {
                            "id": "zerogpt",
                            "minimum_effect_pct": 2,
                            "maximum_same_sha_range_pct": 5,
                        },
                        {
                            "id": "scribbr",
                            "minimum_effect_pct": 2,
                            "maximum_same_sha_range_pct": 5,
                        },
                    ],
                    "start_controls": {
                        "maximum_drift_from_frozen_median_pct": 5
                    },
                },
            }

            def observation(
                *,
                service: str,
                scores: list[float],
                sha: str,
                role: str | None = None,
            ) -> dict:
                row = {
                    "service": service,
                    "scores_pct": scores,
                    "candidate_sha256": sha,
                    "post_visible_text_sha256": sha,
                    "terminal_states": ["complete"] * len(scores),
                    "transition_signals": [
                        "loading_or_disabled_observed"
                    ] * len(scores),
                    "observed_at": [
                        f"2026-07-30T18:00:0{index}Z"
                        for index in range(len(scores))
                    ],
                }
                if role is None:
                    row.update({"sample": "p1", "id": "c1"})
                    if service == "scribbr":
                        row.update(
                            {
                                "ai_generated_pct": scores,
                                "ai_refined_pct": [0] * len(scores),
                                "human_pct": [100 - score for score in scores],
                            }
                        )
                else:
                    row.update({"sample": "p1", "role": role})
                return row

            data = {
                "controls": [
                    observation(
                        service=service,
                        scores=[score],
                        sha=human_sha if role == "human" else ai_sha,
                        role=role,
                    )
                    for role, service, score in (
                        ("human", "zerogpt", 10),
                        ("ai", "zerogpt", 50),
                        ("human", "scribbr", 0),
                        ("ai", "scribbr", 40),
                    )
                ],
                "observations": [
                    observation(
                        service="zerogpt",
                        scores=[45, 44, 45],
                        sha=candidate_sha,
                    ),
                    observation(
                        service="scribbr",
                        scores=[37, 37, 36],
                        sha=candidate_sha,
                    ),
                ],
                "excluded_technical_attempts": [],
            }
            analysis = research_micro.recompute_analysis(
                data,
                prereg,
                root / "result.json",
            )
            self.assertEqual(
                analysis["selected_minimal_candidate"]["id"],
                "c1",
            )
            self.assertTrue(
                analysis["factor_results"][0]["samples"][0][
                    "cross_family_success"
                ]
            )

    def test_micro_two_live_result_selects_true_minimum_only(self) -> None:
        data = research_micro.load_result(self.result_path_two())
        self.assertEqual(
            data["analysis"]["selected_minimal_candidate"],
            {
                "sample": "news-polish-04",
                "id": "f7-quote-date",
                "edit_cost": 0.001883,
                "worst_service_reduction_pct": 7.7,
            },
        )
        self.assertEqual(
            [item["id"] for item in data["analysis"]["cross_family_successes"]],
            ["f7-quote-date", "f8-quote-integrity"],
        )
        dates = next(
            item
            for item in data["analysis"]["factor_results"]
            if item["factor"] == "unsupported_date_removal"
        )
        self.assertFalse(dates["screen_success"])

    def test_micro_two_rejects_forged_minimal_winner(self) -> None:
        data = json.loads(self.result_path_two().read_text(encoding="utf-8"))
        data["analysis"]["selected_minimal_candidate"]["id"] = (
            "f8-quote-integrity"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "does not recompute"):
                research_micro.load_result(path)

    def test_micro_two_rejects_missing_transition_and_control_drift(self) -> None:
        data = json.loads(self.result_path_two().read_text(encoding="utf-8"))
        data["observations"][0]["transition_signals"][0] = "missing"
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "transition signal"):
                research_micro.load_result(path)
        data = json.loads(self.result_path_two().read_text(encoding="utf-8"))
        control = next(
            item
            for item in data["controls"]
            if item["role"] == "ai" and item["service"] == "zerogpt"
        )
        control["scores_pct"] = [60]
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_result_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "drift limit"):
                research_micro.load_result(path)


class ResearchVariantTests(unittest.TestCase):
    def test_builder_binds_source_evidence_to_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_text = "The last remaining witness spoke."
            reference_text = "The oldest living witness spoke at the event."
            original = root / "original.txt"
            reference = root / "reference.txt"
            original.write_text(original_text, encoding="utf-8")
            reference.write_text(reference_text, encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "original_sha256": digest(original_text),
                        "reference_sha256": digest(reference_text),
                        "operations": [
                            {
                                "id": "restore-title",
                                "factor": "factual_title_restoration",
                                "old": "last remaining",
                                "new": "oldest living",
                                "source_evidence": {
                                    "relation": "restores the source title",
                                    "reference_excerpt": "The oldest living witness spoke",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = research_variants.build(
                original,
                plan,
                root / "variants",
                reference,
            )
            self.assertEqual(result["reference_sha256"], digest(reference_text))

    def test_builder_rejects_forged_reference_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_text = "The last remaining witness spoke."
            reference_text = "The oldest living witness spoke at the event."
            original = root / "original.txt"
            reference = root / "reference.txt"
            original.write_text(original_text, encoding="utf-8")
            reference.write_text(reference_text, encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "original_sha256": digest(original_text),
                        "reference_sha256": digest(reference_text),
                        "operations": [
                            {
                                "id": "restore-title",
                                "factor": "factual_title_restoration",
                                "old": "last remaining",
                                "new": "oldest living",
                                "source_evidence": {
                                    "relation": "restores the source title",
                                    "reference_excerpt": "A fabricated source excerpt",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "bound reference excerpt"):
                research_variants.build(
                    original,
                    plan,
                    root / "variants",
                    reference,
                )

    def test_exact_one_factor_builder_is_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_text = "A stable claim remains here. A generic frame follows."
            original = root / "original.txt"
            original.write_text(original_text, encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "original_sha256": digest(original_text),
                        "operations": [
                            {
                                "id": "remove-frame",
                                "factor": "frame",
                                "old": "A generic frame follows.",
                                "new": "The frame follows.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = research_variants.build(original, plan, root / "variants")
            self.assertEqual(len(result["variants"]), 1)
            self.assertGreater(result["variants"][0]["doc_change_ratio"], 0)
            self.assertEqual(
                Path(result["variants"][0]["path"]).read_text(encoding="utf-8"),
                "A stable claim remains here. The frame follows.",
            )

    def test_builder_rejects_ambiguous_source_span(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_text = "same same"
            original = root / "original.txt"
            original.write_text(original_text, encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "original_sha256": digest(original_text),
                        "operations": [
                            {"id": "bad", "factor": "test", "old": "same", "new": "other"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "expected one source span"):
                research_variants.build(original, plan, root / "variants")

    def test_builder_supports_hash_bound_progressive_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_text = "First stable sentence. Second stable sentence."
            original = root / "original.txt"
            original.write_text(original_text, encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "original_sha256": digest(original_text),
                        "operations": [
                            {
                                "id": "two-local-edits",
                                "factor": "progressive_bundle",
                                "replacements": [
                                    {
                                        "old": "First stable sentence.",
                                        "new": "The first sentence is stable.",
                                    },
                                    {
                                        "old": "Second stable sentence.",
                                        "new": "The second sentence is stable.",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = research_variants.build(original, plan, root / "variants")
            candidate = result["variants"][0]
            self.assertEqual(candidate["replacement_count"], 2)
            self.assertEqual(
                Path(candidate["path"]).read_text(encoding="utf-8"),
                "The first sentence is stable. The second sentence is stable.",
            )

    def test_builder_rejects_mixed_single_and_bundle_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_text = "A stable sentence."
            original = root / "original.txt"
            original.write_text(original_text, encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "original_sha256": digest(original_text),
                        "operations": [
                            {
                                "id": "ambiguous-shape",
                                "factor": "test",
                                "old": "A stable sentence.",
                                "new": "The sentence is stable.",
                                "replacements": [
                                    {
                                        "old": "A stable sentence.",
                                        "new": "The sentence remains stable.",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not both"):
                research_variants.build(original, plan, root / "variants")

    def test_surface_metric_counts_punctuation_only_edit(self) -> None:
        metrics = research_variants.character_change_metrics(
            "One frame. Another follows.",
            "One frame: another follows.",
        )
        self.assertGreater(metrics["char_change_ratio"], 0)
        self.assertEqual(metrics["changed_spans"], 2)


class ResearchHoldoutTests(unittest.TestCase):
    PILOT = ROOT / "evals/research-v4/holdout-01-pubmed-canonical.json"
    PREREG = ROOT / "evals/research-v4/holdout-01-preregistration.json"

    def holdout_two_result(self) -> Path:
        return ROOT / "evals/research-v4/holdout-02-result.json"

    def copied_holdout_two(self, root: Path, data: dict) -> Path:
        prereg = ROOT / "evals/research-v4/holdout-02-preregistration.json"
        (root / prereg.name).write_bytes(prereg.read_bytes())
        result = root / "result.json"
        result.write_text(json.dumps(data), encoding="utf-8")
        return result

    def copied_holdout_three_prereg(self, root: Path, data: dict) -> Path:
        source = ROOT / "evals/research-v4"
        research_dir = root / "evals/research-v4"
        assets_dir = root / "assets"
        research_dir.mkdir(parents=True)
        assets_dir.mkdir(parents=True)
        (assets_dir / "service-registry.json").write_bytes(
            (ROOT / "assets/service-registry.json").read_bytes()
        )
        for name in (
            "micro-02-result.json",
            "holdout-03-corpus-manifest.json",
            "news-quote-01-holdout-plan.json",
            "news-quote-02-holdout-plan.json",
            "news-quote-03-holdout-plan.json",
        ):
            (research_dir / name).write_bytes((source / name).read_bytes())
        prereg = research_dir / "holdout-03-preregistration.json"
        prereg.write_text(json.dumps(data), encoding="utf-8")
        return prereg

    def copied_holdout_three_partial(self, root: Path, data: dict) -> Path:
        source = ROOT / "evals/research-v4"
        prereg_data = json.loads(
            (source / "holdout-03-preregistration.json").read_text(
                encoding="utf-8"
            )
        )
        prereg = self.copied_holdout_three_prereg(root, prereg_data)
        prereg.write_bytes(
            (source / "holdout-03-preregistration.json").read_bytes()
        )
        result = prereg.parent / "partial.json"
        result.write_text(json.dumps(data), encoding="utf-8")
        return result

    def test_quote_integrity_holdout_three_is_frozen_and_registry_bound(
        self,
    ) -> None:
        path = ROOT / "evals/research-v4/holdout-03-preregistration.json"
        data = research_holdout.validate_preregistration(path)
        self.assertEqual(
            [plan["sample"] for plan in data["plans"]],
            ["news-quote-01", "news-quote-02", "news-quote-03"],
        )
        self.assertEqual(
            {service["id"] for service in data["services"]["primary_effect"]},
            {"zerogpt", "copyleaks"},
        )
        self.assertEqual(
            data["success_criteria"]["transfer_signal"],
            (
                "All three holdout samples satisfy sample_success; two of three "
                "is reported as partial 66.7%, not rounded up to the protocol's "
                "70% requirement."
            ),
        )
        self.assertTrue(all(plan["edit_cost"] <= 0.08 for plan in data["plans"]))

    def test_quote_integrity_holdout_three_rejects_forged_service_group(
        self,
    ) -> None:
        source = ROOT / "evals/research-v4/holdout-03-preregistration.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        data["services"]["primary_effect"][1]["independence_group"] = "zerogpt"
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_holdout_three_prereg(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "forged independence group"):
                research_holdout.validate_preregistration(path)

    def test_quote_integrity_holdout_three_rejects_forged_candidate_binding(
        self,
    ) -> None:
        source = ROOT / "evals/research-v4/holdout-03-preregistration.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        data["plans"][0]["candidate_sha256"] = "f" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_holdout_three_prereg(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "quote operation mismatch"):
                research_holdout.validate_preregistration(path)

    def test_quote_integrity_partial_result_rejects_transfer(self) -> None:
        path = ROOT / "evals/research-v4/holdout-03-partial-result.json"
        data = research_holdout.load_partial_result(path)
        self.assertFalse(data["analysis"]["confirmatory_holdout_completed"])
        self.assertFalse(data["analysis"]["primary_pair_available"])
        self.assertTrue(data["analysis"]["zerogpt_transfer_rejected"])
        self.assertEqual(data["analysis"]["zerogpt_successful_samples"], 0)
        self.assertFalse(data["analysis"]["production_rule_admitted"])
        self.assertTrue(
            all(
                row["status"] == "failed_no_effect_above_noise"
                for row in data["analysis"]["sample_results"]
            )
        )

    def test_quote_integrity_partial_result_rejects_forged_success(self) -> None:
        source = ROOT / "evals/research-v4"
        data = json.loads(
            (source / "holdout-03-partial-result.json").read_text(encoding="utf-8")
        )
        data["analysis"]["zerogpt_successful_samples"] = 3
        with tempfile.TemporaryDirectory() as directory:
            result = self.copied_holdout_three_partial(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "does not recompute"):
                research_holdout.load_partial_result(result)

    def test_quote_integrity_partial_result_rejects_invented_timestamp(
        self,
    ) -> None:
        source = ROOT / "evals/research-v4"
        data = json.loads(
            (source / "holdout-03-partial-result.json").read_text(encoding="utf-8")
        )
        data["observations"][0]["observed_at"] = "2026-07-30T20:00:00+00:00"
        with tempfile.TemporaryDirectory() as directory:
            result = self.copied_holdout_three_partial(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "must not invent"):
                research_holdout.load_partial_result(result)

    def test_direct_claim_holdout_is_frozen_on_new_strict_texts(self) -> None:
        research_dir = ROOT / "evals/research-v4"
        prereg = json.loads(
            (research_dir / "holdout-02-preregistration.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            prereg["schema"],
            "palimpsest.holdout-preregistration.v2",
        )
        self.assertEqual(prereg["status"], "frozen_before_live_scores")
        self.assertEqual(
            prereg["calibration_binding"]["git_commit"],
            "f0efab0d41781d4df28d01d22e470757a3dd8d0d",
        )
        for binding_name in ("calibration_binding", "corpus_binding"):
            binding = prereg[binding_name]
            path = research_dir / binding["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                binding["sha256"],
            )
        corpus = json.loads(
            (research_dir / prereg["corpus_binding"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(len(corpus["samples"]), 4)
        self.assertTrue(
            all(sample["partition"] == "holdout" for sample in corpus["samples"])
        )
        self.assertEqual(
            {sample["topic_pair"] for sample in corpus["samples"]},
            {"arxiv-polish-02", "news-polish-02"},
        )
        self.assertEqual(len(prereg["plans"]), 2)
        for binding in prereg["plans"]:
            plan_path = research_dir / binding["path"]
            self.assertEqual(
                hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                binding["sha256"],
            )
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["original_sha256"], binding["ai_sha256"])
            self.assertEqual(plan["reference_sha256"], binding["human_sha256"])
            self.assertEqual(len(plan["operations"]), 1)
            self.assertEqual(
                plan["operations"][0]["factor"],
                "direct_claim_restoration",
            )
            self.assertLessEqual(binding["edit_cost"], 0.18)
            self.assertEqual(binding["quality"]["fidelity_screen"], "pass")
            self.assertEqual(binding["quality"]["english_level"], "pass_C2")
            self.assertTrue(
                binding["quality"]["semantic_review"].startswith("pass_")
            )
        procedure = " ".join(prereg["procedure"])
        self.assertIn("transition signal", procedure)
        self.assertIn("Do not create, alter, combine, or replace", procedure)
        self.assertIn(
            "additional independent detector group",
            prereg["success_criteria"]["production_admission"],
        )

    def test_direct_claim_holdout_rejects_transfer(self) -> None:
        data = research_holdout.load_result(self.holdout_two_result())
        results = {
            row["sample"]: row for row in data["analysis"]["sample_results"]
        }
        self.assertEqual(
            results["arxiv-polish-02"]["status"],
            "ineligible_zerogpt_baseline_below_20",
        )
        self.assertEqual(
            results["news-polish-02"]["status"],
            "failed_no_effect_above_noise",
        )
        self.assertEqual(
            results["news-polish-02"]["zerogpt_human"]["median_pct"],
            results["news-polish-02"]["zerogpt_baseline"]["median_pct"],
        )
        self.assertEqual(data["analysis"]["successful_samples"], 0)
        self.assertFalse(data["analysis"]["holdout_success"])
        self.assertFalse(data["analysis"]["production_rule_admitted"])

    def test_direct_claim_holdout_rejects_missing_transition(self) -> None:
        data = json.loads(
            self.holdout_two_result().read_text(encoding="utf-8")
        )
        data["observations"][0]["transition_signals"][1] = "missing"
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_holdout_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "transition signal"):
                research_holdout.load_result(path)

    def test_direct_claim_holdout_rejects_forged_success(self) -> None:
        data = json.loads(
            self.holdout_two_result().read_text(encoding="utf-8")
        )
        data["analysis"]["successful_samples"] = 2
        data["analysis"]["holdout_success"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_holdout_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "does not recompute"):
                research_holdout.load_result(path)

    def test_direct_claim_holdout_rejects_forged_text_binding(self) -> None:
        data = json.loads(
            self.holdout_two_result().read_text(encoding="utf-8")
        )
        data["observations"][0]["post_visible_text_sha256"] = "f" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_holdout_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "not bound"):
                research_holdout.load_result(path)

    def test_direct_claim_holdout_rejects_included_click_timeout(self) -> None:
        data = json.loads(
            self.holdout_two_result().read_text(encoding="utf-8")
        )
        data["excluded_technical_attempts"][0]["included_in_analysis"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = self.copied_holdout_two(Path(directory), data)
            with self.assertRaisesRegex(ValueError, "excluded"):
                research_holdout.load_result(path)

    def test_pubmed_holdout_is_preregistered_and_rejects_split_transfer(self) -> None:
        pilot = json.loads(self.PILOT.read_text(encoding="utf-8"))
        self.assertEqual(pilot["status"], "completed_holdout")
        self.assertEqual(
            pilot["preregistration"]["sha256"],
            hashlib.sha256(self.PREREG.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            pilot["preregistration"]["git_commit_before_live_scores"],
            "0adc16146030a830e5b606fea4ace4f8b975627b",
        )
        candidates = pilot["candidates"]
        confirmatory = [
            candidate
            for candidate in candidates.values()
            if candidate.get("role") == "confirmatory"
        ]
        self.assertEqual(len(confirmatory), 2)
        self.assertTrue(
            all(
                candidate["quality"]["status"] == "rejected"
                and candidate["quality"]["failed_signal"] == "reading_grade"
                for candidate in confirmatory
            )
        )
        observed_candidates = {
            observation["candidate"] for observation in pilot["observations"]
        }
        self.assertTrue(
            all(
                candidate_id not in observed_candidates
                for candidate_id, candidate in candidates.items()
                if candidate.get("role") == "confirmatory"
            )
        )
        self.assertEqual(
            pilot["holdout_transfer"]["successful_samples"],
            0,
        )
        self.assertFalse(pilot["holdout_transfer"]["transfer_confirmed"])
        self.assertFalse(pilot["admission"]["rule_admitted"])
        computed = research_pilot.recompute_holdout_transfer(pilot)
        self.assertEqual(
            {
                sample: result["status"]
                for sample, result in computed["sample_results"].items()
            },
            {
                "pubmed-03": "failed_before_live_scan",
                "pubmed-04": "failed_before_live_scan",
            },
        )
        pareto = research_pilot.validate_declared_pareto(self.PILOT)
        self.assertEqual(
            pareto["eligible_candidates"],
            ["p03-baseline", "p04-baseline"],
        )

    def test_pubmed_holdout_records_human_false_positives_and_saturation(
        self,
    ) -> None:
        pilot = json.loads(self.PILOT.read_text(encoding="utf-8"))

        def scores(candidate: str, service: str) -> list[float]:
            matches = [
                observation["scores_pct"]
                for observation in pilot["observations"]
                if observation["candidate"] == candidate
                and observation["service"] == service
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        self.assertEqual(scores("p03-baseline", "zerogpt"), [100, 100, 100])
        self.assertEqual(scores("p04-baseline", "scribbr"), [100, 100, 100])
        self.assertEqual(
            scores("p04-human-control", "zerogpt"),
            [42.9, 42.9, 42.9],
        )
        self.assertEqual(scores("p04-human-control", "scribbr"), [0, 0, 0])
        self.assertEqual(scores("p03-human-control", "sapling"), [96.4])
        self.assertEqual(scores("p04-human-control", "sapling"), [100])
        comparators = [
            candidate_id
            for candidate_id, candidate in pilot["candidates"].items()
            if candidate.get("role") == "exploratory_comparator"
        ]
        self.assertTrue(
            all(
                scores(candidate_id, service) == [100]
                for candidate_id in comparators
                for service in ("zerogpt", "scribbr")
            )
        )
        self.assertEqual(pilot["service_errors"][0]["service"], "copyleaks")
        self.assertEqual(pilot["service_errors"][0]["status"], "error")

    def _write_tampered_fixture(self, root: Path, pilot: dict) -> Path:
        (root / self.PREREG.name).write_text(
            self.PREREG.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        destination = root / self.PILOT.name
        destination.write_text(json.dumps(pilot), encoding="utf-8")
        return destination

    def test_holdout_validator_rejects_forged_transfer_success(self) -> None:
        pilot = json.loads(self.PILOT.read_text(encoding="utf-8"))
        pilot["holdout_transfer"]["successful_samples"] = 2
        pilot["holdout_transfer"]["transfer_confirmed"] = True
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_tampered_fixture(Path(temp), pilot)
            with self.assertRaisesRegex(ValueError, "holdout transfer mismatch"):
                research_pilot.validate_declared_pareto(path)

    def test_holdout_validator_rejects_scanning_quality_rejected_h1(self) -> None:
        pilot = json.loads(self.PILOT.read_text(encoding="utf-8"))
        candidate_id = "p03-h1-split-adaptive-mechanism"
        pilot["observations"].append(
            {
                "candidate": candidate_id,
                "service": "zerogpt",
                "scores_pct": [0],
                "post_visible_text_sha256": pilot["candidates"][candidate_id][
                    "canonical_sha256"
                ],
                "terminal_state": "complete",
            }
        )
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_tampered_fixture(Path(temp), pilot)
            with self.assertRaisesRegex(
                ValueError, "quality-rejected confirmatory candidate was scanned"
            ):
                research_pilot.validate_declared_pareto(path)


class ResearchMatrixTests(unittest.TestCase):
    def fixture(
        self,
        root: Path,
        stale: bool = False,
        minimum_repeats: int = 1,
    ) -> Path:
        original_text = "Alpha beta gamma delta."
        edited_text = "Alpha beta gamma epsilon."
        original = root / "original.txt"
        edited = root / "edited.txt"
        original.write_text(original_text, encoding="utf-8")
        edited.write_text(edited_text, encoding="utf-8")
        original_hash = digest(original_text)
        edited_hash = digest(edited_text)
        observations = []
        for service in ("zerogpt", "copyleaks"):
            observations.extend(
                [
                    {
                        "candidate_id": "base",
                        "service": service,
                        "repeat": 1,
                        "status": "scored",
                        "terminal_state": "complete",
                        "post_visible_text_sha256": original_hash,
                        "score_pct": 80,
                        "capture_status": "missing",
                    },
                    {
                        "candidate_id": "edited",
                        "service": service,
                        "repeat": 1,
                        "status": "scored",
                        "terminal_state": "complete",
                        "post_visible_text_sha256": (
                            original_hash if stale else edited_hash
                        ),
                        "score_pct": 10,
                        "capture_status": "missing",
                    },
                ]
            )
        experiment = {
            "schema": "palimpsest.detector-research.v2",
            "experiment_id": "unit",
            "canonicalization": "plain_text_v1",
            "original": {"path": "original.txt", "sha256": original_hash},
            "policy": {
                "mandatory_services": ["zerogpt", "copyleaks"],
                "hard_threshold_pct": 20,
                "minimum_repeats": minimum_repeats,
            },
            "candidates": [
                {
                    "id": "base",
                    "operation": "none",
                    "quality_status": "pass",
                    "path": "original.txt",
                    "sha256": original_hash,
                },
                {
                    "id": "edited",
                    "operation": "one-factor",
                    "quality_status": "pass",
                    "path": "edited.txt",
                    "sha256": edited_hash,
                },
            ],
            "observations": observations,
        }
        path = root / "experiment.json"
        path.write_text(json.dumps(experiment), encoding="utf-8")
        return path

    def test_frontier_selects_least_changed_complete_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = research_matrix.summarize(self.fixture(Path(temp)))
            self.assertEqual(result["least_changed_hard_pass"], "edited")
            self.assertIn("base", result["pareto_frontier"])
            self.assertIn("edited", result["pareto_frontier"])

    def test_matrix_rejects_stale_visible_text_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "post-terminal visible text hash"):
                research_matrix.summarize(self.fixture(Path(temp), stale=True))

    def test_matrix_does_not_pass_below_minimum_repeats(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = research_matrix.summarize(
                self.fixture(Path(temp), minimum_repeats=2)
            )
            edited = next(row for row in result["rows"] if row["id"] == "edited")
            self.assertFalse(edited["hard_pass"])
            self.assertEqual(
                edited["insufficient_repeats"]["zerogpt"],
                {"observed": 1, "required": 2},
            )
            self.assertIsNone(result["least_changed_hard_pass"])


class ShadowCaseTests(unittest.TestCase):
    def build_case(
        self,
        root: Path,
        *,
        privacy_mode: str = "delivery_only",
        evidence_tier: str = "delivery_diagnostic",
        record_observations: bool = True,
    ) -> Path:
        original = root / "original.md"
        candidate = root / "candidate.md"
        original.write_text(
            "The review may identify a bounded effect. Evidence remains limited.",
            encoding="utf-8",
        )
        candidate.write_text(
            "The review may identify a bounded effect; evidence remains limited.",
            encoding="utf-8",
        )
        case = root / "shadow" / "case.json"
        shadow_case.init_case(
            SimpleNamespace(
                case=case,
                case_id="unit-en-001",
                original=original,
                language="en",
                genre="technical_report",
                english_level="B2",
                services="zerogpt,scribbr",
                privacy_mode=privacy_mode,
                evidence_tier=evidence_tier,
                consent_quote=(
                    "I explicitly allow aggregate private research metrics."
                    if privacy_mode == "private_research"
                    else ""
                ),
            )
        )
        shadow_case.add_candidate(
            SimpleNamespace(
                case=case,
                candidate=candidate,
                id="C001",
                hypothesis_id="punctuation_repair",
                operation_summary=(
                    "Replaced one sentence boundary with source-compatible punctuation."
                ),
                quality_status="pass",
                fidelity_evidence=(
                    "Both clauses, modality and evidence limitation remain unchanged."
                ),
                style_evidence=(
                    "The compact coordination remains inside the source style envelope."
                ),
                english_level_evidence=(
                    "Vocabulary and syntax remain at the source-relative B2 level."
                ),
            )
        )
        shadow_case.freeze_case(case)
        frozen_at = json.loads(case.read_text(encoding="utf-8"))["freeze"][
            "frozen_at"
        ]
        hashes = {
            "baseline": digest(original.read_text(encoding="utf-8")),
            "C001": digest(candidate.read_text(encoding="utf-8")),
        }
        if not record_observations:
            return case
        scores = {
            ("baseline", "zerogpt"): 80,
            ("baseline", "scribbr"): 70,
            ("C001", "zerogpt"): 10,
            ("C001", "scribbr"): 15,
        }
        repeats = 3 if evidence_tier == "research_candidate" else 1
        index = 0
        for (candidate_id, service), score in scores.items():
            for repeat in range(1, repeats + 1):
                evidence = root / f"source-evidence-{index}.json"
                evidence.write_text(
                    json.dumps(
                        {
                            "service": service,
                            "candidate_id": candidate_id,
                            "repeat": repeat,
                            "visible_result": f"{score}% AI",
                        }
                    ),
                    encoding="utf-8",
                )
                observation = root / f"observation-{index}.json"
                observation.write_text(
                    json.dumps(
                        {
                            "schema": "palimpsest.shadow-observation.v1",
                            "candidate_id": candidate_id,
                            "service": service,
                            "repeat": repeat,
                            "status": "scored",
                            "candidate_sha256": hashes[candidate_id],
                            "post_visible_text_sha256": hashes[candidate_id],
                            "score_pct": score,
                            "terminal_state": "complete",
                            "transition_signal": "loading_or_disabled_observed",
                            "observed_at": frozen_at,
                            "result_url": (
                                "https://www.zerogpt.com/"
                                if service == "zerogpt"
                                else "https://www.scribbr.com/ai-detector/"
                            ),
                            "visible_result_excerpt": (
                                f"Visible result: {score}% AI."
                            ),
                            "evidence": {
                                "kind": "browser_session_record",
                                "path": shadow_case.relative_path(
                                    evidence,
                                    case.parent,
                                ),
                                "sha256": shadow_case.file_sha256(evidence),
                            },
                            "capture_status": "missing",
                            "capture_limitation": (
                                "DOM result was preserved but screenshot capture "
                                "timed out."
                            ),
                        }
                    ),
                    encoding="utf-8",
                )
                shadow_case.record_observation(case, observation)
                index += 1
        return case

    def test_shadow_case_selects_least_changed_complete_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = shadow_case.summarize(self.build_case(Path(directory)))
            self.assertEqual(result["least_changed_hard_pass"], "C001")
            self.assertIn("C001", result["pareto_frontier"])
            self.assertFalse(
                result["research_admission"]["eligible_for_aggregate_review"]
            )
            self.assertFalse(
                result["research_admission"]["production_rule_admitted"]
            )

    def test_shadow_case_freeze_rejects_post_score_candidate_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.build_case(Path(directory))
            data = json.loads(case.read_text(encoding="utf-8"))
            data["candidates"][1]["hypothesis_id"] = "post_score_relabel"
            case.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest-frozen"):
                shadow_case.summarize(case)

    def test_shadow_private_research_full_matrix_is_aggregate_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = shadow_case.summarize(
                self.build_case(
                    Path(directory),
                    privacy_mode="private_research",
                    evidence_tier="research_candidate",
                )
            )
            self.assertTrue(
                result["research_admission"]["eligible_for_aggregate_review"]
            )
            self.assertFalse(
                result["research_admission"]["production_rule_admitted"]
            )

    def test_shadow_prepare_observation_and_terminal_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.build_case(root, record_observations=False)
            template_path = root / "prepared.json"
            template = shadow_case.prepare_observation(
                SimpleNamespace(
                    case=case,
                    candidate_id="baseline",
                    service="zerogpt",
                    repeat=1,
                    out=template_path,
                )
            )
            data = json.loads(case.read_text(encoding="utf-8"))
            self.assertEqual(
                template["candidate_sha256"],
                data["original"]["sha256"],
            )
            self.assertEqual(template["result_url"], "https://www.zerogpt.com/")
            evidence = root / "source-evidence.json"
            evidence.write_text('{"visible_result":"80% AI"}', encoding="utf-8")
            template.update(
                {
                    "status": "scored",
                    "post_visible_text_sha256": template["candidate_sha256"],
                    "score_pct": 80,
                    "terminal_state": "complete",
                    "transition_signal": "loading_or_disabled_observed",
                    "observed_at": data["freeze"]["frozen_at"],
                    "visible_result_excerpt": "Visible result: 80% AI.",
                    "evidence": {
                        "kind": "browser_session_record",
                        "path": shadow_case.relative_path(evidence, case.parent),
                        "sha256": shadow_case.file_sha256(evidence),
                    },
                    "capture_status": "missing",
                    "capture_limitation": (
                        "DOM result was preserved but screenshot capture timed out."
                    ),
                }
            )
            template_path.write_text(json.dumps(template), encoding="utf-8")
            shadow_case.record_observation(case, template_path)
            with self.assertRaisesRegex(ValueError, "full quality-pass matrix"):
                shadow_case.seal_case(case, "completed", "")
            sealed = shadow_case.seal_case(
                case,
                "stopped",
                "The selected detector matrix was intentionally stopped early.",
            )
            self.assertEqual(sealed["status"], "stopped")
            result = shadow_case.summarize(case)
            self.assertTrue(result["lifecycle"]["sealed"])
            self.assertEqual(result["lifecycle"]["outcome"], "stopped")

    def test_shadow_completed_seal_detects_post_seal_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.build_case(Path(directory))
            shadow_case.seal_case(case, "completed", "")
            result = shadow_case.summarize(case)
            self.assertEqual(result["lifecycle"]["outcome"], "completed")
            data = json.loads(case.read_text(encoding="utf-8"))
            data["observations"][0]["score_pct"] = 0
            case.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "seal is missing or stale"):
                shadow_case.summarize(case)

    def test_shadow_case_rejects_tampered_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.build_case(Path(directory))
            data = json.loads(case.read_text(encoding="utf-8"))
            evidence_path = shadow_case.resolve_case_file(
                case,
                data["observations"][0]["evidence"]["path"],
            )
            evidence_path.write_text('{"forged": true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence hash mismatch"):
                shadow_case.summarize(case)

    def test_shadow_private_research_requires_consent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.md"
            original.write_text("A private source text.", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "specific 20"):
                shadow_case.init_case(
                    SimpleNamespace(
                        case=root / "case.json",
                        case_id="unit-en-002",
                        original=original,
                        language="en",
                        genre="report",
                        english_level="B2",
                        services="zerogpt,scribbr",
                        privacy_mode="private_research",
                        evidence_tier="research_candidate",
                        consent_quote="",
                    )
                )

    def test_shadow_research_candidate_needs_independent_groups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.md"
            original.write_text("A private source text.", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "two independent"):
                shadow_case.init_case(
                    SimpleNamespace(
                        case=root / "case.json",
                        case_id="unit-en-003",
                        original=original,
                        language="en",
                        genre="report",
                        english_level="B2",
                        services="zerogpt,gptinf",
                        privacy_mode="private_research",
                        evidence_tier="research_candidate",
                        consent_quote=(
                            "I explicitly allow aggregate private research metrics."
                        ),
                    )
                )
