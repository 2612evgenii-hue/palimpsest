# Shadow-validation на реальной работе

## Зачем нужен этот режим

Лабораторный корпус проверяет воспроизводимость, но не заменяет реальную
редакторскую работу. Shadow-case использует копию настоящего проекта, чтобы
сравнить минимальные смысло- и стилесохраняющие варианты, не задерживая выдачу
пользователю и не превращая клиентский текст в публичный датасет.

Это отдельный исследовательский слой. Он не меняет F1-контракт проекта:
обязательные сервисы, strict `<20%`, target `<15%`, fidelity, genre, Ductus и
English level по-прежнему проверяются через `state.py`.

## Privacy first

По умолчанию использовать `delivery_only`:

- исходник, варианты, captures и case JSON остаются только в приватном
  workspace;
- ничего из case нельзя коммитить в публичный репозиторий;
- metrics нельзя объединять с исследовательским корпусом;
- пользователь получает обычный результат независимо от shadow-case.

`private_research` допустим только после отдельного явного согласия владельца
текста на повторное использование **агрегированных** метрик. Скрипт хранит
только SHA-256 конкретной цитаты согласия, а не её текст. Это аудиторский след,
не криптографическое доказательство авторизации. Не считать согласие заказчика
разрешением раскрывать данные его работодателя, клиента, соавтора или
испытуемого.

Публичный export из shadow-case запрещён. Если когда-либо нужен открытый
корпус, для него требуется отдельное разрешение, деидентификация и новая
проверка, не этот workflow.

## Два evidence tier

1. `delivery_diagnostic` — один практический прогон на service×candidate.
   Полезен для выбора варианта в текущей работе, но не для вывода о переносе.
2. `research_candidate` — три заранее заданных повтора, только при
   `private_research`. Такой case можно включить в будущий aggregate review,
   но один case никогда не допускает production-правило.

Blocked/error записываются как состояния, не как проценты. Они делают ячейку
неполной.

## Порядок работы

### 1. Создать локальный case

Идентификатор не должен содержать имя человека, организацию, тему договора
или номер заказа.

```bash
python3 scripts/shadow_case.py init \
  --case workspace/shadow/case.json \
  --case-id real-en-001 \
  --original workspace/original.md \
  --language en --genre academic_report --english-level B2 \
  --services zerogpt,scribbr,gptinf,copyleaks \
  --privacy-mode delivery_only \
  --evidence-tier delivery_diagnostic
```

Для consented private research:

```bash
python3 scripts/shadow_case.py init \
  --case workspace/shadow/case.json \
  --case-id real-en-002 \
  --original workspace/original.md \
  --language en --genre technical_report --english-level C1 \
  --services zerogpt,scribbr,gptinf,copyleaks \
  --privacy-mode private_research \
  --evidence-tier research_candidate \
  --consent-quote "I allow aggregate private research metrics from this text."
```

### 2. Сначала построить quality-safe кандидатов

Не смотреть новые detector scores при выборе факторов. Baseline добавляется
автоматически. Каждый следующий кандидат должен иметь одну понятную гипотезу,
локальную operation summary и конкретные evidence по fidelity, style и уровню
языка:

```bash
python3 scripts/shadow_case.py add-candidate \
  --case workspace/shadow/case.json \
  --candidate workspace/candidate-C001.md --id C001 \
  --hypothesis-id remove_redundant_frame \
  --operation-summary "Removed one repeated framing sentence; claims unchanged." \
  --quality-status pass \
  --fidelity-evidence "Source-unit review preserves every claim and qualifier." \
  --style-evidence "Sentence rhythm remains inside the source-as-reference envelope." \
  --english-level-evidence "B2 syntax and vocabulary profile remains source-relative."
```

Quality-rejected варианты можно сохранить как отрицательные проектные решения,
но сканировать их нельзя.

### 3. Заморозить план до scores

```bash
python3 scripts/shadow_case.py freeze \
  --case workspace/shadow/case.json
```

Freeze связывает original, все candidate SHA, hypotheses, quality evidence,
detector scope, privacy и repeat policy одним digest. После этого нельзя
добавлять кандидатов. Новый адаптивный раунд требует нового case.

### 4. Подготовить и записывать только terminal observations

Сначала создать SHA-prefilled template для конкретной замороженной ячейки:

```bash
python3 scripts/shadow_case.py prepare-observation \
  --case workspace/shadow/case.json \
  --candidate-id C001 --service zerogpt --repeat 1 \
  --out workspace/shadow/observations/C001-zerogpt-1.json
```

Команда не создаёт score и не делает evidence валидным. Она только фиксирует
candidate/service/repeat, candidate SHA и registry URL, чтобы не перепутать
ячейку. После live result заполнить terminal поля:

Каждый observation — отдельный JSON:

```json
{
  "schema": "palimpsest.shadow-observation.v1",
  "candidate_id": "C001",
  "service": "zerogpt",
  "repeat": 1,
  "status": "scored",
  "candidate_sha256": "<exact candidate SHA-256>",
  "post_visible_text_sha256": "<SHA-256 of visible text after result>",
  "score_pct": 12.4,
  "terminal_state": "complete",
  "transition_signal": "loading_or_disabled_observed",
  "observed_at": "2026-07-30T20:00:00+00:00",
  "result_url": "https://www.zerogpt.com/",
  "visible_result_excerpt": "Visible result: 12.4% AI.",
  "evidence": {
    "kind": "state_detector_observation",
    "path": "../evidence/zerogpt-observation.json",
    "sha256": "<SHA-256 of the complete source evidence JSON>"
  },
  "capture_status": "missing",
  "capture_limitation": "The browser returned a DOM result but capture timed out."
}
```

`evidence` связывает shadow row с challenge-bound observation основного state
или с отдельной browser-session записью. Blocked observation содержит
`score_pct: null`, `terminal_state: "blocked"` и конкретный
`visible_terminal_message`. Не переносить число из другого запуска, не
угадывать score по цвету/loader и не восстанавливать потерянный timestamp.

```bash
python3 scripts/shadow_case.py record \
  --case workspace/shadow/case.json \
  --observation workspace/shadow/observations/C001-zerogpt-1.json
```

### 5. Сравнить Pareto и запечатать case

```bash
python3 scripts/shadow_case.py summary \
  --case workspace/shadow/case.json
```

В frontier входят только quality-pass кандидаты с полной mandatory matrix и
требуемым числом повторов. `least_changed_hard_pass` — самый дешёвый из
кандидатов, которые реально прошли scope, а не обещание, что правка мала.

После проверки terminal matrix:

```bash
python3 scripts/shadow_case.py seal \
  --case workspace/shadow/case.json --outcome completed
```

`completed` принимается только при полной matrix всех quality-pass кандидатов.
Если сервис blocked или исследование осознанно остановлено:

```bash
python3 scripts/shadow_case.py seal \
  --case workspace/shadow/case.json --outcome stopped \
  --reason "Copyleaks reached its guest scan limit before the matrix completed."
```

Seal связывает digest всех observations и вычисленного summary. После него
нельзя записать новую observation; изменение score/evidence делает seal stale.

## Что можно вынести в skill

Одна реальная работа показывает поведение конкретного текста и текущих версий
сервисов. Production-механизм рассматривается только после:

- заранее определённого factor;
- нескольких независимых текстов целевого жанра;
- human controls, где это возможно;
- стабильных same-SHA repeats;
- эффекта выше шума в независимых detector groups;
- отсутствия semantic/style/CEFR regression;
- отдельного preregistered holdout.

Detector highlights, разовый удачный diff и vendor-объяснение сами по себе не
являются правилом.
