# Живая EN-апробация Palimpsest 3.5

Дата: 2026-07-30

Режим: F1, `score_mandatory`, full-document coverage

Original: [`evals/fixtures/ai-en.md`](../evals/fixtures/ai-en.md)

Original SHA-256: `4019dc16cfef048eaacf8b3c2419fd0ea26814ddbc662941c221cf0093542fe1`

Passing candidate:
[`evals/fixtures/edited-success-en.md`](../evals/fixtures/edited-success-en.md)

Candidate SHA-256: `13d4816b3fb226b202b1b24c12c3bae360dd8311285ee3e5083b9acab40069fa`

Это forward edit-cycle на одном синтетическом техническом образце. Он
проверяет, способен ли реальный цикл довести конкретный EN-текст до hard pass.
Это не population benchmark точности детекторов и не гарантия будущего
результата на любом тексте.

## Что изменилось относительно прежнего smoke

Прежняя апробация остановилась на baseline fail: ZeroGPT 63,1%, остальные
доступные сервисы 100%, QuillBot blocked. Новый прогон не подменяет этот
результат: он сохраняет baseline, делает несколько meaning-safe кандидатов и
перепроверяет итоговый текст.

## Выбранный scope

Повторяемое EN-ядро без обязательной регистрации:

1. ZeroGPT;
2. Scribbr;
3. GPTinf;
4. Copyleaks.

GPTZero и QuillBot проверены как optional capability. В текущей сессии их
повторный guest path привёл к sign-up/scan limit, поэтому они не были тихо
объявлены прошедшими и исключены из default no-sign-up profile. Пользователь
по-прежнему может включить их в Q3; тогда они становятся mandatory и blocked
результат оставляет F1 открытым.

## Live before/after

| Service | Baseline | Passing candidate | Hard `<20%` |
|---|---:|---:|---:|
| ZeroGPT | 63,1% | 5,3% | pass |
| Scribbr | 100% | 0% | pass |
| GPTinf | 100% | 0% | pass |
| Copyleaks | 100% | 0% | pass |

Scribbr видимо использует семейство QuillBot. GPTinf видимо заявляет
cross-check нескольких сервисов и остаётся агрегатором. Независимый минимум
обеспечивают ZeroGPT и Copyleaks; дубли/агрегатор не раздувают число
независимых голосов.

## Редакторский результат

| Проверка | Результат |
|---|---|
| Pattern scan | P0=0, P1=0, P2=0 |
| Explicit English level | B2 pass |
| Minimality | document change ratio 0,7925 при explicit budget 0,85 |
| Protected invariants | числа, единицы, отрицание, модальность и citations не менялись |
| Detector target | все четыре результата также `<15%` |

`0,7925` — большой rewrite, а не «минимальная корректура». Он был нужен для
Copyleaks, который оставался на 100% у более близких вариантов. В продукте
такое расширение разрешается только после recorded failed evidence через
`state.py edit-budget`; история бюджета попадает в state. Из проходящих
кандидатов должен выбираться наименее изменённый.

Deterministic fidelity screen на глубоком paraphrase ожидаемо выдал lexical
`CLAIM_DROPPED`/`CLAIM_ADDED`. Обновлённый G7 разрешает reconciliation только
для этих кодов и только через exact, monotonic, digest-bound semantic mapping.
Числа, отрицание, причинность, модальность, chronology, URLs, формулы,
protected literals и citations этим путём снять нельзя.

## Граница evidence

Scores были прочитаны из видимого live result DOM. Автоматический screenshot
capture в этой сессии вернул ошибку браузера, поэтому этот документ не выдаёт
DOM transcription за криптографически подписанный receipt. State machine
по-прежнему требует raw capture для регистрируемой observation и честно
считает локальный screenshot аудиторским следом, а не доказательством
авторства.

## Вывод

Апробация теперь подтверждает две разные вещи:

- fail-closed процесс не закрывает baseline с высокими scores;
- реальный EN edit-cycle на конкретном образце доведён до `<20%` и `<15%` на
  всём repeatable no-sign-up core.

Она не доказывает универсальную гарантию. На другом жанре, уровне английского,
длине или после обновления detector models цикл должен выполняться заново.
