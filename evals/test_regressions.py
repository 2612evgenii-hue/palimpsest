#!/usr/bin/env python3
"""Broad functional regression layer for Palimpsest v3.5."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "evals" / "fixtures"
PATTERN = SCRIPTS / "pattern_scan.py"
STYLE_METRICS = SCRIPTS / "style_metrics.py"
STYLE_DISTANCE = SCRIPTS / "style_distance.py"
MINIMALITY = SCRIPTS / "minimality.py"
FIDELITY = SCRIPTS / "fidelity_check.py"
ANNOTATIONS = SCRIPTS / "annotations.py"
SEGMENT = SCRIPTS / "segment.py"
MEMORY = SCRIPTS / "memory.py"
OVERLAP = SCRIPTS / "source_overlap.py"
ENGLISH_LEVEL = SCRIPTS / "english_level.py"
sys.path.insert(0, str(SCRIPTS))
import state as STATE_MODULE  # noqa: E402


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
    )


def data(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(proc.stdout + proc.stderr) from exc


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class FixtureSensitivityTests(unittest.TestCase):
    def scan(self, name: str) -> dict:
        proc = run(PATTERN, FIXTURES / name, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return data(proc)

    def test_english_ai_fixture_is_high_signal(self) -> None:
        result = self.scan("ai-en.md")
        self.assertGreaterEqual(result["advisory_ai_smell"], 90)
        self.assertGreater(result["counts"]["P0"], 0)

    def test_russian_ai_fixture_is_high_signal(self) -> None:
        result = self.scan("ai-ru.md")
        self.assertGreaterEqual(result["advisory_ai_smell"], 90)
        self.assertGreater(result["counts"]["P0"], 0)

    def test_human_reference_stays_low_signal(self) -> None:
        result = self.scan("reference-ru.md")
        self.assertLess(result["advisory_ai_smell"], 15)
        self.assertEqual(result["counts"]["P0"], 0)

    def test_minimal_edit_reduces_ai_smell_without_claiming_authorship(self) -> None:
        original = self.scan("ai-ru.md")
        edited = self.scan("edited-minimal-ru.md")
        self.assertLess(edited["advisory_ai_smell"], original["advisory_ai_smell"])
        self.assertEqual(edited["counts"]["P0"], 0)


PATTERN_CASES = {
    "en_delve": ("The report will delve into the evidence.", "EN-L1-delve"),
    "en_tapestry": ("The city forms a rich tapestry of cultures.", "EN-L1-tapestry"),
    "en_testament": ("This outcome is a testament to teamwork.", "EN-L1-testament"),
    "en_landscape": ("The evolving landscape affects planning.", "EN-L1-landscape"),
    "en_worth_noting": ("It is worth noting that the result changed.", "EN-L1-worthnoting"),
    "en_not_only": ("It is not only useful but also reliable.", "EN-S-notbut"),
    "en_chatbot": ("As an AI, I hope this helps.", "EN-ART-chatbot"),
    "ru_note": ("Стоит отметить, что результат изменился.", "RU-L1-stoitotmetit"),
    "ru_thus": ("Таким образом, задача завершена.", "RU-L1-takimobrazom"),
    "ru_role": ("Метод играет важную роль в анализе.", "RU-L1-igraetrol"),
    "ru_copula": ("Проект является основой отчёта.", "RU-L1-yavlyaetsya"),
    "ru_chatbot": ("Как ИИ, я надеюсь, это поможет.", "RU-ART-chatbot"),
}


class PatternCaseTests(unittest.TestCase):
    pass


def make_pattern_test(text: str, expected: str):
    def test(self: unittest.TestCase) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = write(Path(raw) / "sample.md", text + "\n")
            proc = run(PATTERN, path, "--json")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            ids = {item["id"] for item in data(proc)["findings"]}
            self.assertIn(expected, ids)

    return test


for case_name, (case_text, case_expected) in PATTERN_CASES.items():
    setattr(PatternCaseTests, f"test_{case_name}", make_pattern_test(case_text, case_expected))


class ProtectedTextTests(unittest.TestCase):
    def test_inline_code_is_not_scanned_as_prose(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = write(Path(raw) / "sample.md", "Use `delve into the evidence` as a literal test value.\n")
            ids = {item["id"] for item in data(run(PATTERN, path, "--json"))["findings"]}
            self.assertNotIn("EN-L1-delve", ids)

    def test_fenced_code_is_not_scanned_as_prose(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = write(Path(raw) / "sample.md", "```text\nIt is worth noting.\n```\n")
            ids = {item["id"] for item in data(run(PATTERN, path, "--json"))["findings"]}
            self.assertNotIn("EN-L1-worthnoting", ids)

    def test_url_and_latex_are_fidelity_protected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(root / "o.md", "See https://example.com/a and use $x = 1$.\n")
            edited = write(root / "e.md", "See https://example.com/b and use $x = 2$.\n")
            proc = run(FIDELITY, "--original", original, "--edited", edited, "--json")
            self.assertEqual(proc.returncode, 1)
            codes = {item["code"] for item in data(proc)["findings"]}
            self.assertIn("URL_CHANGED", codes)
            self.assertIn("LATEX_CHANGED", codes)


class MinimalityTests(unittest.TestCase):
    def test_unchanged_text_is_zero(self) -> None:
        proc = run(
            MINIMALITY,
            "--original",
            FIXTURES / "ai-ru.md",
            "--current",
            FIXTURES / "ai-ru.md",
            "--json",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data(proc)["doc_change_ratio"], 0)

    def test_minimal_fixture_is_inside_explicit_budget(self) -> None:
        proc = run(
            MINIMALITY,
            "--original",
            FIXTURES / "ai-ru.md",
            "--current",
            FIXTURES / "edited-minimal-ru.md",
            "--budget",
            "0.5",
            "--para-budget",
            "1",
            "--json",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertAlmostEqual(data(proc)["doc_change_ratio"], 0.2927, places=4)

    def test_rewrite_fixture_exceeds_budget(self) -> None:
        proc = run(
            MINIMALITY,
            "--original",
            FIXTURES / "ai-ru.md",
            "--current",
            FIXTURES / "edited-ru.md",
            "--budget",
            "0.5",
            "--para-budget",
            "1",
            "--json",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertGreater(data(proc)["doc_change_ratio"], 0.6)

    def test_added_paragraph_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(root / "o.md", "One stable paragraph remains here.\n")
            edited = write(root / "e.md", "One stable paragraph remains here.\n\nA new paragraph is visible.\n")
            result = data(
                run(
                    MINIMALITY,
                    "--original",
                    original,
                    "--current",
                    edited,
                    "--budget",
                    "1",
                    "--para-budget",
                    "1",
                    "--json",
                )
            )
            self.assertEqual(result["paragraphs"]["added"], 1)


class AnnotationTests(unittest.TestCase):
    def test_valid_fixture_has_no_parser_errors(self) -> None:
        proc = run(ANNOTATIONS, FIXTURES / "annotated-ru.md", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = data(proc)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["marks"]), 6)

    def test_broken_fixture_is_rejected(self) -> None:
        proc = run(ANNOTATIONS, FIXTURES / "annotated-broken-ru.md", "--validate")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ошиб", proc.stdout)

    def test_check_clean_rejects_working_marks(self) -> None:
        proc = run(ANNOTATIONS, FIXTURES / "annotated-ru.md", "--check-clean")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("NOT CLEAN", proc.stdout)

    def test_strip_removes_all_markers(self) -> None:
        proc = run(ANNOTATIONS, FIXTURES / "annotated-ru.md", "--strip")
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("⟦", proc.stdout)
        self.assertNotIn("⟧", proc.stdout)


class StyleTests(unittest.TestCase):
    def test_profile_schema_has_all_feature_groups(self) -> None:
        proc = run(STYLE_METRICS, FIXTURES / "reference-ru.md", "--json")
        self.assertEqual(proc.returncode, 0)
        profile = data(proc)
        for key in (
            "sentence_length", "paragraph", "lexicon", "discourse",
            "punctuation_per_1000w", "specificity", "repetition",
        ):
            self.assertIn(key, profile)

    def test_identical_text_has_zero_distance(self) -> None:
        proc = run(
            STYLE_DISTANCE,
            "--ref",
            FIXTURES / "reference-ru.md",
            "--cand",
            FIXTURES / "reference-ru.md",
            "--json",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data(proc)["distance"], 0)

    def test_baseline_reports_improvement_direction(self) -> None:
        proc = run(
            STYLE_DISTANCE,
            "--ref",
            FIXTURES / "reference-ru.md",
            "--cand",
            FIXTURES / "edited-ru.md",
            "--baseline",
            FIXTURES / "ai-ru.md",
            "--json",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("improvement", data(proc))

    def test_gate_can_reject_distant_candidate(self) -> None:
        proc = run(
            STYLE_DISTANCE,
            "--ref",
            FIXTURES / "reference-ru.md",
            "--cand",
            FIXTURES / "ai-en.md",
            "--gate",
            "10",
            "--json",
        )
        self.assertEqual(proc.returncode, 1)

    def test_state_policy_rejects_reliable_source_style_drift(self) -> None:
        ok, details = STATE_MODULE.assess_style_metric(
            {"style_mode": "source_as_reference"},
            {"reliability": "ok", "distance": 29},
        )
        self.assertFalse(ok)
        self.assertIn("28-point preservation ceiling", details[0])

    def test_state_policy_rejects_external_reference_regression(self) -> None:
        ok, details = STATE_MODULE.assess_style_metric(
            {"style_mode": "external_reference"},
            {
                "reliability": "ok",
                "distance": 20,
                "improvement": -0.1,
            },
        )
        self.assertFalse(ok)
        self.assertIn("must not be negative", details[1])

    def test_short_style_metric_is_explicitly_advisory(self) -> None:
        ok, details = STATE_MODULE.assess_style_metric(
            {"style_mode": "source_as_reference"},
            {
                "reliability": "low: short text",
                "distance": 80,
            },
        )
        self.assertTrue(ok)
        self.assertIn("advisory only", details[0])


class FidelityRegressionTests(unittest.TestCase):
    def fidelity(self, original: str, edited: str) -> tuple[int, set[str]]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            o = write(root / "o.md", original + "\n")
            e = write(root / "e.md", edited + "\n")
            proc = run(FIDELITY, "--original", o, "--edited", e, "--json")
            return proc.returncode, {item["code"] for item in data(proc)["findings"]}

    def test_safe_local_copy_passes(self) -> None:
        rc, codes = self.fidelity("The measured value was 12 kg.", "The measured value was 12 kg.")
        self.assertEqual(rc, 0)
        self.assertEqual(codes, set())

    def test_number_loss_is_rejected(self) -> None:
        rc, codes = self.fidelity("The result increased by 12%.", "The result increased.")
        self.assertEqual(rc, 1)
        self.assertIn("NUMBER_SET_CHANGED", codes)

    def test_number_reassignment_is_rejected(self) -> None:
        rc, codes = self.fidelity(
            "Group A reached 12%, while group B reached 18%.",
            "Group A reached 18%, while group B reached 12%.",
        )
        self.assertEqual(rc, 1)
        self.assertIn("NUMBER_ORDER_CHANGED", codes)

    def test_negation_loss_is_rejected(self) -> None:
        rc, codes = self.fidelity(
            "The report does not establish causation.",
            "The report establishes causation.",
        )
        self.assertEqual(rc, 1)
        self.assertIn("NEGATION_CHANGED", codes)

    def test_citation_change_is_visible(self) -> None:
        rc, codes = self.fidelity("The claim is supported [12].", "The claim is supported [13].")
        self.assertEqual(rc, 1)
        self.assertIn("BRACKET_CITATION_CHANGED", codes)


class EnglishLevelTests(unittest.TestCase):
    SOURCE = (
        "I worked on this project for six weeks. The team tested the new schedule "
        "because students needed more time. We found that evening visits increased, "
        "but we cannot say the schedule improved grades."
    )

    def test_unchanged_learner_level_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(root / "o.md", self.SOURCE)
            edited = write(root / "e.md", self.SOURCE)
            proc = run(
                ENGLISH_LEVEL,
                "--original", original,
                "--edited", edited,
                "--target", "B1",
                "--json",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(data(proc)["ok"])

    def test_academic_upgrade_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(root / "o.md", self.SOURCE)
            edited = write(
                root / "e.md",
                (
                    "The longitudinal investigation operationalized a multifactorial "
                    "analytical framework whose methodological sophistication "
                    "substantially exceeded the preliminary exploratory design, "
                    "notwithstanding the epistemological limitations inherent in "
                    "observational inference."
                ),
            )
            proc = run(
                ENGLISH_LEVEL,
                "--original", original,
                "--edited", edited,
                "--target", "B1",
                "--json",
            )
            self.assertEqual(proc.returncode, 1)
            codes = {item["code"] for item in data(proc)["findings"]}
            self.assertIn("ENGLISH_LEVEL_DRIFT", codes)

    def test_mild_one_band_upgrade_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(root / "o.md", self.SOURCE)
            edited = write(
                root / "e.md",
                self.SOURCE.replace("worked", "participated"),
            )
            proc = run(
                ENGLISH_LEVEL,
                "--original",
                original,
                "--edited",
                edited,
                "--target",
                "B2",
                "--json",
            )
            self.assertEqual(proc.returncode, 1)
            result = data(proc)
            self.assertEqual(result["source"]["estimated_cefr"], "B1")
            self.assertEqual(result["edited"]["estimated_cefr"], "B2")
            self.assertIn("estimated_band_shift", result["drift_signals"])

    def test_major_simplification_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "o.md",
                (
                    "Although the observational design cannot establish causation, "
                    "the longitudinal evidence indicates a substantial association "
                    "between sustained participation and improved retention outcomes."
                ),
            )
            edited = write(root / "e.md", "It helped. The result was good.")
            proc = run(
                ENGLISH_LEVEL,
                "--original", original,
                "--edited", edited,
                "--target", "C1",
                "--json",
            )
            self.assertEqual(proc.returncode, 1)
            codes = {item["code"] for item in data(proc)["findings"]}
            self.assertIn("ENGLISH_LEVEL_DRIFT", codes)


class SegmentRegressionTests(unittest.TestCase):
    def make_map(self, root: Path) -> tuple[Path, Path]:
        text = "\n\n".join(
            f"Paragraph {index} contains stable wording for segment regression coverage."
            for index in range(1, 12)
        ) + "\n"
        working = write(root / "working.md", text)
        mapping = root / "SEGMENTS.json"
        proc = run(
            SEGMENT, "map", working, "--out", mapping,
            "--target", "18", "--min", "8", "--max", "28",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return working, mapping

    def test_map_covers_every_character(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            working, mapping = self.make_map(Path(raw))
            result = data(run(SEGMENT, "--map", mapping, "status", "--json"))
            self.assertEqual(result["metrics"]["coverage_pct"], 100.0)
            mapped = json.loads(mapping.read_text(encoding="utf-8"))["segments"]
            self.assertEqual(mapped[0]["start"], 0)
            self.assertEqual(mapped[-1]["end"], len(working.read_text()))
            for left, right in zip(mapped, mapped[1:]):
                self.assertEqual(left["end"], right["start"])

    def test_stale_map_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            working, mapping = self.make_map(Path(raw))
            working.write_text(working.read_text() + "Tail.\n", encoding="utf-8")
            self.assertEqual(run(SEGMENT, "--map", mapping, "status", "--json").returncode, 1)

    def test_sync_preserves_some_ids_and_maps_new_tail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            working, mapping = self.make_map(Path(raw))
            before = data(run(SEGMENT, "--map", mapping, "status", "--json"))
            old_ids = {item["id"] for item in json.loads(mapping.read_text())["segments"]}
            working.write_text(
                working.read_text() + "\nA newly appended paragraph must become visible.\n",
                encoding="utf-8",
            )
            self.assertEqual(
                run(SEGMENT, "--map", mapping, "sync", "--file", working).returncode,
                0,
            )
            after_map = json.loads(mapping.read_text())
            self.assertTrue(old_ids & {item["id"] for item in after_map["segments"]})
            self.assertTrue(
                any(item["new"] or item["changed"] for item in after_map["segments"])
            )
            self.assertEqual(after_map["segments"][-1]["end"], len(working.read_text()))
            self.assertEqual(data(run(SEGMENT, "--map", mapping, "status", "--json"))["metrics"]["coverage_pct"], 100.0)
            self.assertEqual(before["metrics"]["coverage_pct"], 100.0)

    def test_mark_and_next_prioritize_risk(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, mapping = self.make_map(Path(raw))
            first = json.loads(mapping.read_text())["segments"][0]["id"]
            marked = run(
                SEGMENT,
                "--map", mapping,
                "mark", first,
                "--risk", "meaning",
                "--status", "editing",
            )
            self.assertEqual(marked.returncode, 0)
            nxt = run(SEGMENT, "--map", mapping, "next")
            self.assertEqual(nxt.returncode, 0)
            self.assertIn(first, nxt.stdout)

    def test_sample_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, mapping = self.make_map(Path(raw))
            one = run(SEGMENT, "--map", mapping, "sample", "--count", "3", "--json")
            two = run(SEGMENT, "--map", mapping, "sample", "--count", "3", "--json")
            self.assertEqual(one.stdout, two.stdout)


class MemoryRegressionTests(unittest.TestCase):
    def test_literal_recall_does_not_interpret_regex(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write(root / "notes.md", "A literal a+b[1] value remains here.\n")
            proc = run(MEMORY, "--workspace", root, "recall", "a+b[1]")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("a+b[1]", proc.stdout)

    def test_recall_not_found_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            proc = run(MEMORY, "--workspace", raw, "recall", "missing phrase")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("Do not reconstruct it from memory", proc.stdout)

    def test_echoes_detect_edit_amplification(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(root / "o.md", "One stable phrase appears once.\n")
            edited = write(
                root / "e.md",
                "\n\n".join(["One stable phrase appears here."] * 4) + "\n",
            )
            proc = run(
                MEMORY,
                "--workspace",
                root,
                "echoes",
                "--original",
                original,
                "--current",
                edited,
                "--min-count",
                "3",
                "--json",
            )
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(data(proc)["echoes"])

    def test_terms_detect_lost_term(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "o.md",
                "Vectorization vectorization vectorization supports indexing.\n",
            )
            edited = write(root / "e.md", "Indexing remains.\n")
            proc = run(
                MEMORY,
                "--workspace",
                root,
                "terms",
                "--original",
                original,
                "--current",
                edited,
                "--min-count",
                "2",
                "--json",
            )
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(data(proc)["lost"][0]["term"], "vectorization")


class OverlapRegressionTests(unittest.TestCase):
    SOURCE = (
        "The committee reviewed every application in chronological order before "
        "comparing the evidence against published eligibility criteria and recording "
        "a written explanation for each final decision."
    )

    def test_exact_long_run_is_high_risk(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = write(root / "source.md", self.SOURCE)
            draft = write(root / "draft.md", self.SOURCE)
            proc = run(OVERLAP, "--draft", draft, "--source", source, "--json")
            self.assertEqual(proc.returncode, 1)
            self.assertGreater(data(proc)["high_risk_count"], 0)

    def test_quoted_long_run_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = write(root / "source.md", self.SOURCE)
            draft = write(root / "draft.md", f'“{self.SOURCE}”\n')
            proc = run(OVERLAP, "--draft", draft, "--source", source, "--json")
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(data(proc)["high_risk_count"], 0)

    def test_invalid_ngram_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = write(root / "source.md", self.SOURCE)
            draft = write(root / "draft.md", "Different prose.")
            proc = run(OVERLAP, "--draft", draft, "--source", source, "--ngram", "2", "--json")
            self.assertEqual(proc.returncode, 2)


class DocumentationContractTests(unittest.TestCase):
    def test_report_template_has_no_forced_close(self) -> None:
        report = (ROOT / "assets" / "templates" / "REPORT.md").read_text(encoding="utf-8").casefold()
        self.assertNotIn("forced close", report)
        self.assertNotIn("`--force`", report)

    def test_docs_restore_six_service_scope_and_strict_loop(self) -> None:
        texts = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [ROOT / "SKILL.md", *(ROOT / "references").glob("*.md")]
        ).casefold()
        for service in (
            "zerogpt", "gptzero", "scribbr", "quillbot", "gptinf", "copyleaks"
        ):
            self.assertIn(service, texts)
        self.assertIn("score < 20", texts)
        self.assertIn("plateau", texts)
        self.assertIn("не заверш", texts)

    def test_selftest_loads_acceptance_regression_and_stress_layers(self) -> None:
        text = (ROOT / "evals" / "selftest.py").read_text(encoding="utf-8")
        self.assertIn("v3_acceptance", text)
        self.assertIn("test_regressions", text)
        self.assertIn("test_stress", text)


def main() -> int:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
