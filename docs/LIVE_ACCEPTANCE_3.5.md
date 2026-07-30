# Живая EN-апробация Palimpsest 3.5

Дата: 2026-07-30  
Режим: F1, `score_mandatory`, full-document coverage  
Образец: [`evals/fixtures/ai-en.md`](../evals/fixtures/ai-en.md)  
SHA-256: `4019dc16cfef048eaacf8b3c2419fd0ea26814ddbc662941c221cf0093542fe1`  
Объём: 190 слов, 1 401 символ

Это live smoke-test редакторского контура, а не benchmark точности
детекторов. Один технический образец не позволяет ранжировать сервисы или
оценивать false positives на популяции.

## Наблюдения в браузере

| Mandatory service | Доступ без регистрации | Результат на полном образце | Итог для G3 |
|---|---:|---:|---|
| ZeroGPT | Да | 63,1% AI | fail |
| GPTZero | Один guest result, затем sign-up | 100% AI | fail |
| Scribbr | Да | 100% AI-generated | fail |
| QuillBot | Форма доступна | результат не вернулся | blocked |
| GPTinf | Да | 100% AI GPT | fail |
| Copyleaks | Да | 100% AI Content Found | fail |

Scribbr в собственной result surface обозначает QuillBot; поэтому оба бренда
остаются обязательными при таком Q3 scope, но не считаются двумя независимыми
голосами. GPTinf видимо заявляет cross-check нескольких сторонних сервисов и
остаётся агрегатором.

## Проверка state machine

Для пяти вернувших результат сервисов были созданы current
challenge-bound observations. QuillBot отмечен `blocked` в
`capability_review`; исключать его без нового пользовательского решения Q3
не разрешалось.

`verify` вернул ненулевой код и красный G3:

```text
zerogpt/DOCUMENT: 63.1% is not strictly below 20%
gptzero/DOCUMENT: 100% is not strictly below 20%
scribbr/DOCUMENT: 100% is not strictly below 20%
quillbot/DOCUMENT: capability not confirmed and no scoped waiver
gptinf/DOCUMENT: 100% is not strictly below 20%
copyleaks/DOCUMENT: 100% is not strictly below 20%
DOCUMENT: only 0 independent passing groups; need 2
detector_round: not registered
```

Попытка `close` завершилась кодом `2`:

```text
FAIL: cannot close: blocker gates G0, G1, G3, G7, G8, G9, G10
```

## Вывод

Контрольный проект не объявлен успешным. Высокие scores не превращаются в
yellow/`READY_WITH_LIMITS`, а недоступный mandatory service не исчезает из
матрицы. Для реального заказа следующий допустимый шаг — продолжить
check→mark→edit→recheck после восстановления QuillBot либо получить от
пользователя новое явное решение Q3 об исключении сервиса.

Тест подтверждает fail-closed поведение живого контура. Он не подтверждает,
что данный 190-словный образец доведён до `<20%`: такого результата в этой
сессии не было, и релиз его не заявляет.
