#!/usr/bin/env python3
"""Palimpsest: Ductus distance -- measurable gap between текст и почерк референса.

Usage:
  python3 style_distance.py --ref REF.md [REF2.md ...] --cand WORKING.md [--json]
  python3 style_distance.py --ref-profile ductus.json --cand WORKING.md
  python3 style_distance.py --ref R.md --cand W.md --baseline ORIGINAL.md   # прогресс

Distance 0..100 (0 = habits identical). Не «оценка качества»: это карта того,
чем твой текст отличается от почерка автора, с конкретными ходами на сближение.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402
from style_metrics import merge_profiles, profile  # noqa: E402

# (path, label, scale, group, hint_high, hint_low)
FEATURES = [
    (("sentence_length", "mean"), "средняя длина предложения", 6.0, "rhythm",
     "предложения длиннее авторских: дели или урезай хвосты",
     "предложения короче авторских: соединяй мысли, добавляй зависимые части"),
    (("sentence_length", "cov"), "разброс длин (CoV)", 0.18, "rhythm",
     "разброс больше авторского: убери резкие скачки",
     "разброс меньше авторского (метроном): нужны и короткие, и длинные предложения"),
    (("sentence_length", "range"), "размах длин", 14.0, "rhythm",
     "размах больше авторского",
     "размах меньше авторского: не хватает крайних длин"),
    (("sentence_length", "mid_band_share"), "доля 12–20 слов", 0.22, "rhythm",
     "слишком много «средних» предложений — типичный машинный метроном",
     "мало предложений средней длины относительно автора"),
    (("paragraph", "words_mean"), "слов в абзаце", 35.0, "structure",
     "абзацы длиннее авторских", "абзацы короче авторских"),
    (("paragraph", "sentences_mean"), "предложений в абзаце", 1.8, "structure",
     "абзацы плотнее авторских", "абзацы дробнее авторских"),
    (("paragraph", "words_stdev"), "разброс длин абзацев", 25.0, "structure",
     "абзацы разнороднее авторских",
     "абзацы одинаковой длины — автор так не пишет"),
    (("openers", "distinct_first_word_ratio"), "разнообразие начал предложений", 0.20, "structure",
     "начала разнообразнее авторских (редко проблема)",
     "начала однотипные: смени первое слово в части предложений"),
    (("lexicon", "mattr_100"), "лексическое разнообразие MATTR", 0.08, "lexicon",
     "лексика разнообразнее авторской: автор повторяет термины чаще",
     "лексика беднее авторской"),
    (("lexicon", "stopword_share"), "доля служебных слов", 0.06, "lexicon",
     "больше служебных слов, чем у автора (рыхлее)",
     "меньше служебных слов: текст плотнее и суше авторского"),
    (("lexicon", "avg_word_len"), "средняя длина слова", 0.7, "lexicon",
     "слова длиннее авторских (книжнее)", "слова короче авторских"),
    (("lexicon", "long_word_share_9plus"), "доля длинных слов (9+)", 0.07, "lexicon",
     "перегруз длинными словами", "меньше длинных слов, чем у автора"),
    (("punctuation_per_1000w", "comma"), "запятые /1000", 22.0, "punctuation",
     "запятых больше авторского", "запятых меньше авторского"),
    (("punctuation_per_1000w", "em_dash"), "длинное тире /1000", 6.0, "punctuation",
     "тире больше авторского — классический AI-tell",
     "тире меньше авторского"),
    (("punctuation_per_1000w", "colon"), "двоеточия /1000", 5.0, "punctuation",
     "двоеточий больше авторского", "двоеточий меньше авторского"),
    (("punctuation_per_1000w", "semicolon"), "точки с запятой /1000", 3.0, "punctuation",
     "точек с запятой больше авторского", "точек с запятой меньше авторского"),
    (("punctuation_per_1000w", "paren_open"), "скобки /1000", 5.0, "punctuation",
     "скобок больше авторского", "скобок меньше авторского"),
    (("punctuation_per_1000w", "question"), "вопросы /1000", 3.0, "punctuation",
     "вопросов больше авторского", "вопросов меньше авторского"),
    (("discourse", "connectives_per_1000w"), "связки /1000", 8.0, "discourse",
     "связок больше авторского: убери часть «таким образом/более того»",
     "связок меньше авторского"),
    (("discourse", "hedges_per_1000w"), "хеджи /1000", 6.0, "discourse",
     "больше осторожных оговорок, чем у автора",
     "меньше оговорок: автор чаще страхует утверждения"),
    (("discourse", "boosters_per_1000w"), "усилители /1000", 4.5, "discourse",
     "усилителей больше авторского (важно/ключевой/несомненно)",
     "усилителей меньше авторского"),
    (("discourse", "nominalization_per_1000w"), "отглагольные существительные /1000", 30.0, "discourse",
     "канцелярита больше авторского: возвращай глаголы",
     "меньше отглагольных, чем у автора"),
    (("discourse", "passive_markers_per_1000w"), "пассив /1000", 25.0, "discourse",
     "пассива больше авторского", "пассива меньше авторского"),
    (("discourse", "first_person_per_1000w"), "первое лицо /1000", 6.0, "discourse",
     "личное присутствие сильнее авторского",
     "личное присутствие слабее авторского"),
    (("specificity", "numbers_per_1000w"), "числа /1000", 9.0, "specificity",
     "чисел больше авторского", "чисел меньше авторского: автор конкретнее"),
    (("repetition", "repeated_4grams_per_1000w"), "повторяющиеся 4-граммы /1000", 2.5, "specificity",
     "повторяет одинаковые формулировки чаще автора",
     "меньше самоповторов, чем у автора"),
]

GROUP_WEIGHTS = {
    "rhythm": 0.26,
    "structure": 0.16,
    "lexicon": 0.15,
    "punctuation": 0.13,
    "discourse": 0.22,
    "specificity": 0.08,
}


def get(prof: dict, path: tuple[str, str]) -> float:
    node = prof
    for k in path:
        node = node.get(k, 0) if isinstance(node, dict) else 0
    return float(node) if isinstance(node, (int, float)) else 0.0


def connective_overlap(ref: dict, cand: dict) -> tuple[float, list[str], list[str]]:
    r = set(ref["discourse"]["connective_inventory"])
    c = set(cand["discourse"]["connective_inventory"])
    if not r and not c:
        return 1.0, [], []
    jac = len(r & c) / len(r | c) if (r | c) else 1.0
    return jac, sorted(c - r), sorted(r - c)


def compare(ref: dict, cand: dict, quarantine: set[str] | None = None) -> dict:
    quarantine = quarantine or set()
    rows = []
    for path, label, scale, group, hi, lo in FEATURES:
        rv, cv = get(ref, path), get(cand, path)
        # Признак может отличаться максимум "полностью": иначе один саботажный признак
        # маскирует прогресс по остальным, и метрика перестаёт быть монотонной.
        gap = abs(cv - rv) / scale if scale else 0.0
        gap = min(gap, 1.0)
        rows.append(
            {
                "feature": ".".join(path),
                "label": label,
                "group": group,
                "ref": round(rv, 3),
                "cand": round(cv, 3),
                "delta": round(cv - rv, 3),
                "gap": round(gap, 3),
                "hint": hi if cv > rv else lo,
            }
        )
    by_group: dict[str, list[dict]] = {}
    for r in rows:
        by_group.setdefault(r["group"], []).append(r)

    jac, extra_conn, missing_conn = connective_overlap(ref, cand)
    conn_gap = 1.0 - jac
    by_group.setdefault("discourse", []).append(
        {
            "feature": "discourse.connective_inventory",
            "label": "совпадение набора связок (Jaccard)",
            "group": "discourse",
            "ref": len(ref["discourse"]["connective_inventory"]),
            "cand": len(cand["discourse"]["connective_inventory"]),
            "delta": round(jac, 3),
            "gap": round(conn_gap, 3),
            "hint": "автор использует другой набор связок — подменяй на его инвентарь",
        }
    )

    for r in [r for rs in by_group.values() for r in rs]:
        r["quarantined"] = r["feature"] in quarantine

    def weighted(rows_filter) -> float:
        gs = {}
        for g, rs in by_group.items():
            keep = [r for r in rs if rows_filter(r)]
            if keep:
                gs[g] = min(T.mean(r["gap"] for r in keep), 1.0)
        if not gs:
            return 0.0
        return round(
            100 * sum(GROUP_WEIGHTS.get(g, 0) * s for g, s in gs.items())
            / sum(GROUP_WEIGHTS.get(g, 0) for g in gs),
            1,
        )

    group_scores = {g: min(T.mean(r["gap"] for r in rs), 1.0) for g, rs in by_group.items()}
    full_distance = weighted(lambda r: True)
    distance = weighted(lambda r: not r["quarantined"])
    if distance <= 15:
        verdict = "почерк совпадает (в допуске автора)"
    elif distance <= 28:
        verdict = "близко: остались локальные привычки"
    elif distance <= 45:
        verdict = "узнаваемо другой почерк"
    else:
        verdict = "другой автор: имитации нет"

    worst = sorted(
        [r for rs in by_group.values() for r in rs if not r["quarantined"]],
        key=lambda r: -r["gap"] * GROUP_WEIGHTS.get(r["group"], 0.1),
    )
    reliability = "ok"
    if cand["size"]["words"] < 250 or ref["size"]["words"] < 400:
        reliability = (
            "low: стилометрия на коротком тексте шумит "
            "(надёжно от ~400 слов референса и ~250 слов кандидата)"
        )

    return {
        "distance": distance,
        "full_distance": full_distance,
        "quarantined": sorted(quarantine),
        "verdict": verdict,
        "reliability": reliability,
        "group_scores": {g: round(s * 100, 1) for g, s in group_scores.items()},
        "rows": rows,
        "worst": worst[:8],
        "connectives": {
            "jaccard": round(jac, 3),
            "yours_not_authors": extra_conn[:12],
            "authors_not_yours": missing_conn[:12],
        },
        "sizes": {"ref_words": ref["size"]["words"], "cand_words": cand["size"]["words"]},
    }


def load_profile(paths: list[Path] | None, profile_path: Path | None, para: bool = False) -> dict:
    if profile_path:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    profs = [profile(T.read_text(p), para) for p in paths or []]
    return merge_profiles(profs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", nargs="*", type=Path, default=[])
    ap.add_argument("--ref-profile", type=Path)
    ap.add_argument("--cand", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, help="исходный текст до правок: покажет прогресс")
    ap.add_argument(
        "--quarantine",
        default="",
        help="признаки из DUCTUS.md, которые нельзя переносить (жанровый конфликт), через запятую: "
        "discourse.first_person_per_1000w,punctuation_per_1000w.exclam",
    )
    ap.add_argument("--gate", type=float, help="порог: exit 1, если distance выше")
    ap.add_argument("--list-features", action="store_true", help="показать имена признаков для --quarantine")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.list_features:
        for path, label, *_ in FEATURES:
            print(f"{'.'.join(path):48} {label}")
        print(f"{'discourse.connective_inventory':48} совпадение набора связок")
        return 0
    if not args.ref and not args.ref_profile:
        print("FAIL: нужен --ref FILE... или --ref-profile JSON", file=sys.stderr)
        return 2
    quarantine = {q.strip() for q in args.quarantine.split(",") if q.strip()}
    ref = load_profile(args.ref, args.ref_profile)
    cand = profile(T.read_text(args.cand))
    res = compare(ref, cand, quarantine)
    if args.baseline and args.baseline.exists():
        base = compare(ref, profile(T.read_text(args.baseline)), quarantine)
        res["baseline_distance"] = base["distance"]
        res["improvement"] = round(base["distance"] - res["distance"], 1)

    fail = args.gate is not None and res["distance"] > args.gate
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if fail else 0

    print(f"DUCTUS DISTANCE: {res['distance']}/100 — {res['verdict']}")
    if res["quarantined"]:
        print(f"  (по переносимым признакам; в карантине {len(res['quarantined'])}: "
              f"{', '.join(res['quarantined'])}; полная дистанция {res['full_distance']})")
    if "baseline_distance" in res:
        print(f"было: {res['baseline_distance']} → стало: {res['distance']} (сближение {res['improvement']})")
    print(f"reliability: {res['reliability']}  (ref={res['sizes']['ref_words']}w, cand={res['sizes']['cand_words']}w)")
    print("по группам: " + ", ".join(f"{g}={v}" for g, v in sorted(res["group_scores"].items(), key=lambda kv: -kv[1])))
    print("\nГЛАВНЫЕ РАСХОЖДЕНИЯ (что закрывать первым):")
    for r in res["worst"]:
        print(f"  [{r['group']:11}] {r['label']}: автор={r['ref']} ты={r['cand']} (Δ{r['delta']:+}) → {r['hint']}")
    c = res["connectives"]
    if c["yours_not_authors"]:
        print("\nсвязки, которых у автора нет: " + ", ".join(c["yours_not_authors"]))
    if c["authors_not_yours"]:
        print("связки автора, которых нет у тебя: " + ", ".join(c["authors_not_yours"]))
    if args.gate is not None:
        print(f"\nГЕЙТ: порог {args.gate} → {'НЕ ПРОЙДЕН' if fail else 'пройден'}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
