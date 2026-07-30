#!/usr/bin/env python3
"""Palimpsest v3.1 deterministic fidelity screen.

This is deliberately called a *screen*, not a semantic proof.  It catches
protected-fragment edits, number reassignment, polarity reversals, negation
changes, unit changes, modal/logic-relation shifts, likely actor-role swaps, and
loss of claim-bearing sentences.  A structured semantic reconciliation is still
required by state.py before closure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402
import _v3lib as V  # noqa: E402

SCHEMA = "palimpsest.fidelity.v3.1"
NUMBER = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)?(?:\s?%|\s?[A-Za-zА-Яа-яЁё]+)?")
PLAIN_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
SENTENCE = re.compile(r"[^.!?…\n]+(?:[.!?…]+|$)", re.MULTILINE)
REFERENCE_HEADING = re.compile(
    r"(?im)^[ \t]*(?:references|bibliography|список\s+литературы|"
    r"библиография|литература)[ \t]*\r?$"
)

PROTECTED = [
    ("code_fence", T.CODE_FENCE),
    ("latex", T.LATEX),
    ("inline_code", T.INLINE_CODE),
    ("url", T.URL),
    ("tex_citation", T.CITE_TEX),
]
CITATIONS = [
    ("bracket_citation", T.CITE_BRACKET),
    ("author_year_citation", T.CITE_AUTHOR_YEAR),
]

NEGATION = {
    "не", "ни", "нет", "нельзя", "никогда", "без", "not", "no", "never", "none",
    "neither", "without", "cannot", "can't", "won't", "didn't", "doesn't", "isn't",
}
AXES = {
    "direction": {
        "up": ("рост", "вырос", "выросл", "повыс", "увелич", "подня", "grow", "grew", "increase", "rise", "rose", "higher"),
        "down": ("сниж", "упал", "паден", "уменьш", "сократ", "declin", "decreas", "fell", "drop", "lower"),
    },
    "validation": {
        "support": ("подтверж", "доказ", "соглас", "support", "confirm", "validate", "prove", "corrobor"),
        "reject": ("опровер", "отверг", "противореч", "refut", "reject", "contradict", "disprov"),
    },
    "quality": {
        "better": ("улучш", "эффектив", "успеш", "improv", "better", "benefit", "effective"),
        "worse": ("ухудш", "вред", "провал", "wors", "harm", "deterior", "fail"),
    },
    "permission": {
        "allow": ("разреш", "допуст", "можно", "allow", "permit", "may"),
        "forbid": ("запрещ", "нельзя", "недопуст", "forbid", "prohibit", "ban"),
    },
    "causality": {
        "cause": ("вызыва", "привод", "обуслов", "cause", "lead", "result"),
        "prevent": ("предотвращ", "меша", "препятств", "prevent", "avoid", "inhibit"),
    },
}

MODAL_PATTERNS = {
    "possibility": (
        r"\bmay\b", r"\bmight\b", r"\bcould\b", r"\bpossibly\b",
        r"\bмож(?:ет|но|гут)\b", r"\bвозможн\w*\b", r"\bвероятн\w*\b",
    ),
    "recommendation": (
        r"\bshould\b", r"\bought to\b", r"\brecommend(?:s|ed|ing)?\b",
        r"\bследует\b", r"\bстоит\b", r"\bрекоменду\w*\b",
    ),
    "obligation": (
        r"\bmust\b", r"\bshall\b", r"\brequired?\b", r"\bneed(?:s|ed)? to\b",
        r"\bдолж(?:ен|на|но|ны)\b", r"\bобязан\w*\b", r"\bнеобходим\w*\b",
    ),
    "certainty": (
        r"\bwill\b", r"\bcertainly\b", r"\bdefinitely\b",
        r"\bобязательно\b", r"\bнесомненно\b", r"\bточно\b",
    ),
}

RELATION_PATTERNS = {
    "cause": (
        r"\bbecause\b", r"\bdue to\b", r"\bas a result of\b", r"\btherefore\b",
        r"\bпотому что\b", r"\bиз-за\b", r"\bвследствие\b", r"\bпоэтому\b",
    ),
    "concession": (
        r"\bdespite\b", r"\bin spite of\b", r"\balthough\b", r"\bthough\b",
        r"\bнесмотря на\b", r"\bхотя\b", r"\bвопреки\b",
    ),
    "condition": (
        r"\bif\b", r"\bunless\b", r"\bprovided that\b",
        r"\bесли\b", r"\bесли не\b", r"\bпри условии\b",
    ),
}

CHRONOLOGY_PATTERNS = {
    "before": (r"\bbefore\b", r"\bprior to\b", r"\bдо того как\b", r"\bперед\b"),
    "after": (r"\bafter\b", r"\bfollowing\b", r"\bпосле\b", r"\bзатем\b"),
}

UNIT_ALIASES = {
    "kgs": "kg", "kilogram": "kg", "kilograms": "kg", "килограмм": "kg",
    "килограмма": "kg", "килограммов": "kg", "кг": "kg",
    "lbs": "lb", "pound": "lb", "pounds": "lb", "фунт": "lb",
    "фунта": "lb", "фунтов": "lb",
    "meters": "m", "meter": "m", "metres": "m", "metre": "m", "метр": "m",
    "метра": "m", "метров": "m",
    "kilometers": "km", "kilometres": "km", "kilometer": "km", "kilometre": "km",
    "километр": "km", "километра": "km", "километров": "km", "км": "km",
    "seconds": "s", "second": "s", "секунд": "s", "секунда": "s", "секунды": "s",
    "minutes": "min", "minute": "min", "минут": "min", "минута": "min", "минуты": "min",
    "hours": "h", "hour": "h", "час": "h", "часа": "h", "часов": "h",
    "percent": "%", "процентов": "%", "процента": "%", "процент": "%",
}


def normalize_fragment(value: str) -> str:
    return value.replace("\r\n", "\n").strip()


def split_reference_list(text: str) -> tuple[str, str]:
    match = REFERENCE_HEADING.search(text)
    if not match:
        return text, ""
    return text[:match.start()], text[match.start():]


def collect(patterns: list[tuple[str, re.Pattern]], text: str) -> dict[str, list[str]]:
    return {
        name: [normalize_fragment(m.group(0)) for m in rx.finditer(text)]
        for name, rx in patterns
    }


def protected_spans(text: str) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int, int]] = []
    # Longer/high-level constructs win, so inline patterns inside a code fence do
    # not create duplicate checks.
    for priority, (_, rx) in enumerate(PROTECTED):
        for m in rx.finditer(text):
            candidates.append((m.start(), m.end(), priority))
    candidates.sort(key=lambda x: (x[0], x[2], -(x[1] - x[0])))
    kept: list[tuple[int, int]] = []
    for start, end, _ in candidates:
        if any(start < other_end and end > other_start for other_start, other_end in kept):
            continue
        kept.append((start, end))
    return kept


def mask_equal(text: str) -> str:
    chars = list(text)
    for start, end in protected_spans(text):
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def mask_citations_equal(text: str) -> str:
    """Mask citation metadata for numeric-context comparison.

    Author-year and bracket citations are already compared exactly. Treating
    their repeated years as claim numbers caused ordinal misalignment after a
    sentence split or merge and produced dozens of false
    NUMBER_CONTEXT_CHANGED findings in real literature reviews.
    """
    chars = list(mask_equal(text))
    for name, pattern in CITATIONS:
        if name != "author_year_citation":
            continue
        for match in pattern.finditer(text):
            for index in range(match.start(), match.end()):
                if chars[index] != "\n":
                    chars[index] = " "
    return "".join(chars)


def content_tokens(text: str) -> list[str]:
    stop = T.RU_STOP | T.EN_STOP | NEGATION
    return [
        w.lower().replace("ё", "е")
        for w in T.WORD.findall(text)
        if w.lower().replace("ё", "е") not in stop and len(w) > 2
    ]


def jaccard(a: list[str], b: list[str]) -> float:
    aa, bb = set(a), set(b)
    if not aa and not bb:
        return 1.0
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def sentence_records(text: str) -> list[dict]:
    masked = mask_equal(text)
    out: list[dict] = []
    for index, m in enumerate(SENTENCE.finditer(masked), start=1):
        raw = text[m.start():m.end()].strip()
        if not raw:
            continue
        words = [w.lower().replace("ё", "е") for w in T.WORD.findall(raw)]
        axes: dict[str, str] = {}
        joined = " ".join(words)
        for axis, sides in AXES.items():
            hits: list[str] = []
            for side, stems in sides.items():
                if any(any(token.startswith(stem) for stem in stems) for token in words):
                    hits.append(side)
            if len(set(hits)) == 1:
                axes[axis] = hits[0]
            elif len(set(hits)) > 1:
                axes[axis] = "mixed"
        lower = raw.lower().replace("ё", "е")
        modal_hits = [
            label for label, patterns in MODAL_PATTERNS.items()
            if any(re.search(pattern, lower) for pattern in patterns)
        ]
        relation_hits = [
            label for label, patterns in RELATION_PATTERNS.items()
            if any(re.search(pattern, lower) for pattern in patterns)
        ]
        chronology_hits = [
            label for label, patterns in CHRONOLOGY_PATTERNS.items()
            if any(re.search(pattern, lower) for pattern in patterns)
        ]
        out.append(
            {
                "index": index,
                "start": m.start(),
                "end": m.end(),
                "text": raw,
                "tokens": content_tokens(joined),
                "negations": sum(1 for w in words if w in NEGATION),
                "axes": axes,
                "modal": modal_hits[0] if len(modal_hits) == 1 else ("mixed" if modal_hits else ""),
                "relation": (
                    relation_hits[0] if len(relation_hits) == 1
                    else ("mixed" if relation_hits else "")
                ),
                "chronology": (
                    chronology_hits[0] if len(chronology_hits) == 1
                    else ("mixed" if chronology_hits else "")
                ),
            }
        )
    return out


def number_records(text: str, sentences: list[dict]) -> list[dict]:
    masked = mask_citations_equal(text)
    out: list[dict] = []
    for index, m in enumerate(NUMBER.finditer(masked), start=1):
        raw = m.group(0).strip()
        numeric = PLAIN_NUMBER.search(raw)
        if not numeric:
            continue
        value = numeric.group(0).replace(",", ".")
        raw_unit = raw[numeric.end():].strip().lower().rstrip(".,;:")
        unit = UNIT_ALIASES.get(
            raw_unit,
            raw_unit if raw_unit in set(UNIT_ALIASES.values()) | {"%"} else "",
        )
        sent = next((s for s in sentences if s["start"] <= m.start() < s["end"]), None)
        out.append(
            {
                "index": index,
                "raw": raw,
                "value": value,
                "unit": unit,
                "sentence": sent["index"] if sent else None,
                "tokens": sent["tokens"] if sent else [],
                "negations": sent["negations"] if sent else 0,
                "axes": sent["axes"] if sent else {},
            }
        )
    return out


def compare_exact(
    original: dict[str, list[str]],
    edited: dict[str, list[str]],
    *,
    severity: str,
) -> list[dict]:
    findings: list[dict] = []
    for kind in original:
        before, after = Counter(original[kind]), Counter(edited[kind])
        if before == after:
            continue
        findings.append(
            {
                "code": f"{kind.upper()}_CHANGED",
                "severity": severity,
                "message": f"{kind}: protected fragments differ",
                "removed": list((before - after).elements())[:8],
                "added": list((after - before).elements())[:8],
            }
        )
    return findings


def compare_numbers(before: list[dict], after: list[dict]) -> list[dict]:
    findings: list[dict] = []
    before_values = [x["value"] for x in before]
    after_values = [x["value"] for x in after]
    if Counter(before_values) != Counter(after_values):
        findings.append(
            {
                "code": "NUMBER_SET_CHANGED",
                "severity": "error",
                "message": "Numeric anchors were added, removed, or changed",
                "removed": list((Counter(before_values) - Counter(after_values)).elements()),
                "added": list((Counter(after_values) - Counter(before_values)).elements()),
            }
        )
    elif before_values != after_values:
        findings.append(
            {
                "code": "NUMBER_ORDER_CHANGED",
                "severity": "error",
                "message": "Numeric anchors occur in a different order; values may have been reassigned",
                "before": before_values,
                "after": after_values,
            }
        )

    if len(before) == len(after):
        for ordinal, (left, right) in enumerate(zip(before, after), start=1):
            if left["value"] == right["value"] and left.get("unit", "") != right.get("unit", ""):
                findings.append(
                    {
                        "code": "UNIT_CHANGED",
                        "severity": "error",
                        "message": (
                            f"Numeric anchor {left['value']} changed unit: "
                            f"{left.get('unit') or 'none'} → {right.get('unit') or 'none'}"
                        ),
                        "occurrence": ordinal,
                        "before_sentence": left["sentence"],
                        "after_sentence": right["sentence"],
                    }
                )

    grouped_before: dict[str, list[dict]] = defaultdict(list)
    grouped_after: dict[str, list[dict]] = defaultdict(list)
    for item in before:
        grouped_before[item["value"]].append(item)
    for item in after:
        grouped_after[item["value"]].append(item)
    for value in sorted(set(grouped_before) & set(grouped_after)):
        for ordinal, (left, right) in enumerate(
            zip(grouped_before[value], grouped_after[value]), start=1
        ):
            similarity = jaccard(left["tokens"], right["tokens"])
            polarity_changed = (
                left["negations"] != right["negations"]
                or any(
                    left["axes"].get(axis) != right["axes"].get(axis)
                    for axis in set(left["axes"]) & set(right["axes"])
                    if left["axes"].get(axis) != "mixed" and right["axes"].get(axis) != "mixed"
                )
            )
            if similarity < 0.28 or polarity_changed:
                findings.append(
                    {
                        "code": "NUMBER_CONTEXT_CHANGED",
                        "severity": "error",
                        "message": f"Numeric anchor {value} (occurrence {ordinal}) changed claim context",
                        "similarity": round(similarity, 3),
                        "before_sentence": left["sentence"],
                        "after_sentence": right["sentence"],
                        "before_axes": left["axes"],
                        "after_axes": right["axes"],
                    }
                )
    return findings


def role_swap(left: dict, right: dict) -> tuple[str, str, str] | None:
    """Find a compact A-pivot-B → B-pivot-A inversion in matched claims."""
    before = left["tokens"]
    after = right["tokens"]
    if len(before) < 3 or Counter(before) != Counter(after):
        return None
    for index in range(1, len(before) - 1):
        actor_a, pivot, actor_b = before[index - 1:index + 2]
        if actor_a == actor_b:
            continue
        for other in range(1, len(after) - 1):
            if after[other - 1:other + 2] == [actor_b, pivot, actor_a]:
                return actor_a, pivot, actor_b
    return None


def compare_claim_polarity(before: list[dict], after: list[dict]) -> list[dict]:
    findings: list[dict] = []
    used: set[int] = set()
    for left in before:
        candidates = [
            (jaccard(left["tokens"], right["tokens"]), right)
            for right in after
            if right["index"] not in used
        ]
        if not candidates:
            continue
        similarity, right = max(candidates, key=lambda x: x[0])
        if similarity < 0.30:
            continue
        used.add(right["index"])
        if left["negations"] != right["negations"] and similarity >= 0.42:
            findings.append(
                {
                    "code": "NEGATION_CHANGED",
                    "severity": "error",
                    "message": "A matched claim changed its negation",
                    "before_sentence": left["index"],
                    "after_sentence": right["index"],
                    "similarity": round(similarity, 3),
                }
            )
        for axis in set(left["axes"]) & set(right["axes"]):
            old, new = left["axes"][axis], right["axes"][axis]
            if old != new and old != "mixed" and new != "mixed":
                findings.append(
                    {
                        "code": "POLARITY_CHANGED",
                        "severity": "error",
                        "message": f"A matched claim reversed the '{axis}' axis: {old} → {new}",
                        "before_sentence": left["index"],
                        "after_sentence": right["index"],
                        "similarity": round(similarity, 3),
                    }
                )
        for field, code, label in (
            ("modal", "MODALITY_CHANGED", "modality"),
            ("relation", "LOGIC_RELATION_CHANGED", "logic relation"),
            ("chronology", "CHRONOLOGY_CHANGED", "chronology"),
        ):
            old, new = left.get(field, ""), right.get(field, "")
            if old and new and old != new and old != "mixed" and new != "mixed":
                findings.append(
                    {
                        "code": code,
                        "severity": "error",
                        "message": f"A matched claim changed {label}: {old} → {new}",
                        "before_sentence": left["index"],
                        "after_sentence": right["index"],
                        "similarity": round(similarity, 3),
                    }
                )
        inversion = role_swap(left, right)
        if inversion:
            actor_a, pivot, actor_b = inversion
            findings.append(
                {
                    "code": "POSSIBLE_ROLE_SWAP",
                    "severity": "error",
                    "message": (
                        "A matched claim may have swapped actor/object roles: "
                        f"{actor_a} {pivot} {actor_b} → {actor_b} {pivot} {actor_a}"
                    ),
                    "before_sentence": left["index"],
                    "after_sentence": right["index"],
                    "similarity": round(similarity, 3),
                }
            )
    return findings


def claim_bearing(sentence: dict) -> bool:
    return bool(
        sentence["negations"]
        or sentence["axes"]
        or sentence.get("modal")
        or sentence.get("relation")
        or sentence.get("chronology")
        or len(sentence["tokens"]) >= 7
    )


def compare_claim_coverage(before: list[dict], after: list[dict]) -> list[dict]:
    """Flag original/edited claim-bearing sentences with no plausible counterpart."""
    findings: list[dict] = []
    for direction, source, candidates in (
        ("dropped", before, after),
        ("added", after, before),
    ):
        for item in source:
            best = max((jaccard(item["tokens"], other["tokens"]) for other in candidates), default=0.0)
            same_position = next(
                (other for other in candidates if other["index"] == item["index"]),
                None,
            )
            positional_signature_match = bool(
                len(source) == len(candidates)
                and same_position
                and (
                    (item["negations"] and same_position["negations"])
                    or (
                        item.get("modal")
                        and item.get("modal") == same_position.get("modal")
                    )
                    or (
                        item.get("relation")
                        and item.get("relation") == same_position.get("relation")
                    )
                    or bool(set(item["axes"].items()) & set(same_position["axes"].items()))
                )
            )
            if best >= 0.22 or positional_signature_match or not claim_bearing(item):
                continue
            code = "CLAIM_DROPPED" if direction == "dropped" else "CLAIM_ADDED"
            findings.append(
                {
                    "code": code,
                    "severity": "error",
                    "message": (
                        "A claim-bearing original sentence has no plausible edited counterpart"
                        if direction == "dropped"
                        else "An edited claim-bearing sentence has no plausible original counterpart"
                    ),
                    f"{direction}_sentence": item["index"],
                    "best_similarity": round(best, 3),
                    "excerpt": item["text"][:180],
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True)
    parser.add_argument("--edited", "--current", dest="edited", required=True)
    parser.add_argument("--strict-citations", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    original_path = V.resolve_existing(args.original)
    edited_path = V.resolve_existing(args.edited)
    original_text = V.read_text(original_path)
    edited_text = V.read_text(edited_path)

    original_body, original_references = split_reference_list(original_text)
    edited_body, edited_references = split_reference_list(edited_text)
    original_protected = collect(PROTECTED, original_text)
    edited_protected = collect(PROTECTED, edited_text)
    original_protected["reference_list"] = (
        [normalize_fragment(original_references)] if original_references else []
    )
    edited_protected["reference_list"] = (
        [normalize_fragment(edited_references)] if edited_references else []
    )
    original_citations = collect(CITATIONS, original_text)
    edited_citations = collect(CITATIONS, edited_text)
    original_sentences = sentence_records(original_body)
    edited_sentences = sentence_records(edited_body)
    original_numbers = number_records(original_body, original_sentences)
    edited_numbers = number_records(edited_body, edited_sentences)

    findings = compare_exact(original_protected, edited_protected, severity="error")
    citation_severity = "error" if args.strict_citations else "warning"
    findings.extend(compare_exact(original_citations, edited_citations, severity=citation_severity))
    findings.extend(compare_numbers(original_numbers, edited_numbers))
    findings.extend(compare_claim_polarity(original_sentences, edited_sentences))
    findings.extend(compare_claim_coverage(original_sentences, edited_sentences))

    # Stable de-duplication: the same reversal can be discovered through a number
    # and through sentence alignment, but both mechanisms remain visible when
    # their location differs.
    unique: list[dict] = []
    seen: set[str] = set()
    for finding in findings:
        key = json.dumps(finding, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(finding)

    errors = [x for x in unique if x["severity"] == "error"]
    warnings = [x for x in unique if x["severity"] == "warning"]
    result = {
        "schema": SCHEMA,
        "ok": not errors,
        "scope": {
            "original": str(original_path),
            "edited": str(edited_path),
            "original_sha256": V.sha256_file(original_path),
            "edited_sha256": V.sha256_file(edited_path),
        },
        "counts": {
            "errors": len(errors),
            "warnings": len(warnings),
            "original_sentences": len(original_sentences),
            "edited_sentences": len(edited_sentences),
            "original_numbers": len(original_numbers),
            "edited_numbers": len(edited_numbers),
        },
        "findings": unique,
        "limits": (
            "Deterministic screening cannot prove semantic equivalence or reliably "
            "parse every actor and relation. A source-unit semantic reconciliation "
            "is required; possible-role findings need human inspection."
        ),
    }
    if args.out:
        V.atomic_write_json(args.out, result)
    if args.json or not args.out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{'PASS' if result['ok'] else 'FAIL'}: {len(errors)} errors, {len(warnings)} warnings")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
