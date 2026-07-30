#!/usr/bin/env python3
"""Palimpsest: quantitative handwriting fingerprint (Ductus layer L1).

Usage:
  python3 style_metrics.py TEXT.md [--json] [--paragraphs]
  python3 style_metrics.py ref1.md ref2.md --json      # merged profile of several samples

Outputs a stable feature vector used by style_distance.py. Never a verdict on
"AI or human" -- only measurable habits of the text.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402


def opener_class(sentence: str, lang: str) -> str:
    w = T.WORD.findall(sentence)
    if not w:
        return "other"
    first = w[0].lower()
    stop = T.RU_STOP if lang == "ru" else T.EN_STOP
    conn = T.RU_CONNECTIVES if lang == "ru" else T.EN_CONNECTIVES
    low = sentence.lower()
    for c in conn:
        if low.startswith(c):
            return "connective"
    if T.NUMBER.match(sentence.strip()):
        return "numeral"
    if sentence.strip()[0] in "\u00ab\u201c\"'":
        return "quote"
    if first in ("это", "этот", "эта", "эти", "такой", "there", "this", "that", "these", "those", "it"):
        return "deictic"
    if first in stop:
        return "function-word"
    if sentence.strip()[0].isupper() and len(w) > 1 and w[1].lower() in stop:
        return "subject-first"
    return "content-word"


def sentence_shape(s: str) -> str:
    n = len(T.WORD.findall(s))
    if n <= 6:
        return "short"
    if n <= 14:
        return "mid"
    if n <= 25:
        return "long"
    return "very-long"


def profile(text: str, want_paragraphs: bool = False) -> dict:
    lang = T.lang_of(text)
    paras = T.paragraphs(text)
    prose = [p for p in paras if p.kind in ("prose", "quote")]
    sents: list[str] = []
    for p in prose:
        sents.extend(p.sentences)
    body = "\n\n".join(p.text for p in prose)
    masked = T.mask_protected(body)
    low = masked.lower()
    wl = T.words(body)
    total_w = len(wl)
    slen = [len(T.WORD.findall(s)) for s in sents]

    stop = T.RU_STOP if lang == "ru" else T.EN_STOP
    conn_list = T.RU_CONNECTIVES if lang == "ru" else T.EN_CONNECTIVES
    hedges = T.RU_HEDGES if lang == "ru" else T.EN_HEDGES
    boosters = T.RU_BOOSTERS if lang == "ru" else T.EN_BOOSTERS
    fp = T.RU_FIRST_PERSON if lang == "ru" else T.EN_FIRST_PERSON
    nomin = T.RU_NOMINALIZATION if lang == "ru" else T.EN_NOMINALIZATION
    passive = T.RU_PASSIVE if lang == "ru" else T.EN_PASSIVE

    mid_band = [x for x in slen if 12 <= x <= 20]
    runs = 0
    longest_run = 0
    cur = 1
    for a, b in zip(slen, slen[1:]):
        if abs(a - b) <= 3:
            cur += 1
        else:
            longest_run = max(longest_run, cur)
            if cur >= 3:
                runs += 1
            cur = 1
    longest_run = max(longest_run, cur)
    if cur >= 3:
        runs += 1

    openers = [opener_class(s, lang) for s in sents]
    first_words = [(T.WORD.findall(s) or ["?"])[0].lower() for s in sents]
    shapes = [sentence_shape(s) for s in sents]

    content = [w for w in wl if w not in stop and len(w) > 2]
    ttr = len(set(wl)) / total_w if total_w else 0.0
    win = 100
    if total_w >= win:
        mattr = T.mean(
            len(set(wl[i : i + win])) / win for i in range(0, total_w - win + 1, max(1, win // 2))
        )
    else:
        mattr = ttr
    hapax = sum(1 for _, c in Counter(content).items() if c == 1)

    def rx_count(rx) -> int:
        return len(rx.findall(masked))

    punct = {
        "comma": masked.count(","),
        "semicolon": masked.count(";"),
        "colon": masked.count(":"),
        "em_dash": masked.count("\u2014"),
        "en_dash": masked.count("\u2013"),
        "hyphen_as_dash": len([m for m in T.re.finditer(r"\s-\s", masked)]),
        "paren_open": masked.count("("),
        "quotes": masked.count("\u00ab") + masked.count("\u201c") + masked.count('"'),
        "question": masked.count("?"),
        "exclam": masked.count("!"),
        "ellipsis": masked.count("\u2026") + len(T.re.findall(r"\.\.\.", masked)),
    }
    punct_per_1000 = {k: T.per_1000(v, total_w) for k, v in punct.items()}

    conn_hits = T.count_phrases(low, conn_list)
    hedge_hits = T.count_phrases(low, hedges)
    boost_hits = T.count_phrases(low, boosters)
    fp_hits = sum(T.count_phrases(low, fp).values())

    rep4 = Counter(T.ngrams(wl, 4))
    repeated4 = {" ".join(k): v for k, v in rep4.items() if v >= 2}
    rep3_content = Counter(T.ngrams([w for w in wl if w not in stop], 3))
    repeated3c = {" ".join(k): v for k, v in rep3_content.items() if v >= 2}

    para_words = [len(p.words) for p in prose]
    para_sents = [len(p.sentences) for p in prose]

    prof = {
        "lang": lang,
        "size": {
            "words": total_w,
            "sentences": len(sents),
            "paragraphs_prose": len(prose),
            "paragraphs_total": len(paras),
            "headings": sum(1 for p in paras if p.kind == "heading"),
            "lists": sum(1 for p in paras if p.kind == "list"),
        },
        "sentence_length": {
            "mean": round(T.mean(slen), 2),
            "median": T.median(slen),
            "stdev": round(T.stdev(slen), 2),
            "cov": round(T.stdev(slen) / T.mean(slen), 3) if T.mean(slen) else 0.0,
            "min": min(slen) if slen else 0,
            "max": max(slen) if slen else 0,
            "range": (max(slen) - min(slen)) if slen else 0,
            "p10": round(T.pct(slen, 0.10), 1),
            "p90": round(T.pct(slen, 0.90), 1),
            "mid_band_share": round(len(mid_band) / len(slen), 3) if slen else 0.0,
            "similar_runs_ge3": runs,
            "longest_similar_run": longest_run,
        },
        "sentence_shape_mix": {k: round(v / len(shapes), 3) for k, v in Counter(shapes).items()} if shapes else {},
        "paragraph": {
            "words_mean": round(T.mean(para_words), 2),
            "words_stdev": round(T.stdev(para_words), 2),
            "sentences_mean": round(T.mean(para_sents), 2),
            "sentences_stdev": round(T.stdev(para_sents), 2),
            "single_sentence_share": round(
                sum(1 for x in para_sents if x == 1) / len(para_sents), 3
            )
            if para_sents
            else 0.0,
        },
        "openers": {
            "class_mix": {k: round(v / len(openers), 3) for k, v in Counter(openers).items()} if openers else {},
            "distinct_first_word_ratio": round(len(set(first_words)) / len(first_words), 3) if first_words else 0.0,
            "top_first_words": Counter(first_words).most_common(8),
            "repeated_first_word_max": Counter(first_words).most_common(1)[0][1] if first_words else 0,
        },
        "lexicon": {
            "ttr": round(ttr, 4),
            "mattr_100": round(mattr, 4),
            "hapax_share_content": round(hapax / len(content), 3) if content else 0.0,
            "stopword_share": round(sum(1 for w in wl if w in stop) / total_w, 3) if total_w else 0.0,
            "avg_word_len": round(T.mean(len(w) for w in wl), 2) if wl else 0.0,
            "long_word_share_9plus": round(sum(1 for w in wl if len(w) >= 9) / total_w, 3) if total_w else 0.0,
            "top_content_words": Counter(content).most_common(15),
        },
        "punctuation_per_1000w": punct_per_1000,
        "discourse": {
            "connectives_per_1000w": T.per_1000(sum(conn_hits.values()), total_w),
            "connective_inventory": dict(sorted(conn_hits.items(), key=lambda kv: -kv[1])[:15]),
            "distinct_connectives": len(conn_hits),
            "hedges_per_1000w": T.per_1000(sum(hedge_hits.values()), total_w),
            "boosters_per_1000w": T.per_1000(sum(boost_hits.values()), total_w),
            "hedge_booster_ratio": round(
                (sum(hedge_hits.values()) + 0.5) / (sum(boost_hits.values()) + 0.5), 2
            ),
            "first_person_per_1000w": T.per_1000(fp_hits, total_w),
            "nominalization_per_1000w": T.per_1000(rx_count(nomin), total_w),
            "passive_markers_per_1000w": T.per_1000(rx_count(passive), total_w),
        },
        "specificity": {
            "numbers_per_1000w": T.per_1000(rx_count(T.NUMBER), total_w),
            "citations": rx_count(T.CITE_BRACKET) + rx_count(T.CITE_AUTHOR_YEAR) + rx_count(T.CITE_TEX),
            "urls": rx_count(T.URL),
            "quoted_spans": rx_count(T.QUOTED),
        },
        "repetition": {
            "repeated_4grams": len(repeated4),
            "repeated_4grams_per_1000w": T.per_1000(len(repeated4), total_w),
            "repeated_4gram_examples": sorted(repeated4.items(), key=lambda kv: -kv[1])[:10],
            "repeated_content_trigrams": sorted(repeated3c.items(), key=lambda kv: -kv[1])[:10],
        },
    }
    if want_paragraphs:
        prof["paragraph_detail"] = [
            {
                "index": p.index,
                "kind": p.kind,
                "words": len(p.words),
                "sentences": len(p.sentences),
                "sentence_lengths": [len(T.WORD.findall(s)) for s in p.sentences],
                "opener": opener_class(p.sentences[0], lang) if p.sentences else None,
                "first_words": " ".join(T.WORD.findall(p.text)[:6]),
            }
            for p in paras
        ]
    return prof


def merge_profiles(profs: list[dict]) -> dict:
    """Weighted merge of several reference samples (weight = words)."""
    if len(profs) == 1:
        return profs[0]
    total = sum(p["size"]["words"] for p in profs) or 1

    def wavg(path: list[str]) -> float:
        acc = 0.0
        for p in profs:
            node = p
            for k in path:
                node = node.get(k, {}) if isinstance(node, dict) else {}
            if isinstance(node, (int, float)):
                acc += node * p["size"]["words"]
        return round(acc / total, 4)

    merged = json.loads(json.dumps(profs[0]))
    numeric_paths = [
        ["sentence_length", k]
        for k in ("mean", "median", "stdev", "cov", "range", "p10", "p90", "mid_band_share")
    ] + [
        ["paragraph", k] for k in ("words_mean", "words_stdev", "sentences_mean", "sentences_stdev", "single_sentence_share")
    ] + [
        ["lexicon", k] for k in ("ttr", "mattr_100", "hapax_share_content", "stopword_share", "avg_word_len", "long_word_share_9plus")
    ] + [
        ["discourse", k]
        for k in (
            "connectives_per_1000w","hedges_per_1000w","boosters_per_1000w","hedge_booster_ratio",
            "first_person_per_1000w","nominalization_per_1000w","passive_markers_per_1000w",
        )
    ] + [
        ["specificity", "numbers_per_1000w"],
        ["openers", "distinct_first_word_ratio"],
        ["repetition", "repeated_4grams_per_1000w"],
    ]
    for path in numeric_paths:
        node = merged
        for k in path[:-1]:
            node = node.setdefault(k, {})
        node[path[-1]] = wavg(path)
    for k in merged["punctuation_per_1000w"]:
        merged["punctuation_per_1000w"][k] = wavg(["punctuation_per_1000w", k])
    merged["size"] = {
        "words": total,
        "sentences": sum(p["size"]["sentences"] for p in profs),
        "paragraphs_prose": sum(p["size"]["paragraphs_prose"] for p in profs),
        "paragraphs_total": sum(p["size"]["paragraphs_total"] for p in profs),
        "samples": len(profs),
    }
    inv: Counter = Counter()
    for p in profs:
        inv.update(p["discourse"]["connective_inventory"])
    merged["discourse"]["connective_inventory"] = dict(inv.most_common(15))
    merged["discourse"]["distinct_connectives"] = len(inv)
    return merged


def human_report(p: dict) -> str:
    s, sl, lx, d = p["size"], p["sentence_length"], p["lexicon"], p["discourse"]
    lines = [
        f"lang={p['lang']}  words={s['words']}  sentences={s['sentences']}  paragraphs={s['paragraphs_prose']}",
        f"sentence len: mean={sl['mean']} median={sl['median']} sd={sl['stdev']} cov={sl['cov']} "
        f"range={sl['range']} p10-p90={sl['p10']}-{sl['p90']}",
        f"rhythm: mid_band(12-20w)={sl['mid_band_share']} similar_runs>=3={sl['similar_runs_ge3']} "
        f"longest_run={sl['longest_similar_run']}",
        f"paragraphs: words_mean={p['paragraph']['words_mean']} sd={p['paragraph']['words_stdev']} "
        f"sent_mean={p['paragraph']['sentences_mean']}",
        f"openers: distinct_first_word_ratio={p['openers']['distinct_first_word_ratio']} "
        f"mix={p['openers']['class_mix']}",
        f"lexicon: ttr={lx['ttr']} mattr100={lx['mattr_100']} hapax={lx['hapax_share_content']} "
        f"stopword={lx['stopword_share']} avg_wlen={lx['avg_word_len']}",
        f"discourse: connectives/1k={d['connectives_per_1000w']} distinct={d['distinct_connectives']} "
        f"hedges/1k={d['hedges_per_1000w']} boosters/1k={d['boosters_per_1000w']} h/b={d['hedge_booster_ratio']}",
        f"          nominalizations/1k={d['nominalization_per_1000w']} passive/1k={d['passive_markers_per_1000w']} "
        f"first_person/1k={d['first_person_per_1000w']}",
        f"punctuation/1k: {p['punctuation_per_1000w']}",
        f"specificity: numbers/1k={p['specificity']['numbers_per_1000w']} citations={p['specificity']['citations']}",
        f"repetition: repeated_4grams={p['repetition']['repeated_4grams']} "
        f"({p['repetition']['repeated_4grams_per_1000w']}/1k)",
    ]
    if p["repetition"]["repeated_4gram_examples"]:
        lines.append("  top repeated 4-grams: " + "; ".join(f"{k} x{v}" for k, v in p["repetition"]["repeated_4gram_examples"][:5]))
    if d["connective_inventory"]:
        lines.append("  connectives: " + ", ".join(f"{k} x{v}" for k, v in list(d["connective_inventory"].items())[:8]))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--paragraphs", action="store_true", help="include per-paragraph detail")
    ap.add_argument("--out", type=Path, help="write JSON profile to file")
    args = ap.parse_args()

    profs = []
    for path in args.paths:
        if not path.exists():
            print(f"FAIL: not found: {path}", file=sys.stderr)
            return 2
        profs.append(profile(T.read_text(path), args.paragraphs))
    merged = merge_profiles(profs)
    merged["sources"] = [str(p) for p in args.paths]
    if args.out:
        args.out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(merged, ensure_ascii=False, indent=2))
    else:
        print(human_report(merged))
        if args.out:
            print(f"\nprofile JSON -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
