#!/usr/bin/env python3
"""Conservative English-level drift screen for style preservation.

This is a readability/complexity screen, not a certified CEFR assessment.
It estimates a broad band and, in compare mode, blocks changes outside a
tight source-relative feature envelope. A structured style review remains responsible for judging
learner voice, idiom, and context.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textlib as T  # noqa: E402
import _v3lib as V  # noqa: E402

SCHEMA = "palimpsest.english-level.v1"
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]
VOWELS = "aeiouy"
SUBORDINATORS = {
    "although", "because", "before", "despite", "even", "if", "once",
    "provided", "since", "though", "unless", "until", "whereas", "while",
    "whoever", "whom", "whose", "which", "that",
}


def syllables(word: str) -> int:
    token = re.sub(r"[^a-z]", "", word.casefold())
    if not token:
        return 0
    groups = len(re.findall(r"[aeiouy]+", token))
    if token.endswith("e") and groups > 1 and not token.endswith(("le", "ye")):
        groups -= 1
    return max(groups, 1)


def band(reading_grade: float) -> str:
    if reading_grade <= 4:
        return "A1"
    if reading_grade <= 6:
        return "A2"
    if reading_grade <= 8:
        return "B1"
    if reading_grade <= 10.5:
        return "B2"
    if reading_grade <= 13:
        return "C1"
    return "C2"


def profile_text(text: str) -> dict:
    words = [word.casefold() for word in T.words(text)]
    sentences = T.sentences(text)
    word_count = len(words)
    sentence_count = max(len(sentences), 1)
    syllable_count = sum(syllables(word) for word in words)
    words_per_sentence = word_count / sentence_count if word_count else 0.0
    syllables_per_word = syllable_count / word_count if word_count else 0.0
    grade = (
        0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59
        if word_count
        else 0.0
    )
    long_share = (
        sum(len(re.sub(r"[^a-z]", "", word)) >= 8 for word in words) / word_count
        if word_count
        else 0.0
    )
    subordinate_rate = (
        sum(word in SUBORDINATORS for word in words) / sentence_count
        if sentences
        else 0.0
    )
    # Keep the estimate stable on short texts while retaining a continuous
    # comparison signal for upward/downward editing drift.
    complexity = max(
        1.0,
        min(
            6.0,
            1.0
            + max(grade - 3.0, 0.0) / 2.2
            + min(long_share, 0.30) * 2.0
            + min(subordinate_rate, 1.5) * 0.12,
        ),
    )
    estimated = band(grade)
    return {
        "estimated_cefr": estimated,
        "complexity_index": round(complexity, 3),
        "reading_grade": round(grade, 3),
        "words": word_count,
        "sentences": len(sentences),
        "words_per_sentence": round(words_per_sentence, 3),
        "syllables_per_word": round(syllables_per_word, 3),
        "long_word_share": round(long_share, 4),
        "subordinate_markers_per_sentence": round(subordinate_rate, 3),
    }


def level_index(level: str) -> int:
    return LEVELS.index(level)


def compare(
    original: dict,
    edited: dict,
    target: str,
    target_mode: str = "inferred",
) -> dict:
    target_normalized = target if target == "native" else target.upper()
    if target_normalized not in LEVELS:
        raise ValueError(f"unknown target level: {target}")
    if target_mode not in {"inferred", "explicit"}:
        raise ValueError(f"unknown target mode: {target_mode}")
    source_shift = edited["complexity_index"] - original["complexity_index"]
    band_shift = level_index(edited["estimated_cefr"]) - level_index(
        original["estimated_cefr"]
    )
    target_gap = level_index(edited["estimated_cefr"]) - level_index(target_normalized)
    source_target_gap = (
        level_index(original["estimated_cefr"]) - level_index(target_normalized)
    )
    findings = []
    feature_deltas = {
        "complexity_index": round(source_shift, 3),
        "reading_grade": round(edited["reading_grade"] - original["reading_grade"], 3),
        "words_per_sentence": round(
            edited["words_per_sentence"] - original["words_per_sentence"], 3
        ),
        "syllables_per_word": round(
            edited["syllables_per_word"] - original["syllables_per_word"], 3
        ),
        "long_word_share": round(
            edited["long_word_share"] - original["long_word_share"], 4
        ),
        "subordinate_markers_per_sentence": round(
            edited["subordinate_markers_per_sentence"]
            - original["subordinate_markers_per_sentence"],
            3,
        ),
    }
    words_per_sentence_limit = max(
        2.5,
        abs(original["words_per_sentence"]) * 0.18,
    )
    thresholds = {
        "complexity_index": 0.35,
        "reading_grade": 1.25,
        "words_per_sentence": round(words_per_sentence_limit, 3),
        "syllables_per_word": 0.08,
        "long_word_share": 0.035,
        "subordinate_markers_per_sentence": 0.35,
        "estimated_band_shift": 0,
    }
    drift_signals = [
        name
        for name, delta in feature_deltas.items()
        if abs(delta) > thresholds[name]
    ]
    if band_shift != 0:
        drift_signals.append("estimated_band_shift")

    # ``infer_from_source`` means the source itself is authoritative, so even a
    # one-band movement remains a blocker.  With an explicit user level, the
    # selected level is authoritative and the source estimate is only a noisy
    # diagnostic.  This prevents a jargon-heavy B2/C1 draft from trapping the
    # editor at an accidental C2 readability estimate.
    if target_mode == "inferred":
        if drift_signals:
            direction = "raised" if source_shift > 0 else "lowered"
            findings.append(
                {
                    "code": "ENGLISH_LEVEL_DRIFT",
                    "message": (
                        f"estimated English complexity was {direction}: "
                        f"{original['estimated_cefr']} -> {edited['estimated_cefr']} "
                        f"(out-of-envelope signals: {', '.join(drift_signals)})"
                    ),
                }
            )
        if abs(target_gap) > 1:
            findings.append(
                {
                    "code": "ENGLISH_TARGET_MISMATCH",
                    "message": (
                        f"edited estimate {edited['estimated_cefr']} is not close to "
                        f"the source-inferred target {target_normalized}"
                    ),
                }
            )
    else:
        accepted_bands = (
            {"C2", "native"} if target_normalized == "native" else {target_normalized}
        )
        edited_on_target = edited["estimated_cefr"] in accepted_bands
        source_on_target = original["estimated_cefr"] in accepted_bands
        if not edited_on_target:
            findings.append(
                {
                    "code": "ENGLISH_TARGET_MISMATCH",
                    "message": (
                        f"edited estimate {edited['estimated_cefr']} does not match "
                        f"the explicit user target {target_normalized}"
                    ),
                }
            )
        if source_on_target and drift_signals:
            direction = "raised" if source_shift > 0 else "lowered"
            findings.append(
                {
                    "code": "ENGLISH_LEVEL_DRIFT",
                    "message": (
                        f"estimated English complexity was {direction} away from "
                        f"an already on-target source: "
                        f"{original['estimated_cefr']} -> {edited['estimated_cefr']} "
                        f"(out-of-envelope signals: {', '.join(drift_signals)})"
                    ),
                }
            )
        elif (
            not source_on_target
            and not edited_on_target
            and abs(target_gap) >= abs(source_target_gap)
        ):
            findings.append(
                {
                    "code": "ENGLISH_LEVEL_DRIFT",
                    "message": (
                        f"the edit did not move the approximate profile toward the "
                        f"explicit target {target_normalized}: "
                        f"{original['estimated_cefr']} -> {edited['estimated_cefr']}"
                    ),
                }
            )
    return {
        "schema": SCHEMA,
        "ok": not findings,
        "target_cefr": target_normalized,
        "target_mode": target_mode,
        "source": original,
        "edited": edited,
        "complexity_delta": round(source_shift, 3),
        "band_shift": band_shift,
        "feature_deltas": feature_deltas,
        "thresholds": thresholds,
        "drift_signals": drift_signals,
        "findings": findings,
        "limits": [
            "CEFR is only approximated from readability and lexical/syntactic signals.",
            (
                "In inferred mode, a pass means no measured source-relative drift "
                "exceeded the configured envelope. In explicit mode, the selected "
                "user level is authoritative and the source estimate is diagnostic."
            ),
            "A passing readability screen does not prove exact CEFR equivalence.",
            "Do not introduce learner errors; preserve complexity and voice while correcting accidental mistakes.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text")
    parser.add_argument("--original")
    parser.add_argument("--edited")
    parser.add_argument("--target", choices=LEVELS + [x.lower() for x in LEVELS])
    parser.add_argument(
        "--target-mode",
        choices=["inferred", "explicit"],
        default="inferred",
        help="whether the target came from the source estimate or an explicit user choice",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.text:
            if args.original or args.edited or args.target:
                raise ValueError("--text cannot be combined with compare-mode arguments")
            result = {"schema": SCHEMA, **profile_text(V.read_text(args.text))}
            rc = 0
        else:
            if not (args.original and args.edited and args.target):
                raise ValueError(
                    "compare mode requires --original, --edited, and --target"
                )
            result = compare(
                profile_text(V.read_text(args.original)),
                profile_text(V.read_text(args.edited)),
                args.target,
                args.target_mode,
            )
            rc = 0 if result["ok"] else 1
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            result.get(
                "estimated_cefr",
                f"{result['source']['estimated_cefr']} -> "
                f"{result['edited']['estimated_cefr']} "
                f"(target {result['target_cefr']})",
            )
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
