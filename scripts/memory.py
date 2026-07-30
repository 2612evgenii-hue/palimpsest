#!/usr/bin/env python3
"""Disk-backed project memory for Palimpsest v3.

The hot index is derived from current v3 state and segment evidence.  Detailed
notes remain on disk and are retrieved literally with file-and-line citations.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402
import _v3lib as V  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
STATE_SCHEMA = "palimpsest.state.v3.5"
SEGMENT_SCHEMA = "palimpsest.segments.v3"
KEEP_SECTIONS = ("инвариант", "manual", "ручн", "договор")
MAX_GENERATED_LINES = 220


def read_json(path: Path) -> dict | None:
    try:
        return V.load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def state_of(workspace: Path) -> dict | None:
    data = read_json(workspace / "STATE.json")
    return data if data and data.get("schema") == STATE_SCHEMA else None


def segments_of(workspace: Path) -> dict | None:
    data = read_json(workspace / "SEGMENTS.json")
    return data if data and data.get("schema") == SEGMENT_SCHEMA else None


def stamp(workspace: Path, key: str) -> None:
    path = workspace / "STATE.json"
    if not path.exists():
        return
    try:
        with V.locked_json(path) as state:
            if state.get("schema") != STATE_SCHEMA:
                return
            state.setdefault("memory", {})[key] = V.now()
    except (OSError, ValueError, json.JSONDecodeError):
        return


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    heading: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            sections[heading] = []
        elif heading is not None:
            sections[heading].append(line)
    return sections


def manual_sections(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    return {
        heading: body
        for heading, body in parse_sections(V.read_text(path)).items()
        if any(marker in heading.casefold() for marker in KEEP_SECTIONS)
    }


def add_limited(lines: list[str], section: list[str], omitted: list[str], name: str) -> None:
    if len(lines) + len(section) <= MAX_GENERATED_LINES:
        lines.extend(section)
    else:
        omitted.append(name)


def cmd_refresh(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    memory = workspace / "MEMORY.md"
    manual = manual_sections(memory)
    state = state_of(workspace)
    segment_map = segments_of(workspace)
    generated: list[str] = []
    omitted: list[str] = []

    task = state.get("task", workspace.name) if state else workspace.name
    generated.extend(
        [
            f"# MEMORY · {task}",
            f"обновлено: {V.now()}",
            "",
            "> Диск — источник истины. После сжатия: `memory.py resume`; "
            "если детали нет в файлах, её нельзя додумывать.",
            "",
        ]
    )
    invariant_heading = next(
        (heading for heading in manual if "инвариант" in heading.casefold()),
        "Инварианты (ручной раздел)",
    )
    invariant_body = manual.pop(invariant_heading, [])
    generated.extend([f"## {invariant_heading}"])
    generated.extend(
        invariant_body
        or [
            "- главный тезис: <заполнить после полного чтения>",
            "- жанр и аудитория: <заполнить>",
            "- защищённые смыслы/фрагменты: <заполнить>",
            "- терминология: см. TERMS.md",
        ]
    )
    generated.append("")

    if state:
        verification = state.get("verification", {})
        gates = verification.get("gates", {})
        blockers = [gate for gate, info in gates.items() if info.get("color") == "red"]
        limits = [gate for gate, info in gates.items() if info.get("color") == "yellow"]
        flags = ",".join(name for name, value in state.get("flags", {}).items() if value) or "none"
        policy = state.get("detector_policy", {})
        section = [
            "## Текущее состояние",
            f"- статус: {state.get('status')} · маршрут: {state.get('route')} · язык: {state.get('language')}",
            f"- функции: {flags}",
            f"- рабочий SHA-256: {verification.get('working_sha256') or 'ещё не проверен'}",
            f"- блокирующие гейты: {', '.join(blockers) if blockers else 'нет'}",
            f"- гейты с ограничениями: {', '.join(limits) if limits else 'нет'}",
            f"- детекторы: {', '.join(policy.get('selected_services', [])) or 'не выбраны'}; "
            f"порог {policy.get('threshold_pct', '-')}%; покрытие {policy.get('coverage', '-')}",
            f"- прямых результатов: {len(state.get('detector_results', []))}; "
            f"точечных waivers: {len(state.get('waivers', []))}",
            f"- зарегистрированные доказательства: "
            f"{', '.join(sorted(state.get('artifacts', {}))) or 'нет'}",
            "",
        ]
        add_limited(generated, section, omitted, "Текущее состояние")

    if segment_map:
        segments = segment_map.get("segments", [])
        section = [
            "## Карта длинного текста",
            f"- сегментов: {len(segments)} · символов: {segment_map.get('length_chars', 0)} "
            f"· слов: {segment_map.get('words', 0)}",
            f"- изменено: {sum(bool(x.get('changed')) for x in segments)} · "
            f"новых: {sum(bool(x.get('new')) for x in segments)} · "
            f"risk: {sum(bool(x.get('risk')) for x in segments)}",
            f"- сиротских прежних ID: {', '.join(segment_map.get('orphaned_segment_ids', [])) or 'нет'}",
            "- цикл: `segment.py next` → `pack` → правка → `sync` → `status` → `state.py verify`",
            "",
        ]
        add_limited(generated, section, omitted, "Карта длинного текста")

    note_files = sorted((workspace / "notes").glob("*.md")) if (workspace / "notes").exists() else []
    if note_files:
        section = ["## Холодный слой"]
        for path in note_files[:40]:
            first = next((line.strip() for line in V.read_text(path).splitlines() if line.strip()), "")
            section.append(f"- `{path.name}` — {first[:100]}")
        if len(note_files) > 40:
            section.append(f"- ещё {len(note_files) - 40} файлов: искать через `memory.py recall`")
        section.append("")
        add_limited(generated, section, omitted, "Холодный слой")

    handoff = workspace / "HANDOFF.md"
    if handoff.exists():
        bullets = [line for line in V.read_text(handoff).splitlines() if line.startswith("- ")][:12]
        add_limited(generated, ["## Последний handoff", *bullets, ""], omitted, "Последний handoff")

    if omitted:
        generated.extend(
            [
                "## Опущено из горячего индекса",
                f"- {', '.join(omitted)}",
                "- детали не потеряны: используйте `memory.py recall` по workspace.",
                "",
            ]
        )
    for heading, body in manual.items():
        generated.extend([f"## {heading}", *body, ""])

    with V.advisory_lock(memory):
        V.atomic_write_text(memory, "\n".join(generated).rstrip() + "\n")
    stamp(workspace, "last_refresh")
    print(f"MEMORY.md updated: {len(generated)} lines -> {memory}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    memory = workspace / "MEMORY.md"
    if not memory.exists():
        print("FAIL: MEMORY.md is missing; run memory.py refresh", file=sys.stderr)
        return 2
    print(V.read_text(memory))
    handoff = workspace / "HANDOFF.md"
    if handoff.exists():
        print("\n--- HANDOFF ---\n")
        print(V.read_text(handoff))
    state_path = workspace / "STATE.json"
    if state_path.exists():
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "state.py"), "--state", str(state_path), "show"],
            capture_output=True,
            text=True,
        )
        print("\n--- CURRENT GATES ---")
        print((proc.stdout or proc.stderr).strip())
    segment_path = workspace / "SEGMENTS.json"
    if segment_path.exists():
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "segment.py"), "--map", str(segment_path), "next"],
            capture_output=True,
            text=True,
        )
        print("\n--- NEXT SEGMENT ---")
        print((proc.stdout or proc.stderr).strip())
    stamp(workspace, "last_resume")
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state = state_of(workspace)
    segment_map = segments_of(workspace)
    lines = [f"# HANDOFF · {V.now()}", ""]
    if state:
        red = [
            gate for gate, info in state.get("verification", {}).get("gates", {}).items()
            if info.get("color") == "red"
        ]
        lines.extend(
            [
                f"- task: {state.get('task')}",
                f"- status: {state.get('status')} · route: {state.get('route')}",
                f"- blockers: {', '.join(red) if red else 'none'}",
            ]
        )
    if segment_map:
        changed = [x["id"] for x in segment_map.get("segments", []) if x.get("changed")]
        lines.append(f"- changed segments: {', '.join(changed) if changed else 'none'}")
    if args.next:
        lines.extend(["", "## Следующие шаги"])
        lines.extend(f"- {index}. {value}" for index, value in enumerate(args.next, start=1))
    if args.danger:
        lines.extend(["", "## Не трогать"])
        lines.extend(f"- {value}" for value in args.danger)
    if args.note:
        lines.extend(["", "## Заметка", f"- {args.note}"])
    lines.extend(
        [
            "",
            "## Возврат",
            "- `memory.py resume`",
            "- открыть только нужный сегмент/артефакт, а не весь проект",
            "- перед продолжением сверить текущие SHA-256 и гейты",
        ]
    )
    target = workspace / "HANDOFF.md"
    with V.advisory_lock(target):
        V.atomic_write_text(target, "\n".join(lines) + "\n")
    stamp(workspace, "last_handoff")
    print(f"handoff written -> {target}")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    notes = workspace / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w-]+", "-", args.topic.casefold()).strip("-") or "note"
    path = notes / f"{slug}.md"
    with V.advisory_lock(path):
        current = V.read_text(path) if path.exists() else f"# {args.topic}\n\n"
        V.atomic_write_text(path, current + f"- [{V.now()}] {args.text}\n")
    print(f"note written -> {path}")
    return 0


def cmd_recall(args: argparse.Namespace) -> int:
    roots = [Path(value).expanduser().resolve() for value in (args.in_ or [args.workspace])]
    try:
        pattern = re.compile(
            args.query if args.regex else re.escape(args.query),
            0 if args.case else re.IGNORECASE,
        )
    except re.error as exc:
        print(f"FAIL: invalid regular expression: {exc}", file=sys.stderr)
        return 2
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(
                sorted(path for path in root.rglob("*") if path.suffix.casefold() in {".md", ".json", ".txt"})
            )
    hits: list[tuple[Path, int, str]] = []
    for path in files:
        try:
            lines = V.read_text(path).splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            if pattern.search(line):
                hits.append((path, number, line.strip()[:240]))
                if len(hits) >= args.limit:
                    break
        if len(hits) >= args.limit:
            break
    if not hits:
        print(f"NOT FOUND: {args.query!r}. Do not reconstruct it from memory.")
        return 1
    for path, number, line in hits:
        print(f"{path}:{number}: {line}")
    return 0


def normalized_words(text: str) -> list[str]:
    return [word.casefold() for word in T.words(T.strip_annotations(T.mask_protected(text)))]


def phrase_counts(text: str, n_min: int, n_max: int) -> dict[tuple[str, ...], list[int]]:
    counts: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for paragraph in T.paragraphs(text):
        for sentence in paragraph.sentences or [paragraph.text]:
            words = normalized_words(sentence)
            for size in range(n_min, n_max + 1):
                for gram in T.ngrams(words, size):
                    counts[gram].append(paragraph.index)
    return counts


def contained(candidate: tuple[str, ...], selected: tuple[str, ...]) -> bool:
    if len(candidate) > len(selected):
        return False
    for index in range(len(selected) - len(candidate) + 1):
        if selected[index:index + len(candidate)] == candidate:
            return True
    return False


def cmd_echoes(args: argparse.Namespace) -> int:
    current = phrase_counts(V.read_text(args.current), args.n_min, args.n_max)
    original = phrase_counts(V.read_text(args.original), args.n_min, args.n_max) if args.original else {}
    candidates = []
    for phrase, locations in current.items():
        count_now = len(locations)
        count_before = len(original.get(phrase, []))
        if count_now < args.min_count:
            continue
        if count_before and count_now < max(args.min_count, count_before * 2):
            continue
        if all(word in T.RU_STOP or word in T.EN_STOP for word in phrase):
            continue
        candidates.append(
            {
                "phrase": " ".join(phrase),
                "_words": phrase,
                "count": count_now,
                "before": count_before,
                "paragraphs": sorted(set(locations)),
            }
        )
    candidates.sort(key=lambda item: (-len(item["_words"]), -item["count"], item["phrase"]))
    selected = []
    for item in candidates:
        if any(contained(item["_words"], chosen["_words"]) for chosen in selected):
            continue
        selected.append(item)
    selected = selected[:args.top]
    public = [{key: value for key, value in item.items() if key != "_words"} for item in selected]
    if args.json:
        print(json.dumps({"echoes": public}, ensure_ascii=False, indent=2))
    else:
        for item in public:
            print(
                f"{item['count']}x {item['phrase']!r} "
                f"(before {item['before']}x; paragraphs {item['paragraphs'][:10]})"
            )
        if not public:
            print("no edit-amplified phrase echoes")
    return 1 if public else 0


def collect_terms(text: str, minimum: int) -> dict[str, int]:
    words = [word.casefold() for word in T.words(T.strip_annotations(T.mask_protected(text)))]
    stop = T.RU_STOP | T.EN_STOP
    counts = Counter(
        word for word in words
        if len(word) >= 5 and word not in stop and not word.isdigit()
    )
    terms = {word: count for word, count in counts.items() if count >= minimum}
    for abbreviation in re.findall(r"\b[A-ZА-ЯЁ][A-ZА-ЯЁ0-9-]{1,9}\b", text):
        terms[abbreviation] = terms.get(abbreviation, 0) + 1
    return terms


def cmd_terms(args: argparse.Namespace) -> int:
    original = collect_terms(V.read_text(args.original), args.min_count)
    if args.current:
        current = collect_terms(V.read_text(args.current), 1)
        lost = [{"term": term, "before": count, "after": 0} for term, count in original.items() if not current.get(term)]
        thinned = [
            {"term": term, "before": count, "after": current.get(term, 0)}
            for term, count in original.items()
            if current.get(term, 0) and current.get(term, 0) < count * 0.5
        ]
        payload = {"lost": lost, "thinned": thinned}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "\n".join(
            [*(f"LOST {x['term']}: {x['before']} -> 0" for x in lost),
             *(f"THIN {x['term']}: {x['before']} -> {x['after']}" for x in thinned)]
        ) or "terminology preserved")
        return 1 if lost else 0
    workspace = Path(args.workspace).expanduser().resolve()
    rows = sorted(original.items(), key=lambda item: (-item[1], item[0]))[:args.top]
    lines = [
        f"# TERMS · {Path(args.original).name}",
        f"created: {V.now()}",
        "",
        "| term | count |",
        "|---|---:|",
        *(f"| {term} | {count} |" for term, count in rows),
    ]
    target = workspace / "TERMS.md"
    with V.advisory_lock(target):
        V.atomic_write_text(target, "\n".join(lines) + "\n")
    print(f"terms written: {len(rows)} -> {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default="workspace")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("refresh")
    command.set_defaults(func=cmd_refresh)

    command = sub.add_parser("resume")
    command.set_defaults(func=cmd_resume)

    command = sub.add_parser("handoff")
    command.add_argument("--next", action="append")
    command.add_argument("--danger", action="append")
    command.add_argument("--note")
    command.set_defaults(func=cmd_handoff)

    command = sub.add_parser("note")
    command.add_argument("--topic", required=True)
    command.add_argument("--text", required=True)
    command.set_defaults(func=cmd_note)

    command = sub.add_parser("recall")
    command.add_argument("query")
    command.add_argument("--in", dest="in_", action="append")
    command.add_argument("--case", action="store_true")
    command.add_argument("--regex", action="store_true", help="interpret QUERY as regex; literal is default")
    command.add_argument("--limit", type=int, default=60)
    command.set_defaults(func=cmd_recall)

    command = sub.add_parser("echoes")
    command.add_argument("--current", required=True)
    command.add_argument("--original")
    command.add_argument("--n-min", type=int, default=3)
    command.add_argument("--n-max", type=int, default=7)
    command.add_argument("--min-count", type=int, default=3)
    command.add_argument("--top", type=int, default=20)
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_echoes)

    command = sub.add_parser("terms")
    command.add_argument("--original", required=True)
    command.add_argument("--current")
    command.add_argument("--min-count", type=int, default=3)
    command.add_argument("--top", type=int, default=120)
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_terms)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
