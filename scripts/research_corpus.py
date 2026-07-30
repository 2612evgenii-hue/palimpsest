#!/usr/bin/env python3
"""Fetch a hash-pinned public research corpus from Hugging Face.

The manifest pins every dataset revision and row hash. Sources may use the
Hugging Face rows API or a bounded byte range from a pinned JSONL file. A
mutable upstream row can therefore never silently enter an experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import unicodedata
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


def read_range(url: str, start: int, length: int) -> bytes:
    if start < 0 or not 1 <= length <= 2_000_000:
        raise ValueError(f"unsafe byte range: start={start}, length={length}")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Palimpsest research/1",
            "Range": f"bytes={start}-{start + length - 1}",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    with urllib.request.urlopen(request, timeout=60, context=context) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise RuntimeError("range response exceeded the research safety limit")
    return payload


def find_jsonl_row(payload: bytes, row_id: str) -> dict:
    """Return one complete JSONL row from a possibly partial byte-range payload."""
    matches = []
    for raw_line in payload.splitlines():
        try:
            row = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and row.get("id") == row_id:
            matches.append(row)
    if len(matches) != 1:
        raise RuntimeError(f"expected one complete JSONL row for {row_id}, got {len(matches)}")
    return matches[0]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonicalize_text(text: str) -> str:
    """Normalize transport artifacts without changing visible prose structure."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip(" \t") for line in normalized.split("\n"))


def safe_id(value: str) -> str:
    if not value or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in value):
        raise ValueError(f"unsafe sample id: {value!r}")
    return value


def verify_dataset(dataset: dict) -> None:
    identity = read_json(
        "https://huggingface.co/api/datasets/"
        + urllib.parse.quote(dataset["id"], safe="/")
    )
    if identity.get("sha") != dataset["revision"]:
        raise RuntimeError(
            f"dataset revision changed: {identity.get('sha')} != {dataset['revision']}"
        )


def fetch_rows_api(dataset: dict, sample: dict) -> str:
    retrieval = dataset["retrieval"]
    query = urllib.parse.urlencode(
        {
            "dataset": dataset["id"],
            "config": retrieval["config"],
            "split": retrieval["split"],
            "offset": sample["row_index"],
            "length": 1,
        }
    )
    payload = read_json("https://datasets-server.huggingface.co/rows?" + query)
    rows = payload.get("rows", [])
    if len(rows) != 1 or rows[0].get("row_idx") != sample["row_index"]:
        raise RuntimeError(f"unexpected row response for {sample['id']}")
    row = rows[0]["row"]
    if row.get("src") != sample["source"]:
        raise RuntimeError(f"source mismatch for {sample['id']}")
    text = row.get("text")
    if not isinstance(text, str):
        raise RuntimeError(f"missing text for {sample['id']}")
    return text


def fetch_jsonl_range(dataset: dict, sample: dict) -> str:
    retrieval = dataset["retrieval"]
    file_url = (
        "https://huggingface.co/datasets/"
        + dataset["id"]
        + "/resolve/"
        + dataset["revision"]
        + "/"
        + urllib.parse.quote(retrieval["file_path"], safe="/")
    )
    payload = read_range(file_url, sample["range_start"], sample["range_length"])
    row = find_jsonl_row(payload, sample["row_id"])
    if row.get("model") != sample["model"]:
        raise RuntimeError(f"model mismatch for {sample['id']}")
    text = row.get(sample["field"])
    if not isinstance(text, str):
        raise RuntimeError(f"missing {sample['field']} for {sample['id']}")
    return text


def fetch(manifest_path: Path, out_dir: Path) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "palimpsest.research-corpus.v3":
        raise ValueError("unsupported research corpus schema")
    if manifest.get("canonicalization", {}).get("id") != "plain_text_v1":
        raise ValueError("unsupported corpus canonicalization")
    datasets = manifest["datasets"]
    for dataset in datasets.values():
        verify_dataset(dataset)

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for sample in manifest["samples"]:
        sample_id = safe_id(sample["id"])
        try:
            dataset = datasets[sample["dataset"]]
        except KeyError as error:
            raise ValueError(f"unknown dataset for {sample_id}") from error
        retrieval_type = dataset["retrieval"]["type"]
        if retrieval_type == "rows_api":
            text = fetch_rows_api(dataset, sample)
        elif retrieval_type == "jsonl_range":
            text = fetch_jsonl_range(dataset, sample)
        else:
            raise ValueError(f"unsupported retrieval type: {retrieval_type}")
        source_digest = sha256_text(text)
        if source_digest != sample["sha256"]:
            raise RuntimeError(f"source hash mismatch for {sample_id}: {source_digest}")
        canonical = canonicalize_text(text)
        digest = sha256_text(canonical)
        expected_canonical = sample.get("canonical_sha256", sample["sha256"])
        if digest != expected_canonical:
            raise RuntimeError(f"canonical hash mismatch for {sample_id}: {digest}")

        destination = out_dir / f"{sample_id}.txt"
        destination.write_text(canonical, encoding="utf-8")
        written.append(
            {
                "id": sample_id,
                "dataset": sample["dataset"],
                "path": str(destination),
                "sha256": digest,
                "source_sha256": source_digest,
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
