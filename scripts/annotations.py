#!/usr/bin/env python3
"""Palimpsest: слой редакторской разметки в рабочей копии (работа «в редакторе»).

Синтаксис (см. references/annotation.md):
  span:  \u27e6F12|P0|RU-L1-stoitotmetit|ZeroGPT+GPTZero|open\u27e7 текст \u27e6/F12\u27e7
  point: \u27e6!N3|voice|автор так абзац не начинает\u27e7
  типы по первой букве id: F finding, P parked, Q question, A anchor, V voice, C candidate, N note

Usage:
  python3 annotations.py WORKING.md --list
  python3 annotations.py WORKING.md --open          # что ещё не закрыто
  python3 annotations.py WORKING.md --stats
  python3 annotations.py WORKING.md --strip > CLEAN.md
  python3 annotations.py WORKING.md --check-clean   # exit 1, если разметка осталась
  python3 annotations.py WORKING.md --validate      # парность, дубли id, статусы

Смысл: агент обязан сначала помечать, потом править. Разметка — рабочая память
между раундами; в поставку она попасть не может (гейт G-clean).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402

TAG = re.compile(r"\u27e6(/?)([!]?[A-ZА-Я]+\d*[a-zA-Z0-9_-]*)((?:\|[^\u27e7]*)?)\u27e7")
STATUSES = {"open", "in-progress", "fixed", "verified", "parked", "waived", "rejected"}
TYPE_NAMES = {
    "F": "finding",
    "P": "parked",
    "Q": "question",
    "A": "anchor",
    "V": "voice",
    "C": "candidate",
    "N": "note",
}


def parse(text: str) -> dict:
    marks: list[dict] = []
    stack: dict[str, dict] = {}
    errors: list[str] = []
    seen_ids: Counter = Counter()

    for m in TAG.finditer(text):
        closing, mid, meta = m.group(1) == "/", m.group(2), m.group(3).lstrip("|")
        fields = [f.strip() for f in meta.split("|")] if meta else []
        point = mid.startswith("!")
        clean_id = mid.lstrip("!")
        line = text.count("\n", 0, m.start()) + 1
        if point:
            marks.append(
                {
                    "id": clean_id,
                    "type": TYPE_NAMES.get(clean_id[0], "note"),
                    "kind": "point",
                    "fields": fields,
                    "status": next((f for f in fields if f in STATUSES), "open"),
                    "line": line,
                    "span": "",
                }
            )
            seen_ids[clean_id] += 1
            continue
        if closing:
            open_mark = stack.pop(clean_id, None)
            if not open_mark:
                errors.append(f"строка {line}: закрывающий \u27e6/{clean_id}\u27e7 без открывающего")
                continue
            open_mark["span"] = text[open_mark["_end"] : m.start()]
            open_mark["span_words"] = len(T.WORD.findall(open_mark["span"]))
            open_mark.pop("_end", None)
            marks.append(open_mark)
        else:
            if clean_id in stack:
                errors.append(f"строка {line}: повторное открытие \u27e6{clean_id}\u27e7 без закрытия")
            seen_ids[clean_id] += 1
            stack[clean_id] = {
                "id": clean_id,
                "type": TYPE_NAMES.get(clean_id[0], "note"),
                "kind": "span",
                "fields": fields,
                "status": next((f for f in fields if f in STATUSES), "open"),
                "line": line,
                "_end": m.end(),
            }
    for mid, mk in stack.items():
        errors.append(f"строка {mk['line']}: \u27e6{mid}\u27e7 не закрыт")
    dupes = [i for i, c in seen_ids.items() if c > 1]
    if dupes:
        errors.append("дублирующиеся id: " + ", ".join(sorted(dupes)))
    for mk in marks:
        bad = [f for f in mk["fields"] if f in STATUSES]
        if len(bad) > 1:
            errors.append(f"{mk['id']}: несколько статусов {bad}")
    marks.sort(key=lambda x: x["line"])
    return {"marks": marks, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--strip", action="store_true")
    ap.add_argument("--check-clean", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.path.exists():
        print(f"FAIL: not found: {args.path}", file=sys.stderr)
        return 2
    text = T.read_text(args.path)

    if args.strip:
        sys.stdout.write(re.sub(r"[ \t]{2,}", " ", TAG.sub("", text)))
        return 0

    parsed = parse(text)
    marks, errors = parsed["marks"], parsed["errors"]
    unresolved = [m for m in marks if m["type"] in ("finding", "parked", "question") and m["status"] in ("open", "in-progress", "parked")]

    if args.check_clean:
        if marks:
            print(f"NOT CLEAN: {len(marks)} марок осталось в {args.path}")
            for m in marks[:15]:
                print(f"  строка {m['line']}: {m['id']} ({m['status']})")
            return 1
        print("CLEAN: разметки нет — файл можно отдавать")
        return 0

    if args.validate or errors:
        print("VALIDATE: " + ("ошибок нет" if not errors else f"{len(errors)} ошибок"))
        for e in errors:
            print("  " + e)
        if args.validate:
            return 1 if errors else 0

    if args.json:
        print(json.dumps({"marks": marks, "errors": errors, "unresolved": len(unresolved)}, ensure_ascii=False, indent=2))
        return 1 if errors else 0

    if args.stats or not (args.list or args.open):
        by_type = Counter(m["type"] for m in marks)
        by_status = Counter(m["status"] for m in marks)
        print(f"{args.path}: {len(marks)} марок")
        print("  типы:    " + (", ".join(f"{k}={v}" for k, v in by_type.items()) or "—"))
        print("  статусы: " + (", ".join(f"{k}={v}" for k, v in by_status.items()) or "—"))
        print(f"  не закрыто: {len(unresolved)}")
    if args.list:
        for m in marks:
            print(f"  стр.{m['line']:4} {m['id']:8} {m['type']:9} {m['status']:11} {'|'.join(m['fields'])[:60]}")
            if m.get("span"):
                print(f"        «{m['span'].strip()[:100]}»")
    if args.open:
        if not unresolved:
            print("Открытых марок нет.")
        for m in unresolved:
            print(f"  стр.{m['line']:4} {m['id']:8} {m['status']:11} {'|'.join(m['fields'])[:70]}")
            if m.get("span"):
                print(f"        «{m['span'].strip()[:100]}»")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
