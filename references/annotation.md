# Разметка detector/editor loop v3.5

Inline marks — рабочая очередь редактора. `detector_round` — доказательство
полноты текущей service×target проверки. Нужны оба слоя.

## Типы

```text
⟦D01|detector|ZeroGPT highlight: repeated summary cadence|open⟧...⟦/D01⟧
⟦M01|manual|Copyleaks failed without spans: uniform syntax|open⟧...⟦/M01⟧
⟦V01|voice|reference qualifies claims more locally|open⟧...⟦/V01⟧
⟦Q01|fact|primary source needed for 2024 figure|open⟧...⟦/Q01⟧
⟦A01|anchor|preserve exact equation|open⟧x = 1⟦/A01⟧
⟦P01|parked|requires actual user decision|parked⟧...⟦/P01⟧
```

## Правила полноты

- Сначала проверить все обязательные сервисы, потом размечать.
- Перенести каждую видимую подсветку в `highlight_map` и working marks.
- Если score `>=20`, а UI не показывает spans, поставить минимум одну ручную
  diagnostic mark с конкретным механизмом.
- Не оборачивать весь документ, если проблема локальна.
- Не создавать фиктивные marks ради прохождения validator.
- Сложную зону можно `parked`, но открытый detector blocker не закрывается.

## Цикл

1. `open` — зона найдена текущим round;
2. `in-progress` — выбран и записан edit mechanism;
3. `fixed` — минимальная правка сделана;
4. после правки прогнать все mandatory detectors;
5. `verified` — новый полный round подтверждает результат;
6. `false-positive/rejected` — только с конкретным объяснением;
7. удалить marks из delivery.

Нельзя считать старую mark проверенной новым текстом без нового
service×target round.

## Проверка

```bash
python3 scripts/annotations.py workspace/working-annotated.md --validate
python3 scripts/annotations.py workspace/working-annotated.md --open
python3 scripts/annotations.py workspace/working-annotated.md --strip \
  --out workspace/working.md
python3 scripts/annotations.py workspace/working.md --check-clean
```

Финальный `working.md` не содержит `⟦`/`⟧`. История проблем остаётся в
`detector_rounds`, moves и REPORT.
