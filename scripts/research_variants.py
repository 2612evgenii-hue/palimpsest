#!/usr/bin/env python3
"""Build deterministic one-factor research variants from exact replacements."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import minimality


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build(original_path: Path, plan_path: Path, out_dir: Path) -> dict:
    original = original_path.read_text(encoding="utf-8")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if digest(original) != plan["original_sha256"]:
        raise ValueError("original hash does not match plan")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for operation in plan["operations"]:
        old = operation["old"]
        new = operation["new"]
        count = original.count(old)
        if count != 1:
            raise ValueError(f"{operation['id']}: expected one source span, found {count}")
        candidate = original.replace(old, new, 1)
        destination = out_dir / f"{operation['id']}.txt"
        destination.write_text(candidate, encoding="utf-8")
        metrics = minimality.analyze(original, candidate, 1.0, 1.0)
        rows.append(
            {
                "id": operation["id"],
                "factor": operation["factor"],
                "path": str(destination),
                "sha256": digest(candidate),
                "doc_change_ratio": metrics["doc_change_ratio"],
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
