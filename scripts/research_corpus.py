#!/usr/bin/env python3
"""Fetch a hash-pinned public research corpus from Hugging Face rows API.

The manifest pins the dataset revision and every row hash. A mutable upstream
row can therefore never silently enter an experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import certifi
except ImportError:  # pragma: no cover - depends on the host Python bundle
    certifi = None


def read_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Palimpsest research/1"})
    context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return json.load(response)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_id(value: str) -> str:
    if not value or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in value):
        raise ValueError(f"unsafe sample id: {value!r}")
    return value


def fetch(manifest_path: Path, out_dir: Path) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset = manifest["dataset"]
    identity = read_json(
        "https://huggingface.co/api/datasets/"
        + urllib.parse.quote(dataset["id"], safe="/")
    )
    if identity.get("sha") != dataset["revision"]:
        raise RuntimeError(
            f"dataset revision changed: {identity.get('sha')} != {dataset['revision']}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for sample in manifest["samples"]:
        sample_id = safe_id(sample["id"])
        query = urllib.parse.urlencode(
            {
                "dataset": dataset["id"],
                "config": dataset["config"],
                "split": dataset["split"],
                "offset": sample["row_index"],
                "length": 1,
            }
        )
        payload = read_json("https://datasets-server.huggingface.co/rows?" + query)
        rows = payload.get("rows", [])
        if len(rows) != 1 or rows[0].get("row_idx") != sample["row_index"]:
            raise RuntimeError(f"unexpected row response for {sample_id}")
        row = rows[0]["row"]
        text = row.get("text")
        if not isinstance(text, str):
            raise RuntimeError(f"missing text for {sample_id}")
        if row.get("src") != sample["source"]:
            raise RuntimeError(f"source mismatch for {sample_id}")
        digest = sha256_text(text)
        if digest != sample["sha256"]:
            raise RuntimeError(f"hash mismatch for {sample_id}: {digest}")

        destination = out_dir / f"{sample_id}.txt"
        destination.write_text(text, encoding="utf-8")
        written.append(
            {
                "id": sample_id,
                "path": str(destination),
                "sha256": digest,
                "partition": sample["partition"],
                "authorship": sample["authorship"],
            }
        )
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    written = fetch(args.manifest, args.out_dir)
    print(json.dumps({"written": written}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
