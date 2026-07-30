# Разметка v3

Разметка помогает мыслить, но не является обязательным способом для каждой
мелкой правки. Состояние и аттестации — источник гейтов; inline marks — временная
очередь внутри рабочей копии.

## Типы

```text
⟦F01|pattern|repeated claim-summary cadence|open⟧...⟦/F01⟧
⟦V01|voice|reference uses concrete qualification|open⟧...⟦/V01⟧
⟦Q01|fact|source needed for 2024 figure|open⟧...⟦/Q01⟧
⟦A01|anchor|keep exact equation|open⟧x = 1⟦/A01⟧
⟦P01|parked|needs user decision|parked⟧...⟦/P01⟧
```

IDs уникальны в документе. Открывающая и закрывающая марки должны быть
правильно вложены. Статус не дублируется противоречиво.

## Что размечать

- точные hotspots диагноза;
- факты, требующие F3;
- защищённые якоря;
- voice gaps, если есть Ductus;
- решения, ожидающие пользователя.

Не оборачивай весь абзац, если проблема в одной связке. Не создавай сотни
марок ради видимости процесса.

## Жизненный цикл

1. `open` — проблема существует;
2. `in-progress` — выполняется проверяемый move;
3. `fixed` — редакторское изменение сделано;
4. `verified` — активные проверки пройдены на текущем SHA;
5. `waived` — пользователь принял конкретное ограничение;
6. `rejected` — диагноз оказался неверным;
7. `parked` — решение отложено и отражено в state.

## Проверка

```bash
python3 scripts/annotations.py workspace/working.md --validate
python3 scripts/annotations.py workspace/working.md --open
python3 scripts/annotations.py workspace/working.md --strip \
  --out workspace/delivery.md
python3 scripts/annotations.py workspace/delivery.md --check-clean
```

Финальный working/delivery не должен содержать `⟦` или `⟧`. `state.py verify`
проверяет чистоту текущего working-файла.

## Evidence отдельно

Закрытая inline mark не закрывает гейт. Детектор, факт, overlap или semantic
review регистрируются соответствующим artifact/result в `STATE.json`.
