#!/usr/bin/env python3
"""Build deterministic one-factor research variants from exact replacements."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

import minimality


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def character_change_metrics(original: str, candidate: str) -> dict:
    matcher = difflib.SequenceMatcher(a=original, b=candidate, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    ratio = 1 - (2 * matched) / (len(original) + len(candidate) or 1)
    changed_spans = sum(
        tag != "equal" for tag, _a1, _a2, _b1, _b2 in matcher.get_opcodes()
    )
    return {
        "char_change_ratio": round(ratio, 6),
        "changed_spans": changed_spans,
    }


def _operation_replacements(operation: dict) -> list[dict[str, str]]:
    """Return one or more exact replacements for a candidate operation.

    A single-factor operation keeps the compact ``old``/``new`` form.  A
    progressive bundle uses ``replacements`` so the research harness can test
    cumulative low-cost edits without hand-building an unbound text file.
    """
    if "replacements" in operation:
        replacements = operation["replacements"]
        if (
            not isinstance(replacements, list)
            or not replacements
            or any(
                not isinstance(replacement, dict)
                or not isinstance(replacement.get("old"), str)
                or not isinstance(replacement.get("new"), str)
                for replacement in replacements
            )
        ):
            raise ValueError(f"{operation.get('id', '<unknown>')}: invalid replacements")
        if "old" in operation or "new" in operation:
            raise ValueError(
                f"{operation.get('id', '<unknown>')}: use old/new or replacements, not both"
            )
        return replacements
    if not isinstance(operation.get("old"), str) or not isinstance(
        operation.get("new"), str
    ):
        raise ValueError(f"{operation.get('id', '<unknown>')}: missing old/new")
    return [{"old": operation["old"], "new": operation["new"]}]


def build(original_path: Path, plan_path: Path, out_dir: Path) -> dict:
    original = original_path.read_text(encoding="utf-8")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if digest(original) != plan["original_sha256"]:
        raise ValueError("original hash does not match plan")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for operation in plan["operations"]:
        candidate = original
        replacements = _operation_replacements(operation)
        for replacement_number, replacement in enumerate(replacements, start=1):
            old = replacement["old"]
            new = replacement["new"]
            count = candidate.count(old)
            if count != 1:
                raise ValueError(
                    f"{operation['id']} replacement {replacement_number}: "
                    f"expected one source span, found {count}"
                )
            candidate = candidate.replace(old, new, 1)
        destination = out_dir / f"{operation['id']}.txt"
        destination.write_text(candidate, encoding="utf-8")
        metrics = minimality.analyze(original, candidate, 1.0, 1.0)
        character_metrics = character_change_metrics(original, candidate)
        rows.append(
            {
                "id": operation["id"],
                "factor": operation["factor"],
                "replacement_count": len(replacements),
                "path": str(destination),
                "sha256": digest(candidate),
                "doc_change_ratio": metrics["doc_change_ratio"],
                **character_metrics,
                "edit_cost": max(
                    metrics["doc_change_ratio"],
                    character_metrics["char_change_ratio"],
                ),
                "words": metrics["words"],
            }
        )
    return {"original_sha256": digest(original), "variants": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.original, args.plan, args.out_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
