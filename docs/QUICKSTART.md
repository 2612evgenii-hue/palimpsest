# Быстрый старт Palimpsest v3.5

## 1. Создать immutable original и working copy

```bash
mkdir -p workspace/evidence
cp essay.md workspace/original.md
cp essay.md workspace/working.md
```

## 2. Инициализировать проект

```bash
python3 scripts/state.py --state workspace/STATE.json init \
  --original workspace/original.md \
  --working workspace/working.md \
  --flags F1,F2
```

F1 включает `score_mandatory`, strict `<20%`, target `<15%`, полное detector
coverage и расширенный default edit budget 0.30/0.60.

## 3. Записать intake

В диалоге это три вопроса; F1 detector scope — follow-up второго.

```bash
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q1 --style-mode source_as_reference --english-level B2 \
  --answer "No external reference; preserve source handwriting and B2." \
  --source explicit

python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q2 --functions F1,F2 \
  --answer "Enable F1 and F2." --source explicit

python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q3 \
  --services zerogpt,gptzero,scribbr,quillbot,gptinf,copyleaks \
  --answer "Keep the original six-service set mandatory." --source explicit

python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q4 \
  --answer "Technical report; preserve headings, citations, claims, and B2." \
  --source explicit
```

Проверь `goal`:

```bash
python3 scripts/state.py --state workspace/STATE.json show --json
```

## 4. Создать базовые artifacts

```bash
python3 scripts/state.py --state workspace/STATE.json template \
  --kind master_brief --out workspace/master-brief.json
python3 scripts/state.py --state workspace/STATE.json template \
  --kind diagnosis --out workspace/diagnosis.json
python3 scripts/state.py --state workspace/STATE.json template \
  --kind capability_review --out workspace/capability.json
```

Заполни их фактическими результатами полного чтения и live UI. Затем
зарегистрируй:

```bash
python3 scripts/state.py --state workspace/STATE.json artifact \
  --kind master_brief --file workspace/master-brief.json
python3 scripts/state.py --state workspace/STATE.json artifact \
  --kind diagnosis --file workspace/diagnosis.json
python3 scripts/state.py --state workspace/STATE.json artifact \
  --kind capability_review --file workspace/capability.json
```

## 5. Прогнать каждый обязательный detector

Повтори для каждого service×target:

```bash
python3 scripts/state.py --state workspace/STATE.json detector-prepare \
  --service zerogpt --target DOCUMENT \
  --out workspace/evidence/zerogpt-challenge.json

python3 scripts/state.py --state workspace/STATE.json detector \
  --observation workspace/evidence/zerogpt-observation.json
```

Observation создаётся по
`assets/templates/detector-observation.json` после реального browser result.

## 6. Зафиксировать подсветки и round

```bash
python3 scripts/state.py --state workspace/STATE.json template \
  --kind detector_round --out workspace/evidence/round-R001.json
```

Заполни coverage, все visible highlights, manual diagnostic zones,
`editor_analysis` и `next_action`. Не изменяй auto-filled score matrix.

```bash
python3 scripts/state.py --state workspace/STATE.json artifact \
  --kind detector_round --file workspace/evidence/round-R001.json
```

Если любой score `>=20%`, round обязан быть `requires_edit`.

## 7. Пометить и минимально исправить

Работай через отдельную annotated copy:

```bash
python3 scripts/annotations.py workspace/working-annotated.md --validate
python3 scripts/state.py --state workspace/STATE.json move \
  --id M01 --span "P4-P5" --mechanism rhythm_restructure \
  --hypothesis "Break repeated cadence while preserving both qualified claims."
```

После правки:

```bash
python3 scripts/fidelity_check.py \
  --original workspace/original.md --edited workspace/working.md --json
python3 scripts/minimality.py \
  --original workspace/original.md --current workspace/working.md --json
python3 scripts/english_level.py \
  --text workspace/original.md --edited workspace/working.md --json
```

Старая detector evidence теперь stale. Снова прогони **все** обязательные
сервисы и зарегистрируй новый round. Повторяй до hard pass.

## 8. Финальные функции и перепроверка

Выполни F2/F3/F4, если они выбраны. После регистрации их artifacts обязательно
снова прогони весь mandatory detector scope и зарегистрируй final passing
round.

Затем заполни:

- `semantic_review`;
- `style_review`;
- `constraints_review`;
- `proofread`;
- `report`;
- route-specific artifacts.

## 9. Проверить и закрыть

```bash
python3 scripts/state.py --state workspace/STATE.json verify
python3 scripts/state.py --state workspace/STATE.json close
```

`close` невозможен, если:

- хотя бы один mandatory score `>=20%`;
- нет результата или он stale/tampered;
- сервис blocked;
- detector round неполон или требует edit;
- final round зарегистрирован раньше F2/F3/F4;
- остался любой другой red gate.

Plateau документирует blocker, но не завершает F1.
