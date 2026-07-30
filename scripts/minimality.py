#!/usr/bin/env python3
"""Palimpsest: бюджет правок — сколько текста ты реально тронул.

Usage:
  python3 minimality.py --original ORIG.md --current WORKING.md
  python3 minimality.py --original ORIG.md --current WORKING.md --budget 0.15 --para-budget 0.40
  python3 minimality.py --original ORIG.md --current WORKING.md --json

Идея: «минимальные правки» — не декларация, а измеримая величина. Скрипт считает
долю изменённых слов по документу и по каждому абзацу, находит абзацы,
переписанные сверх бюджета, и показывает, где хирургия превратилась в ремонт.
Exit 1 = бюджет превышен (нужно либо откатить лишнее, либо явно поднять бюджет в GOAL.md).
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402


def wordlist(text: str) -> list[str]:
    return T.WORD.findall(T.mask_protected(T.strip_annotations(text)).lower())


def change_ratio(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 0.0
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    matched = sum(bl.size for bl in sm.get_matching_blocks())
    return round(1 - (2 * matched) / (len(a) + len(b) or 1), 4)


def align(orig_paras, cur_paras) -> list[tuple]:
    """Greedy alignment original→current by similarity; unmatched = added/removed."""
    pairs = []
    used = set()
    for op in orig_paras:
        ow = T.WORD.findall(op.text.lower())
        best, best_score = None, 0.0
        for cp in cur_paras:
            if cp.index in used:
                continue
            cw = T.WORD.findall(cp.text.lower())
            score = difflib.SequenceMatcher(a=ow, b=cw, autojunk=False).quick_ratio()
            if score > best_score:
                best, best_score = cp, score
        if best is not None and best_score >= 0.35:
            used.add(best.index)
            pairs.append((op, best))
        else:
            pairs.append((op, None))
    for cp in cur_paras:
        if cp.index not in used:
            pairs.append((None, cp))
    return pairs


def analyze(original: str, current: str, budget: float, para_budget: float) -> dict:
    ow, cw = wordlist(original), wordlist(current)
    doc_ratio = change_ratio(ow, cw)
    op = [p for p in T.paragraphs(original) if p.kind != "code"]
    cp = [p for p in T.paragraphs(current) if p.kind != "code"]
    rows = []
    for o, c in align(op, cp):
        if o is None:
            rows.append({"orig": None, "cur": c.index, "words": len(c.words), "ratio": 1.0, "status": "added"})
            continue
        if c is None:
            rows.append({"orig": o.index, "cur": None, "words": len(o.words), "ratio": 1.0, "status": "removed"})
            continue
        r = change_ratio(T.WORD.findall(o.text.lower()), T.WORD.findall(c.text.lower()))
        rows.append(
            {
                "orig": o.index,
                "cur": c.index,
                "words": len(o.words),
                "ratio": r,
                "status": "untouched" if r == 0 else ("over-budget" if r > para_budget else "edited"),
                "preview": c.text[:70].replace("\n", " "),
            }
        )
    touched = [r for r in rows if r["ratio"] > 0]
    over = [r for r in rows if r["status"] == "over-budget"]
    return {
        "doc_change_ratio": doc_ratio,
        "doc_budget": budget,
        "doc_ok": doc_ratio <= budget,
        "words": {"original": len(ow), "current": len(cw), "delta_pct": round(100 * (len(cw) - len(ow)) / max(len(ow), 1), 1)},
        "paragraphs": {
            "total": len(op),
            "untouched": sum(1 for r in rows if r["status"] == "untouched"),
            "edited": sum(1 for r in rows if r["status"] == "edited"),
            "over_budget": len(over),
            "added": sum(1 for r in rows if r["status"] == "added"),
            "removed": sum(1 for r in rows if r["status"] == "removed"),
        },
        "para_budget": para_budget,
        "over_budget_paragraphs": sorted(over, key=lambda r: -r["ratio"])[:20],
        "rows": sorted(touched, key=lambda r: -r["ratio"]),
        "ok": doc_ratio <= budget and not over,
        "efficiency_note": "КПД правки = снижение AI% и ductus-distance на единицу изменённого текста; "
        "фиксируй его в ROUND-отчёте.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--original", type=Path, required=True)
    ap.add_argument("--current", type=Path, required=True)
    ap.add_argument("--budget", type=float, default=0.18, help="доля изменённых слов по документу (default 0.18)")
    ap.add_argument("--para-budget", type=float, default=0.45, help="доля изменённых слов в абзаце (default 0.45)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = analyze(T.read_text(args.original), T.read_text(args.current), args.budget, args.para_budget)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1

    p = res["paragraphs"]
    print(f"MINIMALITY: изменено {res['doc_change_ratio']*100:.1f}% слов (бюджет {res['doc_budget']*100:.0f}%) "
          f"→ {'OK' if res['doc_ok'] else 'ПРЕВЫШЕН'}")
    print(f"  объём: {res['words']['original']} → {res['words']['current']} слов ({res['words']['delta_pct']:+}%)")
    print(f"  абзацы: всего {p['total']}, не тронуто {p['untouched']}, правлено {p['edited']}, "
          f"сверх бюджета {p['over_budget']}, добавлено {p['added']}, удалено {p['removed']}")
    if res["over_budget_paragraphs"]:
        print(f"\nАБЗАЦЫ СВЕРХ БЮДЖЕТА (>{res['para_budget']*100:.0f}% слов):")
        for r in res["over_budget_paragraphs"]:
            print(f"  абз.{r['orig']}→{r['cur']}: {r['ratio']*100:.0f}% ({r['words']} слов) «{r.get('preview','')}»")
    top = [r for r in res["rows"] if r["status"] == "edited"][:10]
    if top:
        print("\nСамые заметные правки в бюджете:")
        for r in top:
            print(f"  абз.{r['orig']}: {r['ratio']*100:.0f}%")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
