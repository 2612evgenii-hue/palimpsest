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
import research_variants  # noqa: E402


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ResearchCorpusTests(unittest.TestCase):
    def test_manifest_has_pinned_balanced_pairs_and_real_holdout(self) -> None:
        manifest = json.loads(
            (ROOT / "evals/research-v4/corpus-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema"], "palimpsest.research-corpus.v2")
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

    def test_b1_pilot_is_bound_and_rejects_cross_detector_regression(self) -> None:
        pilot = json.loads(
            (ROOT / "evals/research-v4/pilot-02-b1.json").read_text(encoding="utf-8")
        )
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

    def test_surface_metric_counts_punctuation_only_edit(self) -> None:
        metrics = research_variants.character_change_metrics(
            "One frame. Another follows.",
            "One frame: another follows.",
        )
        self.assertGreater(metrics["char_change_ratio"], 0)
        self.assertEqual(metrics["changed_spans"], 2)


class ResearchMatrixTests(unittest.TestCase):
    def fixture(self, root: Path, stale: bool = False) -> Path:
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
                        "visible_text_sha256": original_hash,
                        "score_pct": 80,
                        "capture_status": "missing",
                    },
                    {
                        "candidate_id": "edited",
                        "service": service,
                        "repeat": 1,
                        "status": "scored",
                        "terminal_state": "complete",
                        "visible_text_sha256": original_hash if stale else edited_hash,
                        "score_pct": 10,
                        "capture_status": "missing",
                    },
                ]
            )
        experiment = {
            "schema": "palimpsest.detector-research.v1",
            "experiment_id": "unit",
            "original": {"path": "original.txt", "sha256": original_hash},
            "policy": {
                "mandatory_services": ["zerogpt", "copyleaks"],
                "hard_threshold_pct": 20,
            },
            "candidates": [
                {
                    "id": "base",
                    "operation": "none",
                    "path": "original.txt",
                    "sha256": original_hash,
                },
                {
                    "id": "edited",
                    "operation": "one-factor",
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
            with self.assertRaisesRegex(ValueError, "visible text hash"):
                research_matrix.summarize(self.fixture(Path(temp), stale=True))
