"""Shared text utilities for Palimpsest scripts. Stdlib only, RU/EN aware."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

CYR = re.compile(r"[\u0400-\u04FF]")
WORD = re.compile(r"[^\W\d_]+(?:[-'\u2019][^\W\d_]+)*", re.UNICODE)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

CODE_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]+`")
LATEX = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$|\\\[.*?\\\]|\\\(.*?\\\)", re.DOTALL)
URL = re.compile(r"https?://\S+|www\.\S+")
CITE_TEX = re.compile(r"\\cite[a-zA-Z]*\{[^}]*\}")
CITE_BRACKET = re.compile(r"\[\d{1,3}(?:\s*[,\u2013-]\s*\d{1,3})*\]")
CITE_AUTHOR_YEAR = re.compile(
    r"\(([^()]{0,60}?(?:19|20)\d{2}[a-z]?(?:\s*[;,]\s*[^()]{0,60}?(?:19|20)\d{2}[a-z]?)*)\)"
)
QUOTED = re.compile(r"[\u00ab\u201c\u201e\"']{1}([^\u00bb\u201d\"'\n]{6,200})[\u00bb\u201d\"']{1}")
ANNOTATION = re.compile(r"\u27e6[^\u27e7]*\u27e7")
MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
MD_LIST = re.compile(r"^\s{0,6}(?:[-*+]\s+|\d+[.)]\s+)", re.MULTILINE)

# Abbreviations that must not end a sentence.
ABBR = {
    "т",
    "д",
    "п",
    "е",
    "г",
    "гг",
    "рис",
    "табл",
    "см",
    "стр",
    "им",
    "тыс",
    "млн",
    "млрд",
    "др",
    "проф",
    "акад",
    "ул",
    "обл",
    "вв",
    "no",
    "vs",
    "eg",
    "ie",
    "cf",
    "etc",
    "fig",
    "tab",
    "vol",
    "pp",
    "ed",
    "eds",
    "al",
    "dr",
    "prof",
    "mr",
    "mrs",
    "ms",
    "st",
    "approx",
}

RU_STOP = {
    "и","в","во","не","что","он","на","я","с","со","как","а","то","все","она","так","его","но","да","ты","к",
    "у","же","вы","за","бы","по","только","ее","мне","было","вот","от","меня","еще","нет","о","из","ему",
    "теперь","когда","даже","ну","вдруг","ли","если","уже","или","ни","быть","был","него","до","вас","нибудь",
    "опять","уж","вам","ведь","там","потом","себя","ничего","ей","может","они","тут","где","есть","надо","ней",
    "для","мы","тебя","их","чем","была","сам","чтоб","без","будто","чего","раз","тоже","себе","под","будет",
    "ж","тогда","кто","этот","того","потому","этого","какой","совсем","ним","здесь","этом","один","почти",
    "мой","тем","чтобы","нее","были","куда","зачем","всех","никогда","можно","при","наконец","два","об",
    "другой","хоть","после","над","больше","тот","через","эти","нас","про","всего","них","какая","много",
    "разве","три","эту","моя","впрочем","хорошо","свою","этой","перед","иногда","лучше","чуть","том","нельзя",
    "такой","им","более","всегда","конечно","всю","между","это","её","при","также","однако","этих",
}
EN_STOP = {
    "the","a","an","and","or","but","if","while","of","to","in","on","at","by","for","with","from","as","that",
    "this","these","those","it","its","is","are","was","were","be","been","being","have","has","had","do","does",
    "did","not","no","nor","so","than","then","there","their","them","they","he","she","we","you","i","his","her",
    "our","your","my","me","us","him","which","who","whom","whose","what","when","where","how","why","all","any",
    "both","each","few","more","most","other","some","such","only","own","same","too","very","can","will","just",
    "should","would","could","may","might","must","also","however","thus","because","about","into","through",
    "during","before","after","above","below","between","under","over","again","further","once","here","up","out",
    "off","down","against","without","within","upon","per","via",
}

RU_CONNECTIVES = [
    "таким образом","следовательно","поэтому","в результате","кроме того","более того","в частности",
    "например","то есть","однако","тем не менее","несмотря на","в связи с","вследствие","благодаря",
    "во-первых","во-вторых","в-третьих","наконец","в заключение","подводя итог","стоит отметить",
    "необходимо отметить","важно подчеркнуть","следует учитывать","с одной стороны","с другой стороны",
    "в то же время","между тем","итак","значит","при этом","также","кстати","впрочем","напротив","зато",
]
EN_CONNECTIVES = [
    "therefore","thus","hence","consequently","as a result","moreover","furthermore","in addition",
    "additionally","however","nevertheless","nonetheless","on the other hand","in contrast","for example",
    "for instance","in particular","specifically","that is","in other words","first","second","third",
    "finally","in conclusion","to sum up","it is worth noting","importantly","notably","overall","meanwhile",
    "besides","indeed","although","whereas","by contrast","in summary",
]

RU_HEDGES = [
    "возможно","вероятно","по-видимому","скорее всего","как правило","в некоторых случаях","отчасти",
    "по всей видимости","предположительно","может","могут","обычно","зачастую","нередко","судя по",
    "насколько","предварительно","условно","приблизительно","около","порядка","в целом",
]
EN_HEDGES = [
    "may","might","could","perhaps","possibly","probably","likely","suggests","appears","seems","tends to",
    "relatively","somewhat","arguably","in general","roughly","approximately","about","largely","partly",
]
RU_BOOSTERS = [
    "безусловно","несомненно","очевидно","явно","крайне","чрезвычайно","абсолютно","полностью","однозначно",
    "critически","ключевой","важнейший","принципиально","существенно","значительно","максимально",
]
EN_BOOSTERS = [
    "clearly","obviously","undoubtedly","certainly","definitely","crucial","critical","vital","essential",
    "significantly","substantially","extremely","highly","remarkably","profoundly",
]
RU_FIRST_PERSON = ["я","мы","мне","меня","мной","нас","нам","нами","наш","наша","наше","наши","моя","мой","моё","мои"]
EN_FIRST_PERSON = ["i","we","us","me","our","ours","my","mine"]

RU_NOMINALIZATION = re.compile(
    r"\b\w{3,}(?:ание|ение|ание|ость|ность|ация|изация|ирование|ение|ство|тие)\b", re.IGNORECASE
)
EN_NOMINALIZATION = re.compile(r"\b\w{4,}(?:tion|sion|ment|ness|ity|ance|ence|ization|isation)\b", re.IGNORECASE)
RU_PASSIVE = re.compile(
    r"\b(?:был[аио]?|будет|будут|быть|является|являются)\s+\w+(?:н|на|но|ны|т|та|то|ты)\b|\b\w+(?:ется|ются|ился|илась|ались)\b",
    re.IGNORECASE,
)
EN_PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being|gets|got)\s+\w+(?:ed|en)\b", re.IGNORECASE)

DASHES = {"em": "\u2014", "en": "\u2013", "hyphen": "-", "minus": "\u2212"}


def is_cyrillic(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    cyr = sum(1 for c in letters if CYR.match(c))
    return cyr / len(letters) > 0.35


def lang_of(text: str) -> str:
    return "ru" if is_cyrillic(text) else "en"


def strip_annotations(text: str) -> str:
    return ANNOTATION.sub("", text)


def mask_protected(text: str) -> str:
    """Replace code/latex/urls with placeholders of equal-ish length so stats ignore them."""
    out = text
    for rx in (CODE_FENCE, LATEX, INLINE_CODE, URL, CITE_TEX):
        out = rx.sub(lambda m: " " * min(len(m.group(0)), 3), out)
    return out


@dataclass
class Paragraph:
    index: int
    start: int
    end: int
    text: str
    kind: str = "prose"  # prose | heading | list | code | quote
    sentences: list[str] = field(default_factory=list)

    @property
    def words(self) -> list[str]:
        return WORD.findall(self.text)


def paragraphs(text: str, keep_annotations: bool = False) -> list[Paragraph]:
    src = text if keep_annotations else strip_annotations(text)
    out: list[Paragraph] = []
    pos = 0
    idx = 0
    for chunk in re.split(r"\n\s*\n", src):
        start = src.find(chunk, pos)
        if start < 0:
            start = pos
        end = start + len(chunk)
        pos = end
        body = chunk.strip()
        if not body:
            continue
        kind = "prose"
        if body.startswith("```") or body.startswith("~~~"):
            kind = "code"
        elif MD_HEADING.match(body):
            kind = "heading"
        elif MD_LIST.match(body):
            kind = "list"
        elif body.startswith(">"):
            kind = "quote"
        idx += 1
        p = Paragraph(index=idx, start=start, end=end, text=body, kind=kind)
        p.sentences = sentences(body) if kind in ("prose", "quote", "list") else []
        out.append(p)
    return out


def sentences(text: str) -> list[str]:
    src = mask_protected(text)
    src = MD_HEADING.sub("", src)
    src = re.sub(r"\s+", " ", src).strip()
    if not src:
        return []
    parts: list[str] = []
    buf = ""
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        buf += ch
        if ch in ".!?\u2026":
            # consume repeats like "?!" or "..."
            while i + 1 < n and src[i + 1] in ".!?\u2026":
                i += 1
                buf += src[i]
            nxt = src[i + 1] if i + 1 < n else ""
            nxt2 = src[i + 2] if i + 2 < n else ""
            if nxt == " " and (nxt2.isupper() or nxt2.isdigit() or nxt2 in "\u00ab\u201c-\u2014"):
                tail = WORD.findall(buf[-14:])
                last = tail[-1].lower() if tail else ""
                prev_char = buf[-2] if len(buf) > 1 else " "
                if last in ABBR or (len(last) == 1 and prev_char.isalpha() and last.isalpha()):
                    pass  # abbreviation or initial: keep going
                else:
                    parts.append(buf.strip())
                    buf = ""
                    i += 1  # skip the space
        i += 1
    if buf.strip():
        parts.append(buf.strip())
    return [p for p in parts if WORD.findall(p)]


def words(text: str) -> list[str]:
    return WORD.findall(mask_protected(text).lower())


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def median(xs) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    mid = len(xs) // 2
    return float(xs[mid]) if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def stdev(xs) -> float:
    xs = list(xs)
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def pct(xs, q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(xs[int(k)])
    return xs[lo] * (hi - k) + xs[hi] * (k - lo)


def ngrams(seq: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(seq[i : i + n]) for i in range(len(seq) - n + 1)]


def count_phrases(text_lower: str, phrases: list[str]) -> dict[str, int]:
    """Count phrases with word boundaries on both sides (RU/EN safe).

    Без правой границы «не» матчится внутри «неотъемлемая», а «я» — в любом
    слове на -я; такие подсчёты ломают весь профиль.
    """
    hits: dict[str, int] = {}
    for ph in phrases:
        left = r"(?<![^\W\d_])"
        right = r"(?![^\W\d_])" if ph[-1].isalpha() else ""
        c = len(re.findall(left + re.escape(ph) + right, text_lower))
        if c:
            hits[ph] = c
    return hits


def norm_key(s: str) -> str:
    return unicodedata.normalize("NFKD", s.strip().lower())


def per_1000(count: int, total_words: int) -> float:
    return round(count * 1000 / total_words, 2) if total_words else 0.0


def read_text(path) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8", errors="replace")


# Файлы, которые доказательством детектора быть не могут — даже если непустые.
_EVIDENCE_FORBIDDEN = {
    "state.json", "memory.md", "handoff.md", "segments.json", "terms.md",
    "goal.md", "ductus.md", "ductus.json", "brief-rules.md", "master-brief.md",
    "original.md", "working-copy.md", "claim-ledger.md", "report.md",
    "diagnosis.md", "rehearsal.md",
}
_EVIDENCE_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_EVIDENCE_TEXT = {".md", ".txt"}


def require_evidence_file(path: str | None, what: str = "--evidence") -> str | None:
    """След детектора: существующий непустой файл правильного рода.

    Содержимое скрина скрипт не читает и не должен — но и STATE.json / чужой md
    подсунуть нельзя. Допускаются:
      • изображения (.png/.jpg/.jpeg/.webp/.gif);
      • текстовые отчёты (.md/.txt) только из каталога reports/ или с именем
        detectors-ROUND*.md / detector-*.md.
    Пустой touch и несуществующий путь — отказ.
    """
    from pathlib import Path

    if not path or not str(path).strip():
        return (f"{what} пуст: нужен путь к скриншоту (.png/.jpg) или "
                f"reports/detectors-ROUND-N.md")
    p = Path(str(path).strip())
    if not p.is_file():
        return (f"{what}: файл не найден: {p}\n"
                f"Сначала сохрани скрин/отчёт, потом ссылайся на него. "
                f"Строка «reports/fake.md» без файла — не доказательство.")
    if p.stat().st_size == 0:
        return (f"{what}: файл пуст: {p}\n"
                f"`touch` недостаточно — нужен реальный след (скрин или текст отчёта).")

    name = p.name.lower()
    if name in _EVIDENCE_FORBIDDEN:
        return (f"{what}: «{p.name}» — рабочий артефакт задачи, не след детектора.\n"
                f"Нужен скриншот сервиса или reports/detectors-ROUND-N.md.")

    suffix = p.suffix.lower()
    parts_lower = [x.lower() for x in p.parts]
    in_reports = "reports" in parts_lower
    reportish = (
        name.startswith("detectors-round")
        or name.startswith("detector-")
        or name.startswith("detectors_")
    )

    if suffix in _EVIDENCE_IMAGES:
        return None
    if suffix in _EVIDENCE_TEXT and (in_reports or reportish):
        return None
    if suffix in _EVIDENCE_TEXT:
        return (f"{what}: текстовый след только из reports/ или с именем "
                f"detectors-ROUND-N.md (сейчас: {p}).\n"
                f"Подсунуть STATE.json / MEMORY.md / произвольный md нельзя.")
    return (f"{what}: недопустимый тип файла «{suffix or 'без расширения'}». "
            f"Допустимы скриншоты (.png/.jpg/.webp) или отчёт "
            f"reports/detectors-ROUND-N.md.")
