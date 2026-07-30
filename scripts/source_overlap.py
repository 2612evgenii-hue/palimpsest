#!/usr/bin/env python3
"""Screen a draft for close lexical overlap with supplied source files.

This is a local evidence screen, not a substitute for an external plagiarism
database.  It ignores fenced code and quoted passages, then finds contiguous
word runs shared with the user-supplied source corpus.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _v3lib as V  # noqa: E402

SCHEMA = "palimpsest.overlap.v3"
WORD_RE = re.compile(r"[^\W_]+(?:[-’'][^\W_]+)*", re.UNICODE)


def tokens(text: str) -> list[str]:
    return [match.group(0).casefold() for match in WORD_RE.finditer(text)]


def unquoted_text(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", " ", text)
    text = re.sub(r"«[^»]*»|“[^”]*”|\"[^\"\n]*\"", " ", text)
    return text


def paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n[ \t]*\n+", unquoted_text(text)) if part.strip()]


def excerpt(words: list[str], start: int, length: int) -> str:
    left = max(0, start - 4)
    right = min(len(words), start + length + 4)
    prefix = "… " if left else ""
    suffix = " …" if right < len(words) else ""
    return prefix + " ".join(words[left:right]) + suffix


def source_index(paths: list[Path], ngram: int) -> tuple[dict, list[dict], dict[str, list[str]]]:
    index: dict[tuple[str, ...], list[tuple[str, int]]] = defaultdict(list)
    metadata: list[dict] = []
    source_tokens: dict[str, list[str]] = {}
    for number, path in enumerate(paths, start=1):
        source_id = f"SRC{number:03d}"
        text = unquoted_text(V.read_text(path))
        words = tokens(text)
        source_tokens[source_id] = words
        metadata.append(
            {
                "id": source_id,
                "path": str(path),
                "sha256": V.sha256_file(path),
                "words": len(words),
            }
        )
        for i in range(max(0, len(words) - ngram + 1)):
            index[tuple(words[i:i + ngram])].append((source_id, i))
    return index, metadata, source_tokens


def longest_run(
    draft_words: list[str],
    index: dict,
    ngram: int,
) -> tuple[int, int, str, int] | None:
    previous: dict[tuple[str, int], tuple[int, int]] = {}
    best: tuple[int, int, str, int] | None = None
    for draft_pos in range(max(0, len(draft_words) - ngram + 1)):
        key = tuple(draft_words[draft_pos:draft_pos + ngram])
        current: dict[tuple[str, int], tuple[int, int]] = {}
        for source_id, source_pos in index.get(key, []):
            diagonal = source_pos - draft_pos
            chain_key = (source_id, diagonal)
            prior_len, prior_start = previous.get(chain_key, (0, draft_pos))
            run_ngrams = prior_len + 1
            run_start = prior_start if prior_len else draft_pos
            current[chain_key] = (run_ngrams, run_start)
            run_words = ngram + run_ngrams - 1
            candidate = (run_words, run_start, source_id, source_pos - run_ngrams + 1)
            if best is None or candidate[0] > best[0]:
                best = candidate
        previous = current
    return best


def analyze(draft: Path, sources: list[Path], ngram: int, min_run: int, ratio: float) -> dict:
    index, source_meta, source_words = source_index(sources, ngram)
    findings = []
    for paragraph_number, paragraph in enumerate(paragraphs(V.read_text(draft)), start=1):
        draft_words = tokens(paragraph)
        if len(draft_words) < ngram:
            continue
        run = longest_run(draft_words, index, ngram)
        if not run:
            continue
        run_words, draft_start, source_id, source_start = run
        overlap_ratio = run_words / max(1, len(draft_words))
        high_risk = run_words >= min_run or (run_words >= ngram + 2 and overlap_ratio >= ratio)
        findings.append(
            {
                "paragraph": paragraph_number,
                "source_id": source_id,
                "run_words": run_words,
                "paragraph_words": len(draft_words),
                "overlap_ratio": round(overlap_ratio, 4),
                "risk": "high" if high_risk else "review",
                "draft_excerpt": excerpt(draft_words, draft_start, run_words),
                "source_excerpt": excerpt(source_words[source_id], source_start, run_words),
            }
        )
    return {
        "schema": SCHEMA,
        "version": "3.0.0",
        "created_at": V.now(),
        "draft": str(draft),
        "draft_sha256": V.sha256_file(draft),
        "configuration": {
            "ngram_words": ngram,
            "minimum_high_risk_run_words": min_run,
            "minimum_high_risk_paragraph_ratio": ratio,
            "quoted_and_fenced_code_excluded": True,
        },
        "sources": source_meta,
        "high_risk_count": sum(item["risk"] == "high" for item in findings),
        "review_count": sum(item["risk"] == "review" for item in findings),
        "matches": findings,
        "limitations": [
            "Only supplied local sources are searched.",
            "Semantic copying without a shared lexical run can evade this screen.",
            "Quoted text is excluded here and must be checked separately for citation accuracy.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--ngram", type=int, default=8)
    parser.add_argument("--min-run", type=int, default=16)
    parser.add_argument("--ratio", type=float, default=0.35)
    parser.add_argument("--out")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.ngram < 4:
        print("FAIL: --ngram must be >=4", file=sys.stderr)
        return 2
    if args.min_run < args.ngram:
        print("FAIL: --min-run must be >= --ngram", file=sys.stderr)
        return 2
    if not 0 < args.ratio <= 1:
        print("FAIL: --ratio must be within (0,1]", file=sys.stderr)
        return 2
    try:
        draft = V.resolve_existing(args.draft)
        sources = [V.resolve_existing(path) for path in args.source]
        payload = analyze(draft, sources, args.ngram, args.min_run, args.ratio)
        if args.out:
            V.atomic_write_json(Path(args.out).expanduser().resolve(), payload)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"high_risk={payload['high_risk_count']} review={payload['review_count']} "
            f"sources={len(payload['sources'])}"
        )
        if args.out:
            print(f"report={Path(args.out).expanduser().resolve()}")
    return 1 if payload["high_risk_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
