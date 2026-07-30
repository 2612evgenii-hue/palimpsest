#!/usr/bin/env python3
"""Heterogeneous synthetic long-form and bounded-memory stress for v3.5.

This validates infrastructure behavior at 15k+ words. It is deliberately not
described as proof of book-scale editorial or semantic quality.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STATE = SCRIPTS / "state.py"
SEGMENT = SCRIPTS / "segment.py"
MEMORY = SCRIPTS / "memory.py"


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def longform_block(index: int) -> str:
    templates = [
        (
            "Archive unit {index} describes practical constraints in a regional "
            "catalog project. Staff compared visitor logs with accession notes "
            "before writing a narrow conclusion. The records are observational, "
            "so the section does not attribute the measured change to the revised "
            "schedule. That qualification must remain visible after local editing."
        ),
        (
            "Field note {index} follows a maintenance team across two evening "
            "shifts. A sensor alert, a handwritten checklist, and a delayed repair "
            "ticket disagree on timing. The narrative reports that disagreement "
            "instead of silently resolving it, because chronology is part of the "
            "claim and not decorative background."
        ),
        (
            "Interview set {index} contains three perspectives: a student asked for "
            "longer access, a librarian worried about staffing, and an administrator "
            "requested cost figures. These statements are attributed opinions rather "
            "than verified outcomes. Editing may shorten repetition, but it cannot "
            "convert any speaker's preference into an institutional finding."
        ),
        (
            "Table commentary {index} compares 12 weekly counts, two missing entries, "
            "and a corrected total of 418 visits. The correction was logged after "
            "the initial export. Any revision must preserve both the number and its "
            "status as a correction; otherwise the prose would look cleaner while "
            "reporting a different record."
        ),
        (
            "Method section {index} alternates a short warning with a longer technical "
            "explanation. No causal model was fitted. Although attendance and opening "
            "hours moved together, selection effects and seasonal demand remain "
            "plausible explanations. The varied rhythm is intentional and should not "
            "be flattened into equal-length sentences."
        ),
        (
            "Case fragment {index} opens with an exception. One branch recorded fewer "
            "visits after extending its schedule, while two branches recorded more. "
            "The combined result therefore masks local variation. A summary may state "
            "the aggregate direction only if it retains this exception and avoids a "
            "universal claim."
        ),
        (
            "Source note {index} cites [12], distinguishes a direct quotation from a "
            "close paraphrase, and keeps the URL https://example.com/archive unchanged. "
            "The citation supports the date of the policy, not its effectiveness. "
            "This boundary tests protected strings, attribution, and the temptation "
            "to let a nearby source carry a broader assertion."
        ),
        (
            "Operational log {index} uses a compact sequence: request, review, delay, "
            "decision. The review may reopen if the working digest changes. A later "
            "appendix can add context, but it must not leave an unmapped tail or make "
            "the hot memory grow with every cold note. Those are pipeline invariants, "
            "not conclusions about prose quality."
        ),
    ]
    body = templates[index % len(templates)].format(index=index)
    prefix = f"## Part {index // 25 + 1}\n\n" if index % 25 == 1 else ""
    suffix = (
        "\n\n- preserve the recorded qualification\n"
        "- keep the source boundary explicit"
        if index % 37 == 0
        else ""
    )
    return prefix + body + suffix


class SyntheticLongformStressTests(unittest.TestCase):
    def test_longform_sync_handles_deletion_reorder_and_unicode_tail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            blocks = [longform_block(index) for index in range(1, 321)]
            working = write(root / "working.md", "\n\n".join(blocks) + "\n")
            mapping = root / "SEGMENTS.json"
            mapped = run(
                SEGMENT,
                "map",
                working,
                "--out",
                mapping,
                "--target",
                "700",
                "--min",
                "400",
                "--max",
                "950",
            )
            self.assertEqual(mapped.returncode, 0, mapped.stderr)
            before = json.loads(mapping.read_text(encoding="utf-8"))
            old_ids = {item["id"] for item in before["segments"]}

            mutated = blocks[:75] + blocks[80:]
            mutated[140], mutated[141] = mutated[141], mutated[140]
            mutated[10] = mutated[10].replace(
                "practical constraints",
                "documented practical constraints",
            )
            mutated.append(
                "Unicode tail preserves café, naïve, Москва, and the protected "
                "URL https://example.com/финал without truncation."
            )
            working.write_text("\n\n".join(mutated) + "\n", encoding="utf-8")
            synced = run(
                SEGMENT,
                "--map",
                mapping,
                "sync",
                "--file",
                working,
            )
            self.assertEqual(synced.returncode, 0, synced.stderr)
            status = run(SEGMENT, "--map", mapping, "status", "--json")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(
                json.loads(status.stdout)["metrics"]["coverage_pct"], 100.0
            )

            text = working.read_text(encoding="utf-8")
            after = json.loads(mapping.read_text(encoding="utf-8"))
            segments = after["segments"]
            self.assertEqual(len({item["id"] for item in segments}), len(segments))
            self.assertGreaterEqual(
                len(old_ids & {item["id"] for item in segments}),
                8,
            )
            self.assertTrue(any(item["changed"] or item["new"] for item in segments))
            cursor = 0
            for item in segments:
                self.assertEqual(item["start"], cursor)
                body = text[item["start"]:item["end"]]
                self.assertEqual(
                    hashlib.sha256(body.encode("utf-8")).hexdigest(),
                    item["current_sha256"],
                )
                cursor = item["end"]
            self.assertEqual(cursor, len(text))
            self.assertIn("Москва", text[segments[-1]["start"]:])

    def test_longform_edit_sync_sampling_pack_and_memory_are_lossless(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paragraphs = [longform_block(index) for index in range(1, 321)]
            original = write(root / "original.md", "\n\n".join(paragraphs) + "\n")
            working = write(
                root / "working.md",
                original.read_text(encoding="utf-8"),
            )
            self.assertGreater(len(working.read_text(encoding="utf-8").split()), 15000)

            state = root / "STATE.json"
            initialized = run(
                STATE,
                "--state", state,
                "init",
                "--original", original,
                "--working", working,
                "--flags", "none",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            self.assertIn("route=longform", initialized.stdout)
            intake_rows = [
                (
                    "Q1",
                    "The source is the style baseline and its English level is preserved.",
                    "--style-mode", "source_as_reference",
                    "--english-level", "infer_from_source",
                ),
                (
                    "Q2",
                    "No optional functions are enabled in this infrastructure stress test.",
                    "--functions", "none",
                ),
                (
                    "Q3",
                    "No detector services are enabled because F1 is disabled.",
                    "--services", "none",
                ),
                (
                    "Q4",
                    "Preserve all qualifications while exercising the long-form pipeline.",
                ),
            ]
            for row in intake_rows:
                proc = run(
                    STATE,
                    "--state", state,
                    "intake",
                    "--question", row[0],
                    "--answer", row[1],
                    *row[2:],
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)

            mapping = root / "SEGMENTS.json"
            mapped = run(
                SEGMENT,
                "map", working,
                "--out", mapping,
                "--target", "700",
                "--min", "400",
                "--max", "950",
            )
            self.assertEqual(mapped.returncode, 0, mapped.stderr)
            before = json.loads(mapping.read_text(encoding="utf-8"))
            old_ids = {item["id"] for item in before["segments"]}
            self.assertGreaterEqual(len(old_ids), 15)

            paragraphs[159] = paragraphs[159].replace(
                "practical constraints",
                "documented practical constraints",
            )
            paragraphs.extend(longform_block(index) for index in range(321, 326))
            working.write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")
            self.assertEqual(
                run(SEGMENT, "--map", mapping, "status", "--json").returncode,
                1,
            )
            synced = run(
                SEGMENT,
                "--map", mapping,
                "sync",
                "--file", working,
            )
            self.assertEqual(synced.returncode, 0, synced.stderr)
            status = run(SEGMENT, "--map", mapping, "status", "--json")
            self.assertEqual(status.returncode, 0, status.stderr)
            status_data = json.loads(status.stdout)
            self.assertEqual(status_data["metrics"]["coverage_pct"], 100.0)
            self.assertGreater(status_data["metrics"]["changed"], 0)

            after = json.loads(mapping.read_text(encoding="utf-8"))
            new_ids = {item["id"] for item in after["segments"]}
            self.assertTrue(old_ids & new_ids)
            self.assertEqual(after["segments"][0]["start"], 0)
            self.assertEqual(
                after["segments"][-1]["end"],
                len(working.read_text(encoding="utf-8")),
            )
            for left, right in zip(after["segments"], after["segments"][1:]):
                self.assertEqual(left["end"], right["start"])

            sample_one = run(
                SEGMENT, "--map", mapping, "sample", "--count", "6", "--json"
            )
            sample_two = run(
                SEGMENT, "--map", mapping, "sample", "--count", "6", "--json"
            )
            self.assertEqual(sample_one.returncode, 0, sample_one.stderr)
            self.assertEqual(sample_one.stdout, sample_two.stdout)
            selected = json.loads(sample_one.stdout)
            self.assertGreaterEqual(len(selected), 6)

            packed = run(
                SEGMENT,
                "--map", mapping,
                "pack", selected[0],
                "--file", working,
                "--json",
            )
            self.assertEqual(packed.returncode, 0, packed.stderr)
            pack = json.loads(packed.stdout)
            self.assertEqual(pack["segment"]["id"], selected[0])
            self.assertIn("text", pack)
            self.assertIn("seam_before", pack)
            self.assertIn("seam_after", pack)

            refreshed = run(MEMORY, "--workspace", root, "refresh")
            self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
            memory = (root / "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn("Карта длинного текста", memory)
            self.assertLessEqual(len(memory.splitlines()), 220)

    def test_longform_source_inventory_reaches_heterogeneous_tail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            blocks = [longform_block(index) for index in range(1, 321)]
            original = write(root / "original.md", "\n\n".join(blocks) + "\n")
            state = root / "STATE.json"
            initialized = run(
                STATE,
                "--state",
                state,
                "init",
                "--original",
                original,
                "--working",
                original,
                "--flags",
                "none",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            semantic = root / "semantic-template.json"
            templated = run(
                STATE,
                "--state",
                state,
                "template",
                "--kind",
                "semantic_review",
                "--out",
                semantic,
            )
            self.assertEqual(templated.returncode, 0, templated.stderr)
            units = json.loads(semantic.read_text(encoding="utf-8"))["source_units"]
            self.assertGreater(len(units), 320)
            self.assertNotEqual(units[0]["original_sha256"], units[-1]["original_sha256"])
            self.assertTrue(any("[12]" in unit["original_excerpt"] for unit in units))
            self.assertTrue(
                any("unmapped tail" in unit["original_excerpt"] for unit in units)
            )

    def test_hot_memory_stays_bounded_with_many_cold_notes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for index in range(80):
                noted = run(
                    MEMORY,
                    "--workspace", root,
                    "note",
                    "--topic", f"topic-{index:03d}",
                    "--text",
                    f"Durable detail number {index} remains in the cold layer.",
                )
                self.assertEqual(noted.returncode, 0, noted.stderr)
            refreshed = run(MEMORY, "--workspace", root, "refresh")
            self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
            memory = (root / "MEMORY.md").read_text(encoding="utf-8")
            self.assertLessEqual(len(memory.splitlines()), 220)
            self.assertIn("ещё 40 файлов", memory)
            recalled = run(
                MEMORY,
                "--workspace", root,
                "recall",
                "Durable detail number 79",
            )
            self.assertEqual(recalled.returncode, 0, recalled.stderr)
            self.assertIn("topic-079.md", recalled.stdout)


def main() -> int:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
