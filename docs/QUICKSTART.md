# Быстрый сквозной сценарий

Этот пример показывает базовый `source_as_reference` workflow без внешнего
стилевого образца.

## 1. Подготовьте файлы

```bash
mkdir -p workspace/evidence
cp essay.md workspace/original.md
cp essay.md workspace/working.md
```

Оригинал после `init` не редактируется.

## 2. Создайте state

```bash
python3 scripts/state.py --state workspace/STATE.json init \
  --original workspace/original.md \
  --working workspace/working.md \
  --flags F1,F2
```

Язык определяется из source. Несовпадающий ручной `--language` будет отклонён.

## 3. Запишите intake

```bash
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q1 --style-mode source_as_reference \
  --english-level infer_from_source \
  --answer "Use the source as its own style reference." --source explicit

python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q2 --functions F1,F2 \
  --answer "Enable F1 and F2." --source explicit

python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q3 --services zerogpt,copyleaks \
  --answer "Use ZeroGPT and Copyleaks only." --source explicit

python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q4 \
  --answer "Preserve claims, headings, citations, and learner English." \
  --source explicit
```

## 4. Создайте evidence templates

```bash
python3 scripts/state.py --state workspace/STATE.json template \
  --kind master_brief --out workspace/master-brief.json
python3 scripts/state.py --state workspace/STATE.json template \
  --kind diagnosis --out workspace/diagnosis.json
python3 scripts/state.py --state workspace/STATE.json template \
  --kind semantic_review --out workspace/semantic-review.json
python3 scripts/state.py --state workspace/STATE.json template \
  --kind style_review --out workspace/style-review.json
```

Шаблоны нельзя принимать механическим переключением `pending` → `pass`.
Каждый пункт требует конкретного evidence.

## 5. Проведите baseline

```bash
python3 scripts/pattern_scan.py workspace/working.md
python3 scripts/fidelity_check.py \
  --original workspace/original.md \
  --edited workspace/working.md --json
python3 scripts/minimality.py \
  --original workspace/original.md \
  --current workspace/working.md --json
python3 scripts/english_level.py \
  --original workspace/original.md \
  --edited workspace/working.md \
  --target B2 --json
```

## 6. Редактируйте bounded moves

```bash
python3 scripts/state.py --state workspace/STATE.json move \
  --id M01 --span P4-P5 \
  --mechanism rhythm_restructure \
  --hypothesis "Break the repeated cadence while retaining both claims."
```

После каждого смыслового batch повторяйте fidelity и minimality.

## 7. Запишите detector observation

Сначала получите новый живой результат для точного current SHA, затем:

```bash
python3 scripts/state.py --state workspace/STATE.json detector-prepare \
  --service zerogpt --target DOCUMENT \
  --out workspace/evidence/zerogpt-challenge.json

python3 scripts/state.py --state workspace/STATE.json detector \
  --observation workspace/evidence/zerogpt-observation.json
```

Повторите для каждого сервиса из Q3.

## 8. Финальная проверка

```bash
python3 scripts/state.py --state workspace/STATE.json verify
python3 scripts/state.py --state workspace/STATE.json close
```

- red — исправить или остановиться;
- yellow — `READY_WITH_LIMITS`, локального auto-close нет;
- все активные gates green — `CLOSED`.

Подробные правила находятся в [SKILL.md](../SKILL.md).
