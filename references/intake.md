# Интейк и GOAL v3.5

## Пользовательский диалог

Задать три основные вопросы по одному. Детекторный scope включить как
обязательный follow-up функции F1.

### Q1 — референс и English level

Всегда спросить, есть ли style-reference файлы.

- `external_reference`: извлечь почерк, мыслительные привычки и ритм, но не
  факты и не характерные фразы;
- `source_as_reference`: исходник сам является стилевым эталоном; изменения
  должны быть ещё меньше.

Для английского записать A1–C2/native или `infer_from_source`. Уровень нельзя
повышать или понижать.

### Q2 — функции

- `F1`: humanization + `score_mandatory`;
- `F2`: менее механическая структура без разрушения жанра;
- `F3`: deep fact-check по первичным/официальным источникам;
- `F4`: originality, close paraphrase и атрибуция;
- `none`: только базовая редактура и обязательные fidelity/style gates.

### Q2-F1 — обязательные детекторы

Если F1 включён, показать стартовый список:

EN no-account candidate profile: `zerogpt,scribbr,gptinf,copyleaks`.

RU no-account candidate profile: `zerogpt,gptinf,copyleaks`.

Отдельно предложить account/limit-sensitive `gptzero` и `quillbot`, а также
исходный профиль из шести сервисов:
`zerogpt,gptzero,scribbr,quillbot,gptinf,copyleaks`.

Спросить, какие включить или выключить. ZeroGPT оставить обязательным по
постоянному требованию пользователя. Не включать по умолчанию сервис, который
в текущем live capability требует регистрации или перестал возвращать
повторяемый guest-result. Каждый оставленный сервис должен пройти strict
`<20%`; target `<15%`.

Copyleaks — quota-sensitive кандидат, а не гарантированно repeatable guest:
holdout-03 получил `scan limit reached` без score после предыдущих успешных
guest-прогонов. Если свежий capability review блокируется, не редактировать
текст ради access-проблемы; показать blocker и получить новый Q3.

В state этот follow-up записывается как Q3.

### Q3 — требования

Собрать аудиторию, цель, жанр, язык, объём, структуру, citation style,
protected fragments, обязательные термины, запрещённые формулировки и формат
выдачи. В state это Q4.

## GOAL

После ответов state сохраняет:

- functions;
- style mode;
- English level;
- customer requirements;
- `score_mandatory`;
- mandatory detector scope;
- hard pass `every score <20%`;
- target `every score <15%`;
- closure rule.

Перед каждым этапом сверять действие с GOAL. Не заменять GOAL более удобной
редакторской доктриной.

## Изменение detector scope

Blocked сервис не исключается локальной цитатой. Остановиться, показать
конкретный blocker и спросить пользователя. Только фактический новый ответ
может переопределить Q3. После Q4 intake заблокирован: создать новый state с
новым scope и не переносить старые capability, observations, rounds, plateaus
или waivers как current evidence.

## Бюджеты

| Режим | document ratio | paragraph ratio |
|---|---:|---:|
| без F1, surgical | 0.12 | 0.35 |
| без F1, standard/longform | 0.18 | 0.45 |
| F1 score_mandatory default | 0.30 | 0.60 |

Бюджет — ограничитель, не квота. Начинать с минимального diff. Повышать
осознанно командой `state.py edit-budget` только после зарегистрированного
score `>=20%`. Blocked access не является причиной менять текст: сначала
решить scope/access. Команда требует причину, хранит
историю и ограничивает document ratio значением `0.85`. После расширения
сравнить несколько meaning-safe кандидатов и выбрать наименее изменённый из
реально прошедших, а не называть большой rewrite «минимальной правкой».

## Конфликты

Остановиться и запросить решение, если:

- порог требует смысловой порчи;
- reference несовместим с жанром;
- пользователь просит убрать обязательную атрибуцию;
- lawful access к обязательному сервису отсутствует;
- требования к структуре противоречат друг другу.

Не объявлять такой конфликт успехом или `READY_WITH_LIMITS`.
