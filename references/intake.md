# Интейк v3.2

## Правило

Четыре вопроса задаются по одному и в этом порядке. Вопросы о стилевом baseline
и наборе детекторов задаются всегда: молчание не означает согласие. Не
переспрашивай уже явный ответ, но всё равно коротко назови сделанный вывод и
запиши `source=inferred_from_user_message`. Нельзя выводить лицензионное,
фактическое или этическое разрешение из молчания.

## Q1 — стилевой baseline и уровень английского

Предложи два режима:

1. `external_reference` — один или несколько файлов задают решения, ритм и
   мыслительные привычки, но не факты, ссылки или характерные фразы;
2. `source_as_reference` — внешний образец выключен, а исходный редактируемый
   текст становится собственным стилевым эталоном. Это не `n/a`: обязательны
   минимальное вмешательство, `style_distance` против исходника и
   `style_review`.

Для внешнего режима уточни автора, репрезентативность жанру и черты, которые
нельзя переносить. Без реального файла `external_reference` не принимается.

Для любого английского проекта дополнительно спроси целевой уровень:
`A1/A2/B1/B2/C1/C2/native` или `infer_from_source`. Уровень относится к
сложности лексики и синтаксиса, идиоматике, плотности и learner voice. Не
повышай B2 до академического C1/C2 и не упрощай вниз. Не добавляй специально
ошибки: случайную грамматику и опечатки можно исправить, сохранив исходную
сложность и естественную степень неидеальности.

```bash
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q1 --style-mode source_as_reference \
  --english-level B2 \
  --answer "Use the source as its own style baseline; preserve B2 English." \
  --source explicit
```

Внешний вариант:

```bash
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q1 --style-mode external_reference \
  --english-level infer_from_source --ref samples/author.md \
  --answer "Use the supplied file only as a handwriting reference." \
  --source explicit
```

## Q2 — функции

Запиши точную комбинацию:

- F1 — текущие AI-detector signals;
- F2 — структура;
- F3 — факты;
- F4 — оригинальность/атрибуция;
- `none` — ни одна опциональная функция.

Верность, стилевой baseline, ограничения и proofread обязательны при любой
комбинации.

```bash
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q2 --functions F1,F2 \
  --answer "Enable F1 and F2 only." --source explicit
```

## Q3 — точный набор детекторов

Этот вопрос задаётся всегда. Если F1 выключен, ответ — `none`. Если F1 включён:

- ZeroGPT обязателен по постоянному требованию пользователя;
- рекомендованный минимальный EN core — `zerogpt,copyleaks`;
- Copyleaks и любые optional/audit/institutional сервисы можно включить или
  выключить явным выбором;
- GPTZero/Turnitin выбираются только при уже существующем законном доступе или
  предоставленном пользователем отчёте;
- один ZeroGPT технически можно выбрать только после отдельного снижения
  minimum-independent; такой локальный override всегда оставляет G3 жёлтым,
  даже если в audit trail записана дословная цитата.

Не создавай аккаунт, не покупай доступ и не заменяй сервис без согласования.

```bash
python3 scripts/state.py --state workspace/STATE.json intake \
  --question Q3 --services zerogpt,copyleaks \
  --answer "Enable ZeroGPT and Copyleaks; disable all optional services." \
  --source explicit
```

## Q4 — остальные требования

Собрать:

- аудиторию, цель, жанр, язык и регистр;
- объём и допустимую глубину изменения;
- обязательную структуру/формат и citation style;
- термины, protected fragments и запрещённые формулировки;
- detector threshold, доступные institutional accounts/reports;
- дедлайн и формат выдачи.

Язык source определяется из immutable original. Ручной `--language` — только
совпадающее assertion; он не может переключить русский текст на English
detector policy.

## Конфликты

Остановись до массовой правки, если:

- «минимальные правки» и «полностью новый текст» заданы одновременно;
- внешний reference несовместим с жанром или уровнем английского исходника;
- требуемый процент предполагает смысловую порчу;
- пользователь просит убрать обязательную атрибуцию;
- полный detector coverage невозможен и нужна принятая выборка.

Разрешение конфликта — ответ пользователя, не догадка редактора.

## Бюджеты

| Route | document ratio | paragraph ratio |
|---|---:|---:|
| surgical | 0.12 | 0.35 |
| standard | 0.18 | 0.45 |
| longform | 0.18 | 0.45 |

Это начальные ограничители, не нормативы. Повышение фиксируется до массовой
правки. В `source_as_reference` бюджет особенно важен: отсутствие внешнего
образца означает меньше вмешательства, а не свободу переписать голос.

Master brief принимается только после Q1–Q4 и полного чтения текста.
