#!/usr/bin/env python3
"""Build and maintain a lossless long-document segment map for Palimpsest v3.

Every character belongs to exactly one segment.  `sync` rebuilds the map after
an edit, preserves identities where possible, and marks new or changed content.
Detector evidence is intentionally kept in state.py and is bound to each
segment's current SHA-256 digest.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402
import _v3lib as V  # noqa: E402

SCHEMA = "palimpsest.segments.v3"
DEFAULT_MAP = Path("workspace/SEGMENTS.json")
STATUSES = {"new", "unreviewed", "editing", "reviewed", "verified", "parked"}


def fail(message: str, code: int = 2) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return code


def sha(text: str) -> str:
    return V.sha256_text(text)


def word_count(text: str) -> int:
    return len(T.words(text))


def line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def title_of(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:100]
        return stripped[:100]
    return ""


def match_text(body: str) -> str:
    normalized = " ".join(body.split())
    if len(normalized) <= 1600:
        return normalized
    return normalized[:800] + "\n…\n" + normalized[-800:]


def paragraph_blocks(text: str) -> list[tuple[int, int]]:
    """Return contiguous paragraph-ish blocks that exactly partition text."""
    if not text:
        return [(0, 0)]
    blocks: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"\n[ \t]*\n+", text):
        end = match.end()
        blocks.append((start, end))
        start = end
    if start < len(text):
        blocks.append((start, len(text)))
    if not blocks:
        blocks.append((0, len(text)))
    return blocks


def segment_ranges(text: str, target: int, minimum: int, maximum: int) -> list[tuple[int, int]]:
    if minimum <= 0 or target < minimum or maximum < target:
        raise ValueError("require 0 < minimum <= target <= maximum")
    blocks = paragraph_blocks(text)
    ranges: list[tuple[int, int]] = []
    start = blocks[0][0]
    end = start
    words = 0
    for block_start, block_end in blocks:
        body = text[block_start:block_end]
        block_words = word_count(body)
        would_exceed = words > 0 and words + block_words > maximum
        enough = words >= minimum
        heading_boundary = bool(re.match(r"\s*#{1,6}\s+\S", body))
        if would_exceed or (enough and words >= target and heading_boundary):
            ranges.append((start, end))
            start = block_start
            words = 0
        end = block_end
        words += block_words
        if words >= target and words >= minimum:
            ranges.append((start, end))
            start = end
            words = 0
    if start < len(text) or not ranges:
        ranges.append((start, len(text)))
    if len(ranges) > 1:
        a, b = ranges[-1]
        if word_count(text[a:b]) < minimum:
            prev_a, _ = ranges[-2]
            if word_count(text[prev_a:b]) <= maximum:
                ranges[-2:] = [(prev_a, b)]
    return ranges


def make_segment(text: str, start: int, end: int, sid: str) -> dict:
    body = text[start:end]
    return {
        "id": sid,
        "title": title_of(body),
        "start": start,
        "end": end,
        "line_from": line_at(text, start),
        "line_to": line_at(text, max(start, end - 1)),
        "words": word_count(body),
        "current_sha256": sha(body),
        "baseline_sha256": sha(body),
        "match_text": match_text(body),
        "status": "unreviewed",
        "changed": False,
        "new": False,
        "risk": [],
        "notes": "",
    }


def build_map(text: str, source: Path, target: int, minimum: int, maximum: int) -> dict:
    ranges = segment_ranges(text, target, minimum, maximum)
    return {
        "schema": SCHEMA,
        "version": "3.0.0",
        "source": str(source.resolve()),
        "file_sha256": sha(text),
        "length_chars": len(text),
        "words": word_count(text),
        "updated_at": V.now(),
        "parameters": {"target_words": target, "minimum_words": minimum, "maximum_words": maximum},
        "segments": [
            make_segment(text, start, end, f"S{index:03d}")
            for index, (start, end) in enumerate(ranges, start=1)
        ],
    }


def load_map(path: Path) -> dict:
    data = V.load_json(path)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"unsupported segment schema {data.get('schema')!r}; expected {SCHEMA}")
    return data


def old_body(data: dict, segment: dict) -> str:
    if segment.get("match_text"):
        return str(segment["match_text"])
    source = Path(data["source"])
    if not source.is_file() or V.sha256_file(source) != data.get("file_sha256"):
        return ""
    text = V.read_text(source)
    return text[segment["start"]:segment["end"]]


def similarity(a: str, b: str) -> float:
    a_norm = " ".join(a.split()).casefold()
    b_norm = " ".join(b.split()).casefold()
    if not a_norm and not b_norm:
        return 1.0
    return difflib.SequenceMatcher(None, a_norm, b_norm, autojunk=False).ratio()


def next_id(old: list[dict]) -> int:
    nums = []
    for item in old:
        match = re.fullmatch(r"S(\d+)", str(item.get("id", "")))
        if match:
            nums.append(int(match.group(1)))
    return max(nums, default=0) + 1


def sync_map(old_data: dict, text: str, source: Path) -> dict:
    params = old_data["parameters"]
    fresh = build_map(
        text,
        source,
        int(params["target_words"]),
        int(params["minimum_words"]),
        int(params["maximum_words"]),
    )
    old_segments = old_data.get("segments", [])
    old_texts = {item["id"]: old_body(old_data, item) for item in old_segments}
    unused = {item["id"] for item in old_segments}
    next_num = next_id(old_segments)

    for item in fresh["segments"]:
        body = text[item["start"]:item["end"]]
        exact = next(
            (
                old for old in old_segments
                if old["id"] in unused and old.get("current_sha256") == item["current_sha256"]
            ),
            None,
        )
        chosen = exact
        score = 1.0 if exact else 0.0
        if chosen is None and unused:
            candidates = []
            for old in old_segments:
                if old["id"] not in unused:
                    continue
                old_text = old_texts.get(old["id"], "")
                candidates.append((similarity(old_text, body), old))
            if candidates:
                score, possible = max(candidates, key=lambda pair: pair[0])
                if score >= 0.55:
                    chosen = possible
        if chosen is None:
            item["id"] = f"S{next_num:03d}"
            next_num += 1
            item["status"] = "new"
            item["changed"] = True
            item["new"] = True
            item["baseline_sha256"] = ""
            item["match_confidence"] = 0.0
            continue
        unused.remove(chosen["id"])
        item["id"] = chosen["id"]
        item["baseline_sha256"] = chosen.get("baseline_sha256") or chosen.get("current_sha256", "")
        item["match_text"] = match_text(body)
        item["risk"] = list(chosen.get("risk", []))
        item["notes"] = chosen.get("notes", "")
        changed = item["current_sha256"] != chosen.get("current_sha256")
        item["changed"] = changed or bool(chosen.get("changed"))
        item["new"] = bool(chosen.get("new"))
        item["status"] = "editing" if changed else chosen.get("status", "unreviewed")
        item["match_confidence"] = round(score, 4)

    fresh["orphaned_segment_ids"] = sorted(unused)
    fresh["updated_at"] = V.now()
    return fresh


def validation(data: dict, text: str) -> tuple[bool, list[str], dict]:
    problems: list[str] = []
    segments = data.get("segments", [])
    cursor = 0
    total_chars = 0
    ids: set[str] = set()
    for index, item in enumerate(segments, start=1):
        sid = item.get("id", f"index {index}")
        if sid in ids:
            problems.append(f"duplicate id {sid}")
        ids.add(sid)
        start, end = item.get("start"), item.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            problems.append(f"{sid}: invalid range")
            continue
        if start != cursor:
            problems.append(f"{sid}: coverage discontinuity at {cursor}->{start}")
        if end < start or end > len(text):
            problems.append(f"{sid}: invalid end {end}")
            continue
        body = text[start:end]
        if sha(body) != item.get("current_sha256"):
            problems.append(f"{sid}: stale content digest")
        cursor = end
        total_chars += end - start
    if cursor != len(text):
        problems.append(f"tail not mapped: cursor={cursor}, text={len(text)}")
    if data.get("file_sha256") != sha(text):
        problems.append("map file_sha256 is stale")
    if data.get("length_chars") != len(text):
        problems.append("map length_chars is stale")
    metrics = {
        "segments": len(segments),
        "mapped_chars": total_chars,
        "total_chars": len(text),
        "coverage_pct": 100.0 if len(text) == 0 else round(100 * total_chars / len(text), 4),
        "changed": sum(bool(x.get("changed")) for x in segments),
        "new": sum(bool(x.get("new")) for x in segments),
        "risk": sum(bool(x.get("risk")) for x in segments),
        "orphaned": len(data.get("orphaned_segment_ids", [])),
    }
    return not problems, problems, metrics


def cmd_map(args: argparse.Namespace) -> int:
    source = V.resolve_existing(args.file)
    out = args.out.expanduser().resolve()
    text = V.read_text(source)
    try:
        if out.exists() and not args.force:
            return fail(f"map exists: {out}; use sync or map --force")
        if out.exists() and args.force:
            data = sync_map(load_map(out), text, source)
        else:
            data = build_map(text, source, args.target, args.minimum, args.maximum)
        V.atomic_write_json(out, data)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    print(f"mapped {len(data['segments'])} segment(s), 100% of {len(text)} characters -> {out}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    path = args.map.expanduser().resolve()
    try:
        old = load_map(path)
        source = V.resolve_existing(args.file or old["source"])
        text = V.read_text(source)
        data = sync_map(old, text, source)
        V.atomic_write_json(path, data)
    except (ValueError, OSError, json.JSONDecodeError, FileNotFoundError) as exc:
        return fail(str(exc))
    print(
        f"synced {len(data['segments'])} segment(s): "
        f"{sum(x['changed'] for x in data['segments'])} changed, "
        f"{sum(x['new'] for x in data['segments'])} new, "
        f"{len(data['orphaned_segment_ids'])} orphaned"
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        data = load_map(args.map.expanduser().resolve())
        text = V.read_text(data["source"])
        ok, problems, metrics = validation(data, text)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    payload = {"ok": ok, "metrics": metrics, "problems": problems}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"coverage={metrics['coverage_pct']:.1f}% segments={metrics['segments']} "
            f"changed={metrics['changed']} new={metrics['new']} risk={metrics['risk']}"
        )
        for problem in problems:
            print(f"- {problem}")
    return 0 if ok else 1


def find_segment(data: dict, sid: str) -> dict:
    for item in data.get("segments", []):
        if item.get("id") == sid:
            return item
    raise ValueError(f"unknown segment {sid}")


def cmd_show(args: argparse.Namespace) -> int:
    try:
        data = load_map(args.map.expanduser().resolve())
        item = find_segment(data, args.id)
        text = V.read_text(args.file or data["source"])
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    print(text[item["start"]:item["end"]])
    return 0


def priority(item: dict) -> tuple:
    status_weight = {"new": 0, "editing": 1, "unreviewed": 2, "parked": 3, "reviewed": 4, "verified": 5}
    return (
        0 if item.get("risk") else 1,
        0 if item.get("changed") else 1,
        status_weight.get(item.get("status", "unreviewed"), 9),
        item.get("start", 0),
    )


def cmd_next(args: argparse.Namespace) -> int:
    try:
        data = load_map(args.map.expanduser().resolve())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    candidates = [x for x in data["segments"] if x.get("status") != "verified"]
    if not candidates:
        print("none")
        return 0
    item = min(candidates, key=priority)
    print(f"{item['id']}\t{item['status']}\t{item['words']}\t{item['title']}")
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    try:
        data = load_map(args.map.expanduser().resolve())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    forced = [x for x in data["segments"] if x.get("changed") or x.get("new") or x.get("risk")]
    chosen = {x["id"]: x for x in forced}
    remaining = [x for x in data["segments"] if x["id"] not in chosen]
    if args.count > len(chosen) and remaining:
        slots = min(args.count - len(chosen), len(remaining))
        for i in range(slots):
            index = round(i * (len(remaining) - 1) / max(1, slots - 1))
            chosen[remaining[index]["id"]] = remaining[index]
    result = sorted(chosen.values(), key=lambda x: x["start"])
    if args.json:
        print(json.dumps([x["id"] for x in result], ensure_ascii=False))
    else:
        print(",".join(x["id"] for x in result))
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    try:
        data = load_map(args.map.expanduser().resolve())
        item = find_segment(data, args.id)
        text = V.read_text(args.file or data["source"])
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    index = data["segments"].index(item)
    before = data["segments"][index - 1] if index else None
    after = data["segments"][index + 1] if index + 1 < len(data["segments"]) else None
    payload = {
        "segment": item,
        "seam_before": text[max(0, before["end"] - 240):before["end"]] if before else "",
        "text": text[item["start"]:item["end"]],
        "seam_after": text[after["start"]:min(len(text), after["start"] + 240)] if after else "",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["text"])
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    path = args.map.expanduser().resolve()
    try:
        with V.locked_json(path) as data:
            if data.get("schema") != SCHEMA:
                raise ValueError("not a Palimpsest v3 segment map")
            item = find_segment(data, args.id)
            if args.status:
                item["status"] = args.status
            if args.risk:
                for tag in V.parse_csv(args.risk):
                    if tag not in item["risk"]:
                        item["risk"].append(tag)
            if args.clear_risk:
                item["risk"] = []
            if args.note is not None:
                item["notes"] = args.note
            data["updated_at"] = V.now()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    print(f"{args.id}: status={item['status']} risk={','.join(item['risk']) or 'none'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("map", help="create an exact-coverage v3 map")
    command.add_argument("file")
    command.add_argument("--out", type=Path, default=DEFAULT_MAP)
    command.add_argument("--target", type=int, default=320)
    command.add_argument("--min", dest="minimum", type=int, default=180)
    command.add_argument("--max", dest="maximum", type=int, default=450)
    command.add_argument("--force", action="store_true")
    command.set_defaults(func=cmd_map)

    command = sub.add_parser("sync", help="rebuild after editing and preserve identities")
    command.add_argument("--file")
    command.set_defaults(func=cmd_sync)

    command = sub.add_parser("status", help="validate digests and exact coverage")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_status)

    command = sub.add_parser("next", help="show the next risk/change-first segment")
    command.set_defaults(func=cmd_next)

    command = sub.add_parser("sample", help="choose a deterministic risk-stratified sample")
    command.add_argument("--count", type=int, default=5)
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_sample)

    command = sub.add_parser("show", help="print one exact segment")
    command.add_argument("id")
    command.add_argument("--file")
    command.set_defaults(func=cmd_show)

    command = sub.add_parser("pack", help="emit a bounded segment and its seams")
    command.add_argument("id")
    command.add_argument("--file")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_pack)

    command = sub.add_parser("mark", help="record workflow status or risk tags")
    command.add_argument("id")
    command.add_argument("--status", choices=sorted(STATUSES))
    command.add_argument("--risk")
    command.add_argument("--clear-risk", action="store_true")
    command.add_argument("--note")
    command.set_defaults(func=cmd_mark)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
