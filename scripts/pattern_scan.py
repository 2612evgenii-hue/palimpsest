#!/usr/bin/env python3
"""Palimpsest: deterministic AI-tell scan (RU+EN), cluster-aware, span-addressed.

Usage:
  python3 pattern_scan.py WORKING.md              # текстовый отчёт
  python3 pattern_scan.py WORKING.md --json
  python3 pattern_scan.py WORKING.md --min-sev P1 --top 20
  python3 pattern_scan.py WORKING.md --paragraph 7    # только один абзац

Advisory. Истина по F1 — браузерные детекторы. Скрипт нужен, чтобы (а) не искать
глазами то, что ищется регуляркой, (б) видеть кластеры и метроном, (в) иметь
одинаковые ID находок между раундами.
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

# id, severity, lang, pattern, label, fix-hint (moves from references/surgery.md)
PATTERNS: list[tuple[str, str, str, str, str, str]] = [
    # ---------- EN lexical tier-1 ----------
    ("EN-L1-delve", "P0", "en", r"\bdelv(?:e|es|ing|ed)\b", "delve", "M-LEX-1 заменить на конкретный глагол действия"),
    ("EN-L1-tapestry", "P0", "en", r"\b(?:rich |intricate )?tapestry\b", "tapestry (фигур.)", "M-LEX-1"),
    ("EN-L1-testament", "P0", "en", r"\b(?:a|is a) testament to\b", "testament to", "M-LEX-1 + M-CLAIM-2"),
    ("EN-L1-underscore", "P0", "en", r"\bunderscor(?:e|es|ing|ed)\b", "underscores", "M-LEX-1 → shows/means"),
    ("EN-L1-landscape", "P0", "en", r"\b(?:evolving|changing|dynamic|today'?s)\s+landscape\b", "evolving landscape", "M-OPEN-3 выкинуть рамку"),
    ("EN-L1-realm", "P0", "en", r"\bin the realm of\b", "in the realm of", "M-LEX-1 → in"),
    ("EN-L1-worthnoting", "P0", "en", r"\bit(?:'s| is) worth noting\b", "it is worth noting", "M-OPEN-1 удалить зачин"),
    ("EN-L1-navigate", "P1", "en", r"\bnavigat(?:e|es|ing|ed)\s+(?:the\s+)?(?:complexit|challeng|landscape)", "navigate complexities", "M-LEX-1"),
    ("EN-L1-interplay", "P1", "en", r"\binterplay\b", "interplay", "M-LEX-1"),
    ("EN-L1-multifaceted", "P1", "en", r"\bmulti-?faceted\b", "multifaceted", "M-LEX-1"),
    ("EN-L1-leverage", "P1", "en", r"\bleverag(?:e|es|ing|ed)\b", "leverage (глагол)", "M-LEX-1 → use"),
    ("EN-L1-moreover", "P1", "en", r"\b(?:moreover|furthermore)\b", "moreover/furthermore", "M-CONN-1 снять или заменить на авторскую связку"),
    ("EN-L1-inconclusion", "P1", "en", r"\bin conclusion\b", "in conclusion", "M-CLOSE-1"),
    ("EN-L2-crucial", "P2", "en", r"\b(?:crucial|pivotal|vital|paramount)\b", "significance inflation", "M-CLAIM-1 конкретика вместо оценки"),
    ("EN-L2-robust", "P2", "en", r"\b(?:robust|seamless(?:ly)?|holistic|comprehensive)\b", "оценочные штампы", "M-LEX-1"),
    ("EN-L2-foster", "P2", "en", r"\b(?:foster|bolster|showcase)(?:s|ing|ed)?\b", "foster/bolster/showcase", "M-LEX-1"),
    ("EN-S-copula", "P1", "en", r"\b(?:serves as|stands as|boasts|plays a (?:key|crucial|vital) role)\b", "copula avoidance", "M-SYN-4 → is/has"),
    ("EN-S-notbut", "P1", "en", r"\bnot (?:just|only|merely) [^.;]{3,60}\bbut\b", "not just X but Y", "M-SYN-2 разбить на два утверждения"),
    ("EN-S-notabout", "P0", "en", r"\bit(?:'s|\u2019s| is) not (?:just |only |merely )?(?:about|that) [^.;]{3,80}it(?:'s|\u2019s| is)\b", "it's not X, it's Y", "M-SYN-2"),
    ("EN-S-ingtail", "P1", "en", r",\s+(?:highlighting|underscoring|emphasizing|showcasing|fostering|reflecting|demonstrating|ensuring|allowing|enabling)\b", "-ing хвост-комментарий", "M-SYN-3 отрезать хвост или сделать отдельным предложением"),
    ("EN-S-vague", "P1", "en", r"\b(?:experts?|studies|researchers?|analysts?)\s+(?:say|says|show|shows|argue|argues|suggest|suggests|believe)\b", "vague attribution", "M-FACT-1 указать источник или ослабить"),
    ("EN-S-throat", "P0", "en", r"\b(?:here'?s the thing|let that sink in|make no mistake|the truth is|full stop)\b", "throat-clearing", "M-OPEN-1"),
    ("EN-S-range", "P2", "en", r"\bfrom [\w\s-]{3,25} to [\w\s-]{3,25}\b", "ложный диапазон", "M-LEX-2 назвать конкретные случаи"),
    ("EN-S-future", "P1", "en", r"\bthe future (?:looks|of) [^.]{0,40}(?:bright|promising)\b", "generic uplift ending", "M-CLOSE-1"),
    ("EN-S-dive", "P2", "en", r"\b(?:let'?s (?:dive|explore|unpack)|in this (?:article|section), we)\b", "meta-навигация", "M-OPEN-1"),
    ("EN-ART-chatbot", "P0", "en", r"\b(?:as an ai|i hope this helps|i cannot|certainly!|great question)\b", "chatbot artifact", "M-ART-1 удалить"),
    # ---------- RU lexical / штампы ----------
    ("RU-L1-stoitotmetit", "P0", "ru", r"(?<![^\W\d_])(?:стоит|следует|необходимо|важно)\s+(?:отметить|подчеркнуть|заметить|сказать|учитывать)", "«стоит отметить»", "M-OPEN-1 удалить зачин, начать с сути"),
    ("RU-L1-takimobrazom", "P0", "ru", r"(?<![^\W\d_])таким образом", "«таким образом»", "M-CONN-1"),
    ("RU-L1-vsovremennom", "P0", "ru", r"(?<![^\W\d_])в (?:современном мире|современных условиях|сегодняшних реалиях|эпоху)", "«в современном мире»", "M-OPEN-3 выкинуть рамку"),
    ("RU-L1-nelzyaneupomyanut", "P0", "ru", r"(?<![^\W\d_])нельзя не (?:упомянуть|отметить|сказать)", "«нельзя не упомянуть»", "M-OPEN-1"),
    ("RU-L1-igraetrol", "P0", "ru", r"(?<![^\W\d_])игра(?:ет|ют)\s+(?:важн\w+|ключев\w+|значим\w+|существенн\w+)\s+рол", "«играет ключевую роль»", "M-CLAIM-1 сказать, что именно делает"),
    ("RU-L1-yavlyaetsya", "P1", "ru", r"(?<![^\W\d_])явля(?:ется|ются)\b", "«является» вместо связки", "M-SYN-4 тире или глагол действия"),
    ("RU-L1-predstavlyaet", "P1", "ru", r"(?<![^\W\d_])представля(?:ет|ют) собой", "«представляет собой»", "M-SYN-4"),
    ("RU-L1-osushchestvlyaet", "P1", "ru", r"(?<![^\W\d_])осуществля(?:ет|ют|ется|ются)\b", "«осуществляется»", "M-SYN-5 вернуть действующий глагол"),
    ("RU-L1-danniy", "P2", "ru", r"(?<![^\W\d_])данн(?:ый|ая|ое|ого|ой|ому)\b", "канцелярское «данный»", "M-LEX-3 → этот/такой/убрать"),
    ("RU-L1-vramkah", "P2", "ru", r"(?<![^\W\d_])в рамках\b", "«в рамках»", "M-LEX-3"),
    ("RU-L1-vsvyazi", "P2", "ru", r"(?<![^\W\d_])в связи с (?:тем|этим|вышеизложенным)", "«в связи с тем»", "M-CONN-1"),
    ("RU-L1-slozhno", "P1", "ru", r"(?<![^\W\d_])(?:сложно|трудно) переоценить", "«трудно переоценить»", "M-CLAIM-1"),
    ("RU-L1-bezuslovno", "P2", "ru", r"(?<![^\W\d_])(?:безусловно|несомненно|очевидно, что|разумеется)", "усилители без доказательства", "M-CLAIM-2"),
    ("RU-L1-podvodya", "P1", "ru", r"(?<![^\W\d_])(?:подводя итог|в заключение (?:можно|стоит|следует)|обобщая (?:всё|все) вышесказанное)", "шаблонный финал", "M-CLOSE-1"),
    ("RU-L1-kompleksniy", "P2", "ru", r"(?<![^\W\d_])(?:комплексн\w+ подход|системн\w+ подход|целостн\w+ картин)", "«комплексный подход»", "M-LEX-3"),
    ("RU-L1-neotemlemoy", "P1", "ru", r"(?<![^\W\d_])неотъемлем\w+ част", "«неотъемлемая часть»", "M-LEX-3"),
    ("RU-L1-postoyanno", "P2", "ru", r"(?<![^\W\d_])(?:постоянно|стремительно) (?:развива|меня|раст)\w+", "«стремительно развивается»", "M-CLAIM-1"),
    ("RU-S-notbut", "P1", "ru", r"(?<![^\W\d_])не (?:просто|только|столько) [^.;]{3,60}\b(?:а|но|сколько)\b", "«не просто X, а Y»", "M-SYN-2"),
    ("RU-S-vopros-otvet", "P2", "ru", r"\?\s+(?:Ответ|Всё|Все|Дело в том)", "риторический вопрос-ответ", "M-OPEN-2"),
    ("RU-S-vaguesource", "P1", "ru", r"(?<![^\W\d_])(?:эксперты|исследовани\w+|специалисты|учёные|ученые|аналитики)\s+(?:сходятся|показывают|утверждают|считают|отмечают|говорят)", "источник без ссылки", "M-FACT-1"),
    ("RU-S-pervih", "P2", "ru", r"(?<![^\W\d_])во-первых", "нумерованный штабель", "M-STRUCT-2 если триада механическая"),
    ("RU-ART-chatbot", "P0", "ru", r"(?<![^\W\d_])(?:как (?:ии|искусственный интеллект)|надеюсь, это поможет|конечно!|отличный вопрос)", "chatbot artifact", "M-ART-1"),
    # ---------- language-agnostic artifacts ----------
    ("ANY-ART-citeturn", "P0", "any", r"citeturn\d*|oaicite|\ue200|\ue202|utm_source=(?:chatgpt|openai)", "LLM-артефакт", "M-ART-1 удалить"),
    ("ANY-ART-placeholder", "P0", "any", r"\[(?:вставить|insert|TODO|placeholder|your \w+)[^\]]{0,40}\]|\bLorem ipsum\b", "placeholder", "M-ART-1"),
    ("ANY-ART-md-bold-abuse", "P2", "any", r"\*\*[^*\n]{1,40}\*\*[,.:;]?\s+\*\*[^*\n]{1,40}\*\*", "штабель болда", "M-FORM-1"),
    ("ANY-ART-emoji", "P2", "any", r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "эмодзи", "M-FORM-1 (если не в почерке автора)"),
]

STRUCTURAL_HINTS = {
    "metronome": "M-RHY-1: 3+ предложения подряд почти одной длины — сломай ритм в одном месте, не во всех",
    "opener-repeat": "M-OPEN-2: одинаковое первое слово в 3+ предложениях подряд/абзацах",
    "twin-paragraphs": "M-STRUCT-1: абзацы-близнецы (та же длина + тот же тип зачина + та же схема)",
    "triad-stack": "M-STRUCT-2: навязчивая триада (три однородных члена/пункта в одном такте)",
    "uniform-closings": "M-CLOSE-2: каждый абзац заканчивается выводом/моралью",
    "list-parallelism": "M-STRUCT-3: все пункты списка одной синтаксической формы и длины",
    "dash-cluster": "M-FORM-2: тире-кластер (3+ длинных тире на 300 слов)",
    "elegant-variation": "M-LEX-4: синонимическая карусель — один референт называется 3+ способами",
}

SEV_ORDER = {"P0": 0, "P1": 1, "P2": 2}
SEV_WEIGHT = {"P0": 6.0, "P1": 3.0, "P2": 1.0}


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_patterns(text: str, lang: str) -> list[dict]:
    masked = T.mask_protected(T.strip_annotations(text))
    out = []
    for pid, sev, plang, rx, label, hint in PATTERNS:
        if plang not in ("any", lang):
            continue
        for m in re.finditer(rx, masked, flags=re.IGNORECASE):
            s, e = m.span()
            out.append(
                {
                    "id": pid,
                    "severity": sev,
                    "label": label,
                    "match": masked[s:e][:80],
                    "context": masked[max(0, s - 45) : e + 45].replace("\n", " ").strip(),
                    "offset": s,
                    "line": line_of(masked, s),
                    "fix": hint,
                }
            )
    return out


def structural(text: str, lang: str) -> list[dict]:
    paras = T.paragraphs(text)
    prose = [p for p in paras if p.kind in ("prose", "quote")]
    findings: list[dict] = []

    def metronome(p, run: int, band: int) -> dict:
        # метроном в средней полосе (12–25 слов) — главный машинный ритм;
        # серия коротких фраз чаще авторская привычка → мягче
        sev = "P1" if (12 <= band <= 25 or run >= 4) else "P2"
        return {
            "id": "STRUCT-metronome",
            "severity": sev,
            "label": f"метроном: {run} предложения подряд ~{band} слов",
            "paragraph": p.index,
            "line": line_of(text, p.start),
            "fix": STRUCTURAL_HINTS["metronome"],
            "structural": True,
        }

    for p in prose:
        lens = [len(T.WORD.findall(s)) for s in p.sentences]
        run, start = 1, 0
        for i in range(1, len(lens)):
            if abs(lens[i] - lens[i - 1]) <= 2:
                run += 1
            else:
                if run >= 3:
                    findings.append(metronome(p, run, lens[start]))
                run, start = 1, i
        if run >= 3:
            findings.append(metronome(p, run, lens[start]))

        firsts = [(T.WORD.findall(s) or ["?"])[0].lower() for s in p.sentences]
        for w, c in Counter(firsts).items():
            if c >= 3:
                findings.append(
                    {
                        "id": "STRUCT-opener-repeat",
                        "severity": "P1",
                        "label": f"«{w}» открывает {c} предложения в абзаце",
                        "paragraph": p.index,
                        "line": line_of(text, p.start),
                        "fix": STRUCTURAL_HINTS["opener-repeat"],
                        "structural": True,
                    }
                )
        dashes = p.text.count("\u2014")
        if len(p.words) >= 40 and dashes >= 3 and dashes * 300 / len(p.words) >= 6:
            findings.append(
                {
                    "id": "STRUCT-dash-cluster",
                    "severity": "P2",
                    "label": f"{dashes} длинных тире на {len(p.words)} слов",
                    "paragraph": p.index,
                    "line": line_of(text, p.start),
                    "fix": STRUCTURAL_HINTS["dash-cluster"] + " — сверь с DUCTUS: у автора это может быть привычкой",
                    "structural": True,
                }
            )
        triad = re.search(
            r"(\b[\w-]+\b(?:\s+[\w-]+){0,3}),\s+(\b[\w-]+\b(?:\s+[\w-]+){0,3})\s+(?:и|and)\s+(\b[\w-]+\b(?:\s+[\w-]+){0,3})",
            p.text,
        )
        if triad and len(p.sentences) >= 2:
            trip = [len(x.split()) for x in triad.groups()]
            if max(trip) - min(trip) <= 1:
                findings.append(
                    {
                        "id": "STRUCT-triad",
                        "severity": "P2",
                        "label": f"симметричная триада: «{triad.group(0)[:60]}»",
                        "paragraph": p.index,
                        "line": line_of(text, p.start),
                        "fix": STRUCTURAL_HINTS["triad-stack"],
                        "structural": True,
                    }
                )

    # twin paragraphs: same sentence count, near-equal words, same opener word class
    for a, b in zip(prose, prose[1:]):
        if not a.sentences or not b.sentences:
            continue
        wa, wb = len(a.words), len(b.words)
        if (
            len(a.sentences) == len(b.sentences)
            and abs(wa - wb) <= max(3, 0.08 * max(wa, wb))
            and (T.WORD.findall(a.sentences[0]) or [""])[0].lower()
            == (T.WORD.findall(b.sentences[0]) or [""])[0].lower()
        ):
            findings.append(
                {
                    "id": "STRUCT-twins",
                    "severity": "P1",
                    "label": f"абзацы {a.index} и {b.index} — близнецы ({wa}/{wb} слов, тот же зачин)",
                    "paragraph": b.index,
                    "line": line_of(text, b.start),
                    "fix": STRUCTURAL_HINTS["twin-paragraphs"],
                        "structural": True,
                }
            )

    # uniform closings: last sentence short + starts with a connective, repeatedly
    closers = 0
    conn = T.RU_CONNECTIVES if lang == "ru" else T.EN_CONNECTIVES
    for p in prose:
        if not p.sentences:
            continue
        last = p.sentences[-1].lower()
        if any(last.startswith(c) for c in conn):
            closers += 1
    if len(prose) >= 3 and closers >= max(2, int(0.5 * len(prose))):
        findings.append(
            {
                "id": "STRUCT-uniform-closings",
                "severity": "P1",
                "label": f"{closers} из {len(prose)} абзацев закрываются связкой-выводом",
                "paragraph": None,
                "line": None,
                "fix": STRUCTURAL_HINTS["uniform-closings"],
                        "structural": True,
            }
        )

    lists = [p for p in paras if p.kind == "list"]
    for p in lists:
        items = [ln.strip() for ln in p.text.splitlines() if ln.strip()]
        if len(items) >= 3:
            lens = [len(T.WORD.findall(i)) for i in items]
            firsts = [(T.WORD.findall(i) or ["?"])[0].lower() for i in items]
            if T.stdev(lens) < 1.5 and len(set(firsts)) <= max(1, len(items) // 3):
                findings.append(
                    {
                        "id": "STRUCT-list-parallel",
                        "severity": "P2",
                        "label": f"список из {len(items)} пунктов одинаковой формы и длины",
                        "paragraph": p.index,
                        "line": line_of(text, p.start),
                        "fix": STRUCTURAL_HINTS["list-parallelism"],
                        "structural": True,
                    }
                )
    return findings


def cluster(findings: list[dict], text: str) -> list[dict]:
    """Group findings by paragraph; a paragraph with 3+ hits or any P0 is a hotspot."""
    paras = T.paragraphs(text)
    bounds = [(p.index, p.start, p.end, p) for p in paras]

    def para_of(offset: int | None, given: int | None):
        if given:
            return given
        if offset is None:
            return None
        for idx, s, e, _ in bounds:
            if s <= offset <= e:
                return idx
        return None

    for f in findings:
        f["paragraph"] = para_of(f.get("offset"), f.get("paragraph"))
    groups: dict[int | None, list[dict]] = {}
    for f in findings:
        groups.setdefault(f["paragraph"], []).append(f)
    hotspots = []
    for idx, fs in groups.items():
        p0 = sum(1 for f in fs if f["severity"] == "P0")
        score = sum(SEV_WEIGHT[f["severity"]] for f in fs)
        pw = next((len(p.words) for p in paras if p.index == idx), 0) or 1
        hotspots.append(
            {
                "paragraph": idx,
                "hits": len(fs),
                "p0": p0,
                "density_per_100w": round(score * 100 / pw, 2),
                "score": round(score, 1),
                "priority": "P0" if p0 else ("P1" if len(fs) >= 3 else "P2"),
                "ids": sorted({f["id"] for f in fs}),
            }
        )
    hotspots = [h for h in hotspots if h["paragraph"] is not None]
    hotspots.sort(key=lambda h: (-h["p0"], -h["density_per_100w"], -h["hits"]))
    return hotspots


def advisory_score(findings: list[dict], words: int) -> float:
    """Лексическая плотность штампов + ограниченный вклад структурных находок.

    Структурные события считаются по количеству, а не по плотности: одна
    метрономная серия в коротком тексте не должна давать тот же вес, что
    двадцать штампов.
    """
    if not words:
        return 0.0
    lexical = [f for f in findings if not f.get("structural")]
    struct = [f for f in findings if f.get("structural")]
    lex_density = sum(SEV_WEIGHT[f["severity"]] for f in lexical) * 100 / words
    struct_points = min(len(struct), 6) * 3.0
    return round(min(100.0, lex_density * 2.0 + struct_points), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-sev", choices=["P0", "P1", "P2"], default="P2")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--paragraph", type=int, help="ограничиться одним абзацем")
    args = ap.parse_args()
    if not args.path.exists():
        print(f"FAIL: not found: {args.path}", file=sys.stderr)
        return 2

    text = T.read_text(args.path)
    lang = T.lang_of(text)
    findings = scan_patterns(text, lang) + structural(text, lang)
    findings = [f for f in findings if SEV_ORDER[f["severity"]] <= SEV_ORDER[args.min_sev]]
    hotspots = cluster(findings, text)
    if args.paragraph:
        findings = [f for f in findings if f.get("paragraph") == args.paragraph]
        hotspots = [h for h in hotspots if h["paragraph"] == args.paragraph]
    words = len(T.words(text))
    score = advisory_score(findings, words)
    counts = Counter(f["severity"] for f in findings)
    report = {
        "file": str(args.path),
        "lang": lang,
        "words": words,
        "advisory_ai_smell": score,
        "counts": {k: counts.get(k, 0) for k in ("P0", "P1", "P2")},
        "hotspots": hotspots[:15],
        "findings": sorted(findings, key=lambda f: (SEV_ORDER[f["severity"]], f.get("line") or 0))[: args.top],
        "note": "Advisory. Detector-gates решаются в браузере; здесь — воспроизводимые ID и кластеры.",
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"{args.path}  lang={lang}  words={words}")
    print(f"advisory AI-smell: {score}/100   P0={counts.get('P0',0)} P1={counts.get('P1',0)} P2={counts.get('P2',0)}")
    if hotspots:
        print("\nHOTSPOTS (порядок работы):")
        for h in hotspots[:10]:
            print(
                f"  абзац {h['paragraph']}: {h['hits']} находок, P0={h['p0']}, "
                f"плотность={h['density_per_100w']}/100сл → {h['priority']}  [{', '.join(h['ids'][:5])}]"
            )
    print("\nНАХОДКИ:")
    for f in report["findings"]:
        loc = f"стр.{f['line']}" if f.get("line") else "док"
        para = f"абз.{f['paragraph']}" if f.get("paragraph") else "-"
        print(f"  [{f['severity']}] {f['id']:24} {para:7} {loc:8} {f['label']}")
        if f.get("context"):
            print(f"      «{f['context'][:110]}»")
        print(f"      fix: {f['fix']}")
    print(f"\n{report['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
