# Отчёт Palimpsest v3.2

Дата: · Рабочий SHA-256: · Итоговый статус: OPEN / READY_WITH_LIMITS / CLOSED

## Изменения

- исходный жанр, язык и объём:
- активные функции: F1 / F2 / F3 / F4 / none
- режим стиля: `external_reference` / `source_as_reference`
- целевой уровень английского и оценка исходника (если применимо):
- какие проблемы были подтверждены:
- какие минимальные вмешательства выполнены:
- document change ratio: X при бюджете Y
- что сознательно не менялось:

## Проверки

### Верность и минимальность

- `fidelity_check.py`: pass / fail; SHA отчёта:
- semantic source-unit reconciliation: N из N; SHA:
- `minimality.py`: pass / fail; document/paragraph ratios:
- числа, единицы, модальность, причинность, хронология и роли:
- externally authorized change claims, source-unit/offset binding и жёлтый G7:

### Стиль и уровень языка

- baseline: внешний корпус / исходный текст как собственный референс
- Ductus (только для внешнего корпуса): IMPORT / ADAPT / QUARANTINE
- `style_distance.py`: reliability; baseline → final; применённый policy или advisory:
- English-level screen: source estimate → final estimate; target; drift signals:
- ручная проверка уровня: лексика, синтаксис, идиоматика, learner voice
- случайные ошибки исправлены без искусственного добавления новых ошибок:

### Детекторы (только если F1 включён)

Выбранный пользователем набор: · Порог: · Minimum independent: · Coverage:

| Сервис | Target | Content SHA | Score | Checked at | Challenge | Raw capture SHA | Итог |
|---|---|---|---:|---|---|---|---|
| | | | | | | | pass / fail / waived / plateau |

- ZeroGPT присутствует: да / нет / F1 выключен
- capability review SHA и возраст:
- независимые passing groups:
- формальный plateau bundle (если есть):
- waivers, каждый для точного service/target/SHA:

Сырые снимки подтверждают сохранённое наблюдение, но не доказывают авторство и
не дают гарантии результата на другой версии сервиса.

### Дополнительные маршруты

- F2 structure review:
- F3 claim ledger, первичные источники и даты:
- F4 overlap report, атрибуция и разрешённые цитаты:
- pattern scan (advisory):
- constraints review:
- proofread и отсутствие рабочих аннотаций:

### Long-form и память

- `segment.py status`: сегментов N; coverage X%; changed/new/risk:
- browser coverage: все targets / принятая risk sample:
- orphaned prior IDs:
- `MEMORY.md` refresh:
- `TERMS.md` lost:
- edit-amplified echoes:

## Ограничения

- детекторный корпус EN 3+3 — пилот, не оценка популяционной точности:
- RU core остаётся provisional до полного отдельного корпуса:
- CEFR определяется приближённо и подтверждается редакторской сверкой:
- synthetic 15k+ stress проверяет pipeline, а не book-scale редакторское качество:
- browser evidence можно подделать локально; challenge/digest/capture binding
  создаёт аудиторский след, а не криптографическое доказательство:
- yellow gates: локальный CLI не аутентифицирует согласие и оставляет
  `READY_WITH_LIMITS`; требуемое внешнее решение пользователя:
- заблокированные сервисы, лимиты, неполное покрытие или недоступные источники:
- что пользователю следует проверить самостоятельно:
