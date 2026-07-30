#!/usr/bin/env python3
"""Regression tests for the Palimpsest 4.0 research harness."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import research_matrix  # noqa: E402
import research_corpus  # noqa: E402
import research_pilot  # noqa: E402
import research_scout  # noqa: E402
import research_variants  # noqa: E402


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


class ResearchVariantTests(unittest.TestCase):
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
