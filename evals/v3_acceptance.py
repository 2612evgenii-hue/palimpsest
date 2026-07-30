#!/usr/bin/env python3
"""Adversarial acceptance suite for Palimpsest v3.5."""
from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STATE = SCRIPTS / "state.py"
SEGMENT = SCRIPTS / "segment.py"
MEMORY = SCRIPTS / "memory.py"
OVERLAP = SCRIPTS / "source_overlap.py"
FIDELITY = SCRIPTS / "fidelity_check.py"
sys.path.insert(0, str(SCRIPTS))
import _textlib as T  # noqa: E402


def run(script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"expected JSON, rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        ) from exc


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def captured_png(width: int = 640, height: int = 360) -> bytes:
    """Build a deterministic, structurally valid browser-sized PNG fixture."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(((x * 3 + y) % 256, (x + y * 5) % 256, (x * 7 + y * 2) % 256))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


def state_cmd(state: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    return run(STATE, "--state", str(state), command, *args)


def init_project(
    root: Path,
    flags: str = "F1",
    *extra_init: str,
) -> tuple[Path, Path, Path]:
    original = write(
        root / "original.md",
        (
            "A regional library introduced evening study hours for six weeks. "
            "Attendance increased during the trial, but the report does not claim "
            "that the schedule caused higher grades. Staff recorded visitor counts "
            "and collected optional comments before recommending a longer pilot.\n"
        ),
    )
    working = write(root / "working.md", original.read_text(encoding="utf-8"))
    state = root / "STATE.json"
    init_args = list(extra_init)
    if "F1" in flags and "--services" not in init_args:
        # Focused acceptance cases keep the explicit two-service scope. A
        # separate contract test verifies the repeatable no-sign-up default.
        init_args.extend(["--services", "zerogpt,copyleaks"])
    proc = state_cmd(
        state,
        "init",
        "--original",
        str(original),
        "--working",
        str(working),
        "--flags",
        flags,
        *init_args,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return state, original, working


def complete_intake(state: Path) -> None:
    current = json.loads(state.read_text(encoding="utf-8"))
    functions = ",".join(
        name for name, enabled in current["flags"].items() if enabled
    ) or "none"
    services = ",".join(current["detector_policy"]["selected_services"]) or "none"
    rows = [
        (
            "Q1",
            "Use the source text itself as the active style baseline.",
            ["--style-mode", "source_as_reference", "--english-level", "infer_from_source"],
        ),
        (
            "Q2",
            "Use only the functions explicitly selected for this project.",
            ["--functions", functions],
        ),
        (
            "Q3",
            "Use exactly the enabled detector services and disable all others.",
            ["--services", services],
        ),
        (
            "Q4",
            "Preserve meaning, English prose, proficiency level, and all factual qualifications.",
            [],
        ),
    ]
    for question, answer, extra in rows:
        proc = state_cmd(
            state,
            "intake",
            "--question",
            question,
            "--answer",
            answer,
            "--source",
            "explicit",
            *extra,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)


def capability(
    state: Path,
    root: Path,
    *,
    forge_group: bool = False,
    forge_guest_service: str = "",
) -> Path:
    path = root / ("capability-forged.json" if forge_group else "capability.json")
    proc = state_cmd(state, "template", "--kind", "capability_review", "--out", str(path))
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    data = json.loads(path.read_text(encoding="utf-8"))
    for service, entry in data["services"].items():
        observation = entry["observation"]
        observation["status"] = "confirmed"
        observation["checked_at"] = datetime.now(timezone.utc).isoformat()
        observation["access_observed"] = (
            "guest"
            if entry["registry_facts"]["guest_access"]
            else (
                "institutional_existing"
                if entry["registry_facts"]["kind"] == "institutional"
                else "authenticated_existing"
            )
        )
        observation["language_tested"] = True
        observation["result_returned"] = True
        observation["evidence"] = (
            f"Visible live guest form for {service}; English accepted and score returned."
        )
        if observation["access_observed"] == "authenticated_existing":
            observation["access_authorization_quote"] = (
                "I authorize use of my existing authenticated account for this service."
            )
    if forge_group:
        data["services"]["copyleaks"]["registry_facts"]["independence_group"] = "zerogpt"
    if forge_guest_service:
        data["services"][forge_guest_service]["registry_facts"]["guest_access"] = True
        data["services"][forge_guest_service]["observation"]["access_observed"] = "guest"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def register_capability(state: Path, root: Path) -> None:
    path = capability(state, root)
    proc = state_cmd(state, "artifact", "--kind", "capability_review", "--file", str(path))
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)


def detector(
    state: Path,
    root: Path,
    service: str,
    score: float,
    *,
    token: str = "",
    raw_bytes: bytes | None = None,
    register: bool = True,
) -> tuple[Path, Path]:
    stem = f"{service}-{token}" if token else service
    challenge_path = root / "evidence" / f"{stem}-challenge.json"
    prepared = state_cmd(
        state,
        "detector-prepare",
        "--service",
        service,
        "--target",
        "DOCUMENT",
        "--out",
        str(challenge_path),
    )
    if prepared.returncode != 0:
        raise AssertionError(prepared.stderr)
    challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
    raw = root / "evidence" / f"{stem}-result.png"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(captured_png() if raw_bytes is None else raw_bytes)
    registry = json.loads((ROOT / "assets" / "service-registry.json").read_text(encoding="utf-8"))
    observation = root / "evidence" / f"{stem}-observation.json"
    observation.write_text(
        json.dumps(
            {
                "schema": "palimpsest.detector-observation.v1",
                "challenge_id": challenge["id"],
                "challenge_nonce": challenge["nonce"],
                "service": service,
                "target": "DOCUMENT",
                "content_sha256": challenge["content_sha256"],
                "capture_mode": "browser_observed",
                "score_pct": score,
                "label": "human",
                "result_url": registry["services"][service]["url"],
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "visible_result_excerpt": f"Visible detector result: {score:g}% human label.",
                "raw_artifact": str(raw),
                "raw_artifact_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if register:
        proc = state_cmd(
            state,
            "detector",
            "--observation",
            str(observation),
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
    return observation, raw


def register_detector_round(
    state: Path,
    root: Path,
    *,
    filename: str = "detector-round.json",
) -> Path:
    round_path = root / filename
    prepared = state_cmd(
        state,
        "template",
        "--kind",
        "detector_round",
        "--out",
        str(round_path),
    )
    if prepared.returncode != 0:
        raise AssertionError(prepared.stderr)
    round_data = json.loads(round_path.read_text(encoding="utf-8"))
    for item in round_data["coverage_declarations"]:
        item["state"] = "all_visible_highlights_mapped"
        item["evidence"] = (
            "The complete visible result surface was inspected and mapped for this target."
        )
    for row in round_data["service_results"]:
        if row["score_pct"] is not None and row["score_pct"] >= round_data[
            "hard_max_exclusive_pct"
        ]:
            round_data["highlight_map"].append(
                {
                    "id": f"H-{row['service']}-{row['target']}",
                    "service": row["service"],
                    "target": row["target"],
                    "origin": "manual_diagnosis",
                    "location": "DOCUMENT paragraph 1",
                    "excerpt": "A regional library introduced evening study hours",
                    "reason": (
                        "The failing service requires a concrete diagnostic zone "
                        "before the next bounded edit."
                    ),
                    "status": "open",
                }
            )
    round_data["editor_analysis"] = (
        "All mandatory service results and visible highlight surfaces were compared "
        "before deciding whether another bounded edit is required."
    )
    round_data["next_action"] = (
        "Apply the mapped minimal edits and recheck every mandatory service."
        if round_data["round_status"] == "requires_edit"
        else "Proceed to final fidelity gates without changing the current text."
    )
    round_path.write_text(
        json.dumps(round_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    registered = state_cmd(
        state,
        "artifact",
        "--kind",
        "detector_round",
        "--file",
        str(round_path),
    )
    if registered.returncode != 0:
        raise AssertionError(registered.stderr)
    return round_path


def make_attestation(
    state: Path,
    root: Path,
    kind: str,
    *,
    filename: str | None = None,
) -> Path:
    path = root / (filename or f"{kind}.json")
    proc = state_cmd(state, "template", "--kind", kind, "--out", str(path))
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "pass"
    data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    for check in data["checks"]:
        check["status"] = "pass"
        check["evidence"] = (
            f"Reviewed {check['id']} against the complete bound text and found no unresolved issue."
        )
        if kind == "semantic_review":
            check["locations"] = ["P1"]
    if kind == "semantic_review":
        current_state = json.loads(state.read_text(encoding="utf-8"))
        working_text = Path(current_state["files"]["working"]).read_text(encoding="utf-8")
        current_sentences = T.sentences(working_text)
        cursor = 0
        for index, row in enumerate(data["source_units"]):
            row["verdict"] = "preserved"
            excerpt = (
                current_sentences[min(index, len(current_sentences) - 1)]
                if current_sentences
                else working_text[:120]
            )
            start = working_text.find(excerpt, cursor)
            if start < 0:
                start = working_text.find(excerpt)
            if start < 0:
                raise AssertionError("semantic evidence excerpt was not found")
            end = start + len(excerpt)
            cursor = end
            row["edited_evidence"] = [
                {
                    "location": f"S{index + 1}",
                    "start_char": start,
                    "end_char": end,
                    "excerpt": excerpt,
                }
            ]
            row["rationale"] = (
                "The mapped sentence retains the same claim, qualification, and pragmatic role."
            )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def fill_attestation(state: Path, root: Path, kind: str) -> None:
    path = make_attestation(state, root, kind)
    proc = state_cmd(state, "artifact", "--kind", kind, "--file", str(path))
    if proc.returncode != 0:
        raise AssertionError(f"{kind}: {proc.stderr}")


class FidelityTests(unittest.TestCase):
    def test_formula_polarity_negation_and_context_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "o.md",
                "The study confirms growth of 8%. The formula is x = 1. "
                "The policy does not permit access.\n",
            )
            edited = write(
                root / "e.md",
                "The study refutes a decline of 8%. The formula is x = 9. "
                "The policy permits access.\n",
            )
            proc = run(FIDELITY, "--original", str(original), "--edited", str(edited), "--json")
            self.assertEqual(proc.returncode, 1)
            data = payload(proc)
            codes = {item["code"] for item in data["findings"]}
            self.assertIn("NUMBER_SET_CHANGED", codes)
            self.assertIn("NUMBER_CONTEXT_CHANGED", codes)
            self.assertIn("NEGATION_CHANGED", codes)
            self.assertFalse(data["ok"])
            self.assertIn("cannot prove semantic equivalence", data["limits"])

    def test_modality_logic_units_roles_and_claim_loss_are_blocked(self) -> None:
        cases = {
            "MODALITY_CHANGED": (
                "The analyst may publish the result.",
                "The analyst must publish the result.",
            ),
            "LOGIC_RELATION_CHANGED": (
                "The trial ended because the sensor failed.",
                "The trial ended despite the sensor failure.",
            ),
            "UNIT_CHANGED": ("The package weighs 10 kg.", "The package weighs 10 lb."),
            "POSSIBLE_ROLE_SWAP": (
                "The regulator warned the bank before the audit.",
                "The bank warned the regulator before the audit.",
            ),
            "CLAIM_DROPPED": (
                "The evidence does not establish causation. Selection bias may explain the association.",
                "Selection bias may explain the association.",
            ),
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for expected, (source, edited) in cases.items():
                with self.subTest(expected=expected):
                    original = write(root / f"{expected}-o.md", source + "\n")
                    current = write(root / f"{expected}-e.md", edited + "\n")
                    proc = run(
                        FIDELITY,
                        "--original",
                        str(original),
                        "--edited",
                        str(current),
                        "--json",
                    )
                    self.assertEqual(proc.returncode, 1)
                    codes = {item["code"] for item in payload(proc)["findings"]}
                    self.assertIn(expected, codes)


class SemanticAuthorizationTests(unittest.TestCase):
    def _filled_semantic_template(self, state: Path, root: Path) -> tuple[Path, dict]:
        review = root / "semantic.json"
        templated = state_cmd(
            state,
            "template",
            "--kind",
            "semantic_review",
            "--out",
            str(review),
        )
        self.assertEqual(templated.returncode, 0, templated.stderr)
        data = json.loads(review.read_text(encoding="utf-8"))
        data["status"] = "pass"
        data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        for check in data["checks"]:
            check["status"] = "pass"
            check["evidence"] = (
                "The full source-unit inventory was compared against exact working offsets."
            )
            check["locations"] = ["S1"]
        return review, data

    def test_authorized_change_cannot_reuse_unrelated_source_unit_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "original.md",
                (
                    "The safety committee retained the original qualification. "
                    "A finance team published a separate budget note after the meeting.\n"
                ),
            )
            working = write(root / "working.md", original.read_text(encoding="utf-8"))
            state = root / "STATE.json"
            initialized = state_cmd(
                state,
                "init",
                "--original",
                str(original),
                "--working",
                str(working),
                "--flags",
                "none",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            complete_intake(state)
            review, data = self._filled_semantic_template(state, root)
            unrelated = (
                "A finance team published a separate budget note after the meeting."
            )
            start = working.read_text(encoding="utf-8").index(unrelated)
            for row in data["source_units"]:
                row["verdict"] = "authorized_change"
                row["rationale"] = (
                    "This row declares a replacement but deliberately reuses another unit."
                )
                row["edited_evidence"] = [
                    {
                        "location": "S2",
                        "start_char": start,
                        "end_char": start + len(unrelated),
                        "excerpt": unrelated,
                    }
                ]
                row["authorization"] = {
                    "trust": "unverified_external_claim",
                    "source_unit_id": row["id"],
                    "source_unit_sha256": row["original_sha256"],
                    "change_scope": (
                        "Replace this exact source unit under an externally asserted instruction."
                    ),
                    "user_quote": (
                        "I allegedly authorize this exact change for the selected source unit."
                    ),
                    "user_message_ref": "invented-message-ref",
                }
            review.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            registered = state_cmd(
                state,
                "artifact",
                "--kind",
                "semantic_review",
                "--file",
                str(review),
            )
            self.assertNotEqual(registered.returncode, 0)
            self.assertIn("overlaps or reuses", registered.stderr)

    def test_declared_authorized_change_is_red_until_source_is_rebaselined(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "original.md",
                "The report retains one qualified claim for this authorization test.\n",
            )
            working = write(root / "working.md", original.read_text(encoding="utf-8"))
            state = root / "STATE.json"
            initialized = state_cmd(
                state,
                "init",
                "--original",
                str(original),
                "--working",
                str(working),
                "--flags",
                "none",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            complete_intake(state)
            review, data = self._filled_semantic_template(state, root)
            text = working.read_text(encoding="utf-8").strip()
            row = data["source_units"][0]
            row["verdict"] = "authorized_change"
            row["rationale"] = (
                "The unit is explicitly declared as an externally authorized exception."
            )
            row["edited_evidence"] = [
                {
                    "location": "S1",
                    "start_char": 0,
                    "end_char": len(text),
                    "excerpt": text,
                }
            ]
            row["authorization"] = {
                "trust": "unverified_external_claim",
                "source_unit_id": row["id"],
                "source_unit_sha256": row["original_sha256"],
                "change_scope": (
                    "Treat this exact source unit as a declared replacement exception."
                ),
                "user_quote": (
                    "I authorize the declared change to this exact source unit in the draft."
                ),
                "user_message_ref": "external-message-ref",
            }
            review.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            registered = state_cmd(
                state,
                "artifact",
                "--kind",
                "semantic_review",
                "--file",
                str(review),
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            verification = payload(state_cmd(state, "verify", "--json"))
            self.assertEqual(verification["gates"]["G7"]["color"], "red")
            self.assertIn(
                "cannot be authenticated",
                "\n".join(verification["gates"]["G7"]["details"]),
            )

    def test_exact_semantic_mapping_can_reconcile_lexical_coverage_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "original.md",
                (
                    "The committee reviewed the regional transport schedule before "
                    "approving the pilot. The report retained the original qualification.\n"
                ),
            )
            working = write(
                root / "working.md",
                (
                    "Before approving the trial, the committee examined the local "
                    "logistics timetable. The report retained the original qualification.\n"
                ),
            )
            state = root / "STATE.json"
            initialized = state_cmd(
                state,
                "init",
                "--original",
                str(original),
                "--working",
                str(working),
                "--flags",
                "none",
                "--budget",
                "0.8",
                "--para-budget",
                "1",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            complete_intake(state)
            semantic = make_attestation(state, root, "semantic_review")
            registered = state_cmd(
                state,
                "artifact",
                "--kind",
                "semantic_review",
                "--file",
                str(semantic),
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            verification = payload(state_cmd(state, "verify", "--json"))
            fidelity = verification["machine_checks"]["fidelity"]
            self.assertFalse(fidelity["raw_ok"])
            self.assertTrue(fidelity["coverage_reconciled"])
            self.assertEqual(verification["gates"]["G7"]["color"], "green")

    def test_semantic_mapping_never_overrides_number_or_negation_change(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "original.md",
                "The committee did not approve 12 applications.\n",
            )
            working = write(
                root / "working.md",
                "The committee approved 13 applications.\n",
            )
            state = root / "STATE.json"
            initialized = state_cmd(
                state,
                "init",
                "--original",
                str(original),
                "--working",
                str(working),
                "--flags",
                "none",
                "--budget",
                "0.8",
                "--para-budget",
                "1",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            complete_intake(state)
            semantic = make_attestation(state, root, "semantic_review")
            registered = state_cmd(
                state,
                "artifact",
                "--kind",
                "semantic_review",
                "--file",
                str(semantic),
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            verification = payload(state_cmd(state, "verify", "--json"))
            fidelity = verification["machine_checks"]["fidelity"]
            self.assertFalse(fidelity["coverage_reconciled"])
            self.assertIn(
                "hard fidelity findings",
                " ".join(fidelity["coverage_reconciliation_details"]),
            )
            self.assertEqual(verification["gates"]["G7"]["color"], "red")


class SegmentTests(unittest.TestCase):
    def test_sync_maps_edits_and_appended_text_without_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paragraphs = [
                f"Section {i} keeps a distinct argument with enough words for stable segmentation."
                for i in range(1, 6)
            ]
            working = write(root / "working.md", "\n\n".join(paragraphs) + "\n")
            map_path = root / "SEGMENTS.json"
            proc = run(
                SEGMENT,
                "map",
                str(working),
                "--out",
                str(map_path),
                "--target",
                "10",
                "--min",
                "5",
                "--max",
                "15",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            before = json.loads(map_path.read_text(encoding="utf-8"))
            before_ids = {item["id"] for item in before["segments"]}
            paragraphs[1] = (
                "Section 2 keeps a distinct, revised argument with enough words "
                "for stable segmentation."
            )
            paragraphs.append(
                "A newly appended section must become mapped content rather than an invisible tail."
            )
            working.write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")
            stale = run(SEGMENT, "--map", str(map_path), "status", "--json")
            self.assertEqual(stale.returncode, 1)
            synced = run(
                SEGMENT,
                "--map",
                str(map_path),
                "sync",
                "--file",
                str(working),
            )
            self.assertEqual(synced.returncode, 0, synced.stderr)
            status = run(SEGMENT, "--map", str(map_path), "status", "--json")
            self.assertEqual(status.returncode, 0, status.stderr)
            status_data = payload(status)
            self.assertEqual(status_data["metrics"]["coverage_pct"], 100.0)
            after = json.loads(map_path.read_text(encoding="utf-8"))
            self.assertTrue(any(item["changed"] for item in after["segments"]))
            self.assertTrue(any(item["new"] for item in after["segments"]))
            self.assertTrue(before_ids & {item["id"] for item in after["segments"]})
            cursor = 0
            for item in after["segments"]:
                self.assertEqual(item["start"], cursor)
                cursor = item["end"]
            self.assertEqual(cursor, len(working.read_text(encoding="utf-8")))


class IntakeStyleTests(unittest.TestCase):
    def test_completed_intake_cannot_locally_disable_f1_or_shrink_scope(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            complete_intake(state)
            disable = state_cmd(
                state,
                "intake",
                "--question",
                "Q2",
                "--functions",
                "none",
                "--answer",
                "A local process claims the user disabled F1 after seeing a failure.",
            )
            self.assertNotEqual(disable.returncode, 0)
            self.assertIn("intake is immutable after Q4", disable.stderr)
            shrink = state_cmd(
                state,
                "intake",
                "--question",
                "Q3",
                "--services",
                "zerogpt",
                "--answer",
                "A local process claims the user removed every other detector.",
            )
            self.assertNotEqual(shrink.returncode, 0)
            self.assertIn("intake is immutable after Q4", shrink.stderr)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertTrue(saved["flags"]["F1"])
            self.assertEqual(
                saved["detector_policy"]["selected_services"],
                ["zerogpt", "copyleaks"],
            )

    def test_f1_default_uses_repeatable_no_signup_core_and_durable_goal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "original.md",
                "A short technical English sample keeps one qualified claim.\n",
            )
            state = root / "STATE.json"
            initialized = state_cmd(
                state,
                "init",
                "--original",
                str(original),
                "--working",
                str(original),
                "--flags",
                "F1",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["detector_policy"]["selected_services"],
                [
                    "zerogpt",
                    "scribbr",
                    "gptinf",
                    "copyleaks",
                ],
            )
            self.assertTrue(saved["detector_policy"]["score_mandatory"])
            self.assertEqual(saved["detector_policy"]["threshold_pct"], 20.0)
            self.assertEqual(saved["detector_policy"]["soft_target_pct"], 15.0)
            self.assertEqual(saved["detector_policy"]["coverage"], "full")
            self.assertIn("strict", saved["goal"]["hard_pass"])
            self.assertEqual(saved["budgets"]["document_change_ratio"], 0.30)

    def test_original_digest_change_is_a_g0_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, original, _ = init_project(root, flags="")
            complete_intake(state)
            fill_attestation(state, root, "master_brief")
            original.write_text(
                original.read_text(encoding="utf-8")
                + "A local process must not silently rebaseline the source.\n",
                encoding="utf-8",
            )
            verification = payload(state_cmd(state, "verify", "--json"))
            self.assertEqual(verification["gates"]["G0"]["color"], "red")
            self.assertIn(
                "changed after init",
                "\n".join(verification["gates"]["G0"]["details"]),
            )

    def test_manual_language_cannot_override_russian_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(
                root / "original.md",
                "Это русский исходный текст, и ручной флаг не должен менять язык проверки.\n",
            )
            state = root / "STATE.json"
            denied = state_cmd(
                state,
                "init",
                "--original",
                str(original),
                "--working",
                str(original),
                "--flags",
                "F1",
                "--language",
                "en",
            )
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("conflicts with source detection ru", denied.stderr)
            self.assertFalse(state.exists())

    def test_source_as_reference_and_detector_choices_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            out_of_order = state_cmd(
                state,
                "intake",
                "--question", "Q2",
                "--answer", "Enable F1 only for this project.",
                "--functions", "F1",
            )
            self.assertNotEqual(out_of_order.returncode, 0)
            self.assertIn("complete Q1 first", out_of_order.stderr)

            missing_level = state_cmd(
                state,
                "intake",
                "--question", "Q1",
                "--answer", "Use the source as its own style reference.",
                "--style-mode", "source_as_reference",
            )
            self.assertNotEqual(missing_level.returncode, 0)
            self.assertIn("--english-level", missing_level.stderr)

            q1 = state_cmd(
                state,
                "intake",
                "--question", "Q1",
                "--answer", "Use the source as its own style reference.",
                "--style-mode", "source_as_reference",
                "--english-level", "B2",
            )
            self.assertEqual(q1.returncode, 0, q1.stderr)
            q2 = state_cmd(
                state,
                "intake",
                "--question", "Q2",
                "--answer", "Enable F1 and disable all other optional functions.",
                "--functions", "F1",
            )
            self.assertEqual(q2.returncode, 0, q2.stderr)
            no_zero = state_cmd(
                state,
                "intake",
                "--question", "Q3",
                "--answer", "Enable only the optional Copyleaks service.",
                "--services", "copyleaks",
            )
            self.assertNotEqual(no_zero.returncode, 0)
            self.assertIn("ZeroGPT is mandatory", no_zero.stderr)
            selected = state_cmd(
                state,
                "intake",
                "--question", "Q3",
                "--answer", "Enable ZeroGPT and Copyleaks; disable other services.",
                "--services", "zerogpt,copyleaks",
            )
            self.assertEqual(selected.returncode, 0, selected.stderr)

            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["style_mode"], "source_as_reference")
            self.assertEqual(saved["english_level"]["target"], "B2")
            self.assertEqual(
                saved["detector_policy"]["selected_services"],
                ["zerogpt", "copyleaks"],
            )

    def test_external_reference_mode_requires_a_real_reference(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root, flags="")
            denied = state_cmd(
                state,
                "intake",
                "--question", "Q1",
                "--answer", "Use an external handwriting reference.",
                "--style-mode", "external_reference",
                "--english-level", "infer_from_source",
            )
            self.assertNotEqual(denied.returncode, 0)
            reference = write(
                root / "reference.md",
                "I keep my sentences direct, qualified, and moderately detailed.\n",
            )
            accepted = state_cmd(
                state,
                "intake",
                "--question", "Q1",
                "--answer", "Use the supplied external handwriting reference.",
                "--style-mode", "external_reference",
                "--english-level", "infer_from_source",
                "--ref", str(reference),
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["style_mode"], "external_reference")
            self.assertEqual(saved["files"]["references"], [str(reference.resolve())])


class DetectorStateTests(unittest.TestCase):
    def test_edit_budget_escalates_only_after_recorded_detector_resistance(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            complete_intake(state)
            premature = state_cmd(
                state,
                "edit-budget",
                "--document",
                "0.7",
                "--paragraph",
                "1",
                "--reason",
                (
                    "The initial detector round appears resistant and requires "
                    "a broader evidence-bound edit."
                ),
            )
            self.assertNotEqual(premature.returncode, 0)
            self.assertIn("requires a recorded score", premature.stderr)

            register_capability(state, root)
            detector(state, root, "zerogpt", 83)
            escalated = state_cmd(
                state,
                "edit-budget",
                "--document",
                "0.7",
                "--paragraph",
                "1",
                "--reason",
                (
                    "ZeroGPT remained above the hard threshold after the first "
                    "bounded editorial pass."
                ),
            )
            self.assertEqual(escalated.returncode, 0, escalated.stderr)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["budgets"]["document_change_ratio"], 0.7)
            self.assertEqual(len(saved["budget_history"]), 2)
            self.assertEqual(
                saved["budget_history"][-1]["supporting_failed_observations"], 1
            )

    def test_capability_cannot_forge_independence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            forged = capability(state, root, forge_group=True)
            proc = state_cmd(
                state,
                "artifact",
                "--kind",
                "capability_review",
                "--file",
                str(forged),
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("registry_facts were changed", proc.stderr)

    def test_capability_cannot_forge_guest_access(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = write(root / "original.md", "A short English probe remains unchanged.\n")
            working = write(root / "working.md", original.read_text(encoding="utf-8"))
            state = root / "STATE.json"
            init = state_cmd(
                state,
                "init",
                "--original",
                str(original),
                "--working",
                str(working),
                "--flags",
                "F1",
                "--services",
                "zerogpt,turnitin",
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            forged = capability(state, root, forge_guest_service="turnitin")
            registered = state_cmd(
                state,
                "artifact",
                "--kind",
                "capability_review",
                "--file",
                str(forged),
            )
            self.assertNotEqual(registered.returncode, 0)
            self.assertIn("registry_facts were changed", registered.stderr)

    def test_browser_capture_must_be_a_real_image(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            register_capability(state, root)
            observation, _ = detector(
                state,
                root,
                "zerogpt",
                19.0,
                raw_bytes=b"\x89PNG\r\n\x1a\n" + bytes([37]) * 2048,
                register=False,
            )
            registered = state_cmd(
                state,
                "detector",
                "--observation",
                str(observation),
            )
            self.assertNotEqual(registered.returncode, 0)
            self.assertIn("raw PNG", registered.stderr)

    def test_each_service_needs_current_untampered_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, working = init_project(root)
            complete_intake(state)
            register_capability(state, root)
            _, zero_raw = detector(state, root, "zerogpt", 3)

            one_only = state_cmd(state, "verify", "--json")
            one_data = payload(one_only)
            self.assertEqual(one_data["gates"]["G3"]["color"], "red")
            self.assertIn(
                "copyleaks/DOCUMENT: no current result",
                "\n".join(one_data["gates"]["G3"]["details"]),
            )

            detector(state, root, "copyleaks", 0)
            register_detector_round(state, root)
            complete = state_cmd(state, "verify", "--json")
            complete_data = payload(complete)
            self.assertEqual(complete_data["gates"]["G3"]["color"], "green")

            zero_raw.write_bytes(b"changed raw detector artifact" * 40)
            tampered = payload(state_cmd(state, "verify", "--json"))
            self.assertEqual(tampered["gates"]["G3"]["color"], "red")
            self.assertIn(
                "raw artifact changed",
                "\n".join(tampered["gates"]["G3"]["details"]),
            )

            detector(state, root, "zerogpt", 3)
            rejected_waiver = state_cmd(
                state,
                "waive",
                "--service",
                "copyleaks",
                "--code",
                "user_choice",
                "--reason",
                "The user explicitly accepts this exact current service limitation.",
                "--user-quote",
                "I accept the Copyleaks limitation for this exact current document.",
            )
            self.assertNotEqual(rejected_waiver.returncode, 0)
            self.assertIn("cannot satisfy score_mandatory", rejected_waiver.stderr)
            working.write_text(
                working.read_text(encoding="utf-8") + "A new final sentence changes the digest.\n",
                encoding="utf-8",
            )
            stale = payload(state_cmd(state, "verify", "--json"))
            details = "\n".join(stale["gates"]["G3"]["details"])
            self.assertEqual(stale["gates"]["G3"]["color"], "red")
            self.assertIn("only stale results", details)
            self.assertNotIn("waived", details)

    def test_hard_threshold_is_strict_and_soft_target_is_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            complete_intake(state)
            register_capability(state, root)
            detector(state, root, "zerogpt", 19.9)
            detector(state, root, "copyleaks", 20.0)
            register_detector_round(state, root, filename="round-failing.json")

            failing = payload(state_cmd(state, "verify", "--json"))
            details = "\n".join(failing["gates"]["G3"]["details"])
            self.assertEqual(failing["gates"]["G3"]["color"], "red")
            self.assertIn("20% is not strictly below 20%", details)
            self.assertNotEqual(state_cmd(state, "close").returncode, 0)

            detector(state, root, "copyleaks", 19.9, token="below-hard")
            register_detector_round(state, root, filename="round-passing.json")
            passing = payload(state_cmd(state, "verify", "--json"))
            details = "\n".join(passing["gates"]["G3"]["details"])
            self.assertEqual(passing["gates"]["G3"]["color"], "green")
            self.assertIn("soft target <15% not reached", details)

    def test_detector_round_rejects_unbound_highlight_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            complete_intake(state)
            register_capability(state, root)
            detector(state, root, "zerogpt", 40)
            detector(state, root, "copyleaks", 35)
            round_path = root / "round-forged-highlight.json"
            prepared = state_cmd(
                state,
                "template",
                "--kind",
                "detector_round",
                "--out",
                str(round_path),
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            round_data = json.loads(round_path.read_text(encoding="utf-8"))
            for item in round_data["coverage_declarations"]:
                item["state"] = "all_visible_highlights_mapped"
                item["evidence"] = (
                    "Every visible result area was inspected for this service target."
                )
            for index, row in enumerate(round_data["service_results"], start=1):
                round_data["highlight_map"].append(
                    {
                        "id": f"H{index}",
                        "service": row["service"],
                        "target": row["target"],
                        "origin": "manual_diagnosis",
                        "location": "DOCUMENT paragraph 1",
                        "excerpt": (
                            "This sentence does not occur anywhere in the current target."
                            if index == 2
                            else "A regional library introduced evening study hours"
                        ),
                        "reason": (
                            "This concrete zone is claimed as the basis for the next edit."
                        ),
                        "status": "open",
                    }
                )
            round_data["editor_analysis"] = (
                "The round attempts to bind every failing service to a concrete text zone."
            )
            round_data["next_action"] = (
                "Repair mapped zones minimally and then rerun every mandatory service."
            )
            round_path.write_text(
                json.dumps(round_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            rejected = state_cmd(
                state,
                "artifact",
                "--kind",
                "detector_round",
                "--file",
                str(round_path),
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("excerpt is not verbatim text", rejected.stderr)

    def test_edit_requires_every_service_recheck_and_a_new_round(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, working = init_project(root)
            complete_intake(state)
            register_capability(state, root)
            detector(state, root, "zerogpt", 4)
            detector(state, root, "copyleaks", 3)
            register_detector_round(state, root, filename="round-before-edit.json")
            self.assertEqual(
                payload(state_cmd(state, "verify", "--json"))["gates"]["G3"]["color"],
                "green",
            )

            working.write_text(
                working.read_text(encoding="utf-8").replace(
                    "six weeks", "a six-week period"
                ),
                encoding="utf-8",
            )
            stale = payload(state_cmd(state, "verify", "--json"))
            stale_details = "\n".join(stale["gates"]["G3"]["details"])
            self.assertEqual(stale["gates"]["G3"]["color"], "red")
            self.assertIn("zerogpt/DOCUMENT: only stale results", stale_details)
            self.assertIn("copyleaks/DOCUMENT: only stale results", stale_details)
            self.assertIn("detector round is stale", stale_details)

            detector(state, root, "zerogpt", 5, token="after-edit")
            partial = payload(state_cmd(state, "verify", "--json"))
            self.assertIn(
                "copyleaks/DOCUMENT: only stale results",
                "\n".join(partial["gates"]["G3"]["details"]),
            )
            detector(state, root, "copyleaks", 6, token="after-edit")
            register_detector_round(state, root, filename="round-after-edit.json")
            self.assertEqual(
                payload(state_cmd(state, "verify", "--json"))["gates"]["G3"]["color"],
                "green",
            )

    def test_score_mandatory_rejects_sampled_coverage_and_blocked_service(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            rejected = state_cmd(
                state,
                "detector-policy",
                "--coverage",
                "risk_sampled",
                "--user-quote",
                "The user allegedly accepts a sampled detector pass for this project.",
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("forbids risk_sampled", rejected.stderr)

            complete_intake(state)
            cap_path = capability(state, root)
            cap_data = json.loads(cap_path.read_text(encoding="utf-8"))
            cap_data["services"]["copyleaks"]["observation"] = {
                "status": "blocked",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "access_observed": "blocked",
                "language_tested": False,
                "result_returned": False,
                "evidence": (
                    "The live page required unavailable access and returned no usable result."
                ),
                "access_authorization_quote": "",
            }
            cap_path.write_text(
                json.dumps(cap_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            accepted = state_cmd(
                state,
                "artifact",
                "--kind",
                "capability_review",
                "--file",
                str(cap_path),
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            detector(state, root, "zerogpt", 2)
            verification = payload(state_cmd(state, "verify", "--json"))
            self.assertEqual(verification["gates"]["G3"]["color"], "red")
            self.assertIn(
                "capability not confirmed",
                "\n".join(verification["gates"]["G3"]["details"]),
            )

    def test_reducing_independent_minimum_requires_user_words(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root)
            denied = state_cmd(state, "detector-policy", "--min-independent", "1")
            self.assertNotEqual(denied.returncode, 0)
            accepted = state_cmd(
                state,
                "detector-policy",
                "--min-independent",
                "1",
                "--user-quote",
                "I explicitly accept using only one independent detector for this project.",
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            data = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(data["detector_policy"]["minimum_independent"], 1)
            self.assertIn("minimum_acceptance_quote", data["detector_policy"])

    def test_no_manual_gate_or_force_close_command_exists(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root, flags="")
            gate = state_cmd(state, "gate", "--id", "G3", "--status", "green")
            self.assertNotEqual(gate.returncode, 0)
            force = state_cmd(state, "close", "--force")
            self.assertNotEqual(force.returncode, 0)
            bare_score = state_cmd(
                state,
                "detector",
                "--service",
                "zerogpt",
                "--score",
                "0",
                "--label",
                "human",
                "--evidence",
                str(write(root / "arbitrary.txt", "arbitrary score theater evidence")),
            )
            self.assertNotEqual(bare_score.returncode, 0)

    def test_formal_plateau_requires_and_accepts_three_bound_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, original, working = init_project(
                root,
                "F1",
                "--budget",
                "0.6",
                "--para-budget",
                "1",
            )
            complete_intake(state)
            register_capability(state, root)
            candidates = [
                (
                    "For six weeks, a regional library introduced evening study "
                    "hours. Attendance increased during the trial, but the report "
                    "does not claim that the schedule caused higher grades. Staff "
                    "recorded visitor counts and collected optional comments before "
                    "recommending a longer pilot.\n"
                ),
                original.read_text(encoding="utf-8"),
                (
                    "A regional library introduced evening study hours for six weeks. "
                    "Although attendance increased during the trial, the report does "
                    "not claim that the schedule caused higher grades. Before "
                    "recommending a longer pilot, staff recorded visitor counts and "
                    "collected optional comments.\n"
                ),
            ]
            rows = []
            mechanisms = [
                "lexical_cleanup",
                "syntax_restructure",
                "rhythm_restructure",
            ]
            for index, text_value in enumerate(candidates, start=1):
                working.write_text(text_value, encoding="utf-8")
                candidate = write(root / f"candidate-{index}.md", text_value)
                move_id = f"plateau-move-{index}"
                moved = state_cmd(
                    state,
                    "move",
                    "--id",
                    move_id,
                    "--span",
                    "DOCUMENT",
                    "--mechanism",
                    mechanisms[index - 1],
                    "--hypothesis",
                    (
                        "This candidate tests a distinct documented edit mechanism "
                        "against the unchanged detector threshold."
                    ),
                )
                self.assertEqual(moved.returncode, 0, moved.stderr)
                fidelity_proc = run(
                    FIDELITY,
                    "--original", str(original),
                    "--edited", str(candidate),
                    "--json",
                )
                self.assertEqual(
                    fidelity_proc.returncode,
                    0,
                    fidelity_proc.stdout + fidelity_proc.stderr,
                )
                fidelity_path = root / f"fidelity-{index}.json"
                fidelity_path.write_text(
                    json.dumps(payload(fidelity_proc), ensure_ascii=False, indent=2)
                    + "\n",
                    encoding="utf-8",
                )
                semantic = make_attestation(
                    state,
                    root,
                    "semantic_review",
                    filename=f"semantic-{index}.json",
                )
                observation, _ = detector(
                    state,
                    root,
                    "copyleaks",
                    82 + (index - 1) * 0.4,
                    token=f"plateau-{index}",
                )
                rows.append(
                    {
                        "candidate_path": str(candidate),
                        "candidate_sha256": hashlib.sha256(
                            candidate.read_bytes()
                        ).hexdigest(),
                        "fidelity_path": str(fidelity_path),
                        "fidelity_sha256": hashlib.sha256(
                            fidelity_path.read_bytes()
                        ).hexdigest(),
                        "semantic_review_path": str(semantic),
                        "semantic_review_sha256": hashlib.sha256(
                            semantic.read_bytes()
                        ).hexdigest(),
                        "move_ids": [move_id],
                        "change_summary": (
                            "This candidate applies a separately recorded mechanism "
                            "while preserving every qualification and factual claim."
                        ),
                        "segment_map_path": "",
                        "segment_map_sha256": "",
                        "observation_path": str(observation),
                        "observation_sha256": hashlib.sha256(
                            observation.read_bytes()
                        ).hexdigest(),
                        "score_pct": 82 + (index - 1) * 0.4,
                    }
                )

            plateau_path = root / "plateau.json"
            prepared = state_cmd(
                state,
                "plateau-template",
                "--service", "copyleaks",
                "--target", "DOCUMENT",
                "--out", str(plateau_path),
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            plateau = json.loads(plateau_path.read_text(encoding="utf-8"))
            plateau["reason"] = (
                "Three materially different, meaning-safe candidates remained "
                "within one score point above the project threshold."
            )
            plateau["candidates"] = rows
            plateau_path.write_text(
                json.dumps(plateau, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            registered = state_cmd(
                state,
                "plateau",
                "--file", str(plateau_path),
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["plateaus"]), 1)
            self.assertEqual(saved["plateaus"][0]["service"], "copyleaks")
            verification = payload(state_cmd(state, "verify", "--json"))
            details = "\n".join(verification["gates"]["G3"]["details"])
            self.assertEqual(verification["gates"]["G3"]["color"], "red")
            self.assertIn("plateau is still a blocker", details)
            self.assertNotEqual(state_cmd(state, "close").returncode, 0)

    def test_plateau_rejects_cosmetic_synonym_variants_even_with_move_labels(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, original, working = init_project(
                root,
                "F1",
                "--budget",
                "0.6",
                "--para-budget",
                "1",
            )
            complete_intake(state)
            register_capability(state, root)
            source = original.read_text(encoding="utf-8")
            candidates = [
                source,
                source.replace("introduced", "established").replace(
                    "increased", "escalated"
                ),
                source.replace("introduced", "inaugurated").replace(
                    "increased", "expanded"
                ),
            ]
            rows = []
            mechanisms = [
                "lexical_cleanup",
                "syntax_restructure",
                "rhythm_restructure",
            ]
            for index, text_value in enumerate(candidates, start=1):
                working.write_text(text_value, encoding="utf-8")
                candidate = write(root / f"cosmetic-{index}.md", text_value)
                move_id = f"cosmetic-move-{index}"
                moved = state_cmd(
                    state,
                    "move",
                    "--id",
                    move_id,
                    "--span",
                    "DOCUMENT",
                    "--mechanism",
                    mechanisms[index - 1],
                    "--hypothesis",
                    (
                        "The declared label claims a distinct mechanism even though "
                        "the text changes only same-position synonyms."
                    ),
                )
                self.assertEqual(moved.returncode, 0, moved.stderr)
                fidelity_proc = run(
                    FIDELITY,
                    "--original",
                    str(original),
                    "--edited",
                    str(candidate),
                    "--json",
                )
                self.assertEqual(fidelity_proc.returncode, 0, fidelity_proc.stdout)
                fidelity_path = root / f"cosmetic-fidelity-{index}.json"
                fidelity_path.write_text(fidelity_proc.stdout, encoding="utf-8")
                semantic = make_attestation(
                    state,
                    root,
                    "semantic_review",
                    filename=f"cosmetic-semantic-{index}.json",
                )
                observation, _ = detector(
                    state,
                    root,
                    "copyleaks",
                    83 + (index - 1) * 0.3,
                    token=f"cosmetic-{index}",
                )
                rows.append(
                    {
                        "candidate_path": str(candidate),
                        "candidate_sha256": hashlib.sha256(
                            candidate.read_bytes()
                        ).hexdigest(),
                        "fidelity_path": str(fidelity_path),
                        "fidelity_sha256": hashlib.sha256(
                            fidelity_path.read_bytes()
                        ).hexdigest(),
                        "semantic_review_path": str(semantic),
                        "semantic_review_sha256": hashlib.sha256(
                            semantic.read_bytes()
                        ).hexdigest(),
                        "move_ids": [move_id],
                        "change_summary": (
                            "This row falsely describes a material intervention while "
                            "the candidate only substitutes two words in place."
                        ),
                        "segment_map_path": "",
                        "segment_map_sha256": "",
                        "observation_path": str(observation),
                        "observation_sha256": hashlib.sha256(
                            observation.read_bytes()
                        ).hexdigest(),
                        "score_pct": 83 + (index - 1) * 0.3,
                    }
                )
            plateau_path = root / "cosmetic-plateau.json"
            prepared = state_cmd(
                state,
                "plateau-template",
                "--service",
                "copyleaks",
                "--target",
                "DOCUMENT",
                "--out",
                str(plateau_path),
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            plateau = json.loads(plateau_path.read_text(encoding="utf-8"))
            plateau["reason"] = (
                "Three synonym variants stayed above threshold, but they do not "
                "represent materially different editorial mechanisms."
            )
            plateau["candidates"] = rows
            plateau_path.write_text(
                json.dumps(plateau, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            rejected = state_cmd(state, "plateau", "--file", str(plateau_path))
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("same-position substitutions", rejected.stderr)


class OverlapTests(unittest.TestCase):
    def test_close_paraphrase_is_flagged_and_quotes_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source_text = (
                "The committee reviewed every application in chronological order before "
                "comparing the evidence against the published eligibility criteria and "
                "recording a written explanation for each final decision."
            )
            source = write(root / "source.md", source_text)
            close = write(
                root / "close.md",
                "Context.\n\n" + source_text + " Additional analysis follows.\n",
            )
            report = root / "overlap.json"
            proc = run(
                OVERLAP,
                "--draft",
                str(close),
                "--source",
                str(source),
                "--out",
                str(report),
                "--json",
            )
            self.assertEqual(proc.returncode, 1)
            data = payload(proc)
            self.assertGreater(data["high_risk_count"], 0)
            self.assertEqual(data["draft_sha256"], __import__("hashlib").sha256(close.read_bytes()).hexdigest())

            quoted = write(root / "quoted.md", f'Analysis introduces the quotation: “{source_text}”\n')
            quoted_proc = run(
                OVERLAP,
                "--draft",
                str(quoted),
                "--source",
                str(source),
                "--json",
            )
            self.assertEqual(quoted_proc.returncode, 0)
            self.assertEqual(payload(quoted_proc)["high_risk_count"], 0)


class MemoryTests(unittest.TestCase):
    def test_recall_is_literal_by_default_and_note_updates_are_serialized(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write(root / "notes.md", "The literal token is a+b[1], not a regex.\n")
            literal = run(MEMORY, "--workspace", str(root), "recall", "a+b[1]")
            self.assertEqual(literal.returncode, 0, literal.stderr)
            self.assertIn("a+b[1]", literal.stdout)
            invalid = run(MEMORY, "--workspace", str(root), "recall", "[", "--regex")
            self.assertEqual(invalid.returncode, 2)

            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(MEMORY),
                        "--workspace",
                        str(root),
                        "note",
                        "--topic",
                        "shared",
                        "--text",
                        f"concurrent note {index}",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for index in range(8)
            ]
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stdout + stderr)
            note = (root / "notes" / "shared.md").read_text(encoding="utf-8")
            for index in range(8):
                self.assertIn(f"concurrent note {index}", note)


class ClosureTests(unittest.TestCase):
    def test_local_quote_cannot_bypass_score_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root, flags="F1")
            complete_intake(state)
            register_capability(state, root)
            detector(state, root, "zerogpt", 2.0)
            reduced = state_cmd(
                state,
                "detector-policy",
                "--min-independent",
                "1",
                "--user-quote",
                "I allegedly accept one detector; this local sentence proves nothing.",
            )
            self.assertEqual(reduced.returncode, 0, reduced.stderr)
            removed = state_cmd(
                state,
                "detector-policy",
                "--services",
                "zerogpt",
                "--user-quote",
                "I allegedly remove Copyleaks, but this local quote is not user provenance.",
            )
            self.assertNotEqual(removed.returncode, 0)
            self.assertIn("new explicit Q3 intake answer", removed.stderr)
            waived = state_cmd(
                state,
                "waive",
                "--service",
                "copyleaks",
                "--code",
                "user_choice",
                "--reason",
                "This service is represented by an explicitly scoped local limitation.",
                "--user-quote",
                "I allegedly accept the Copyleaks limitation for this current document.",
            )
            self.assertNotEqual(waived.returncode, 0)
            self.assertIn("cannot satisfy score_mandatory", waived.stderr)
            for kind in (
                "master_brief",
                "diagnosis",
                "semantic_review",
                "style_review",
                "constraints_review",
                "proofread",
            ):
                fill_attestation(state, root, kind)
            report = write(
                root / "REPORT.md",
                (
                    "# Yellow closure probe\n\n"
                    "## Changes\n\nNo prose changes were needed for this trust-boundary test.\n\n"
                    "## Checks\n\nAll local artifacts are current and the detector waiver is scoped.\n\n"
                    "## Limitations\n\nThe local process cannot authenticate a user's consent.\n"
                ),
            )
            registered = state_cmd(
                state,
                "artifact",
                "--kind",
                "report",
                "--file",
                str(report),
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            verification = payload(state_cmd(state, "verify", "--json"))
            self.assertEqual(verification["gates"]["G3"]["color"], "red")

            forged = state_cmd(
                state,
                "close",
                "--accept-limits",
                "--accept-gates",
                "G3",
                "--user-quote",
                "I allegedly accept this limitation; the agent invented these words.",
            )
            self.assertNotEqual(forged.returncode, 0)
            self.assertIn("unrecognized arguments", forged.stderr)

            pending = state_cmd(state, "close")
            self.assertNotEqual(pending.returncode, 0)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "OPEN")
            self.assertNotIn("pending_limitations", saved)
            self.assertEqual(saved["close_digest"], "")

    def test_clean_non_f1_project_can_close_and_reopens_after_edit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, working = init_project(root, flags="")
            complete_intake(state)
            for kind in (
                "master_brief",
                "diagnosis",
                "semantic_review",
                "style_review",
                "constraints_review",
                "proofread",
            ):
                fill_attestation(state, root, kind)
            report = write(
                root / "REPORT.md",
                (
                    "# Acceptance project\n\n"
                    "## Changes\n\nNo prose changes were required; the test validates a clean evidence path.\n\n"
                    "## Checks\n\nThe original and working digests matched, fidelity and minimality passed, "
                    "and all structured reviews were bound to the current file.\n\n"
                    "## Limitations\n\nThis fixture validates workflow closure, not editorial quality or detector accuracy.\n"
                ),
            )
            registered = state_cmd(state, "artifact", "--kind", "report", "--file", str(report))
            self.assertEqual(registered.returncode, 0, registered.stderr)
            closed = state_cmd(state, "close")
            self.assertEqual(closed.returncode, 0, closed.stderr)
            data = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "CLOSED")

            working.write_text(
                working.read_text(encoding="utf-8") + "Post-close edit.\n",
                encoding="utf-8",
            )
            state_cmd(state, "verify", "--json")
            reopened = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(reopened["status"], "OPEN")
            self.assertEqual(reopened["close_digest"], "")

    def test_external_reference_route_keeps_ductus_and_style_gates_active(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, _, _ = init_project(root, flags="")
            reference = write(
                root / "reference.md",
                (
                    "I usually begin with the observed constraint, qualify the "
                    "evidence, and end without a ceremonial summary.\n"
                ),
            )
            intake_rows = [
                (
                    "Q1",
                    "Use the supplied text only as an external handwriting reference.",
                    [
                        "--style-mode", "external_reference",
                        "--english-level", "infer_from_source",
                        "--ref", str(reference),
                    ],
                ),
                (
                    "Q2",
                    "No optional routes are enabled for this reference-mode test.",
                    ["--functions", "none"],
                ),
                (
                    "Q3",
                    "No detector services are enabled because F1 is disabled.",
                    ["--services", "none"],
                ),
                (
                    "Q4",
                    "Preserve the source meaning and use only transferable style decisions.",
                    [],
                ),
            ]
            for question, answer, extra in intake_rows:
                proc = state_cmd(
                    state,
                    "intake",
                    "--question", question,
                    "--answer", answer,
                    *extra,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
            for kind in (
                "master_brief",
                "diagnosis",
                "ductus",
                "semantic_review",
                "style_review",
                "constraints_review",
                "proofread",
            ):
                fill_attestation(state, root, kind)
            report = write(
                root / "REPORT.md",
                (
                    "# External reference project\n\n"
                    "## Changes\n\nNo text change was required; this validates the "
                    "external-reference evidence route.\n\n"
                    "## Checks\n\nDuctus, style distance, semantic reconciliation, "
                    "English level, fidelity, and minimality all used current digests.\n\n"
                    "## Limitations\n\nA short reference has limited statistical "
                    "reliability and supplies no factual content.\n"
                ),
            )
            registered = state_cmd(
                state,
                "artifact",
                "--kind", "report",
                "--file", str(report),
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            verification = payload(state_cmd(state, "verify", "--json"))
            self.assertEqual(verification["gates"]["G2"]["color"], "green")
            self.assertEqual(verification["gates"]["G8"]["color"], "green")
            closed = state_cmd(state, "close")
            self.assertEqual(closed.returncode, 0, closed.stderr)


class ContractTests(unittest.TestCase):
    def test_live_acceptance_manifest_is_bound_to_passing_fixture(self) -> None:
        manifest = json.loads(
            (ROOT / "evals" / "live-acceptance-3.5.json").read_text(
                encoding="utf-8"
            )
        )
        candidate = ROOT / manifest["candidate"]["path"]
        self.assertEqual(
            hashlib.sha256(candidate.read_bytes()).hexdigest(),
            manifest["candidate"]["sha256"],
        )
        self.assertEqual(manifest["version"], "3.5.0")
        self.assertFalse(manifest["evidence_trust"]["screenshot_saved"])
        self.assertEqual(
            {row["service"] for row in manifest["results"]},
            {"zerogpt", "scribbr", "gptinf", "copyleaks"},
        )
        self.assertTrue(
            all(row["candidate_score_pct"] < 20 for row in manifest["results"])
        )

    def test_registry_and_skill_contract(self) -> None:
        registry = json.loads((ROOT / "assets" / "service-registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["schema"], "palimpsest.service-registry.v3.5")
        policy = registry["policy"]
        repeatable_english = [
            "zerogpt", "scribbr", "gptinf", "copyleaks"
        ]
        repeatable_russian = ["zerogpt", "gptinf", "copyleaks"]
        original_six = [
            "zerogpt", "gptzero", "scribbr", "quillbot", "gptinf", "copyleaks"
        ]
        self.assertEqual(
            policy["default_english_guest_services"], repeatable_english
        )
        self.assertEqual(
            policy["default_russian_guest_services"], repeatable_russian
        )
        self.assertEqual(policy["original_six_service_profile"], original_six)
        self.assertTrue(policy["zero_gpt_required"])
        self.assertEqual(policy["pilot_validated_languages"], ["en"])
        self.assertIn("provisional", policy["language_policy"]["ru"])
        independent_groups = {
            registry["services"][service]["independence_group"]
            for service in repeatable_english
            if registry["services"][service]["kind"] != "aggregator"
        }
        self.assertGreaterEqual(
            len(independent_groups), policy["minimum_independent_services"]
        )
        self.assertEqual(
            registry["services"]["scribbr"]["independence_group"],
            registry["services"]["quillbot"]["independence_group"],
        )
        self.assertEqual(registry["services"]["gptinf"]["kind"], "aggregator")

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(skill.splitlines()), 500)
        frontmatter = skill.split("---", 2)[1]
        keys = [
            line.split(":", 1)[0].strip()
            for line in frontmatter.splitlines()
            if line.strip() and not line.startswith(" ")
        ]
        self.assertEqual(keys, ["name", "description"])
        for link in re.findall(r"\]\((references/[^)]+)\)", skill):
            self.assertTrue((ROOT / link).is_file(), link)
        self.assertRegex(skill.casefold(), r"strictly below\s+20")

        yaml_text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        prompt = re.search(r'default_prompt:\s*"([^"]+)"', yaml_text).group(1)
        description = re.search(r'short_description:\s*"([^"]+)"', yaml_text).group(1)
        self.assertIn("$palimpsest", prompt)
        self.assertGreaterEqual(len(description), 25)
        self.assertLessEqual(len(description), 64)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
