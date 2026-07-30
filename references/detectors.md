# F1 и детекторы: контракт v3.5

## Содержание

1. Контракт успеха
2. Выбор сервисов
3. Capability review
4. Полный цикл
5. Detector round
6. Long-form
7. Plateau и недоступность
8. Evidence и границы доверия

## 1. Контракт успеха

При F1 автоматически действует `score_mandatory`.

- hard pass: каждый обязательный сервис на каждом target даёт `score < 20%`;
- soft target: стремиться к `score < 15%` везде;
- `20.0%` не проходит;
- ни среднее, ни лучший сервис, ни голосование не заменяют проверку каждого;
- plateau, waiver, blocked, stale evidence и partial coverage не являются
  успешным завершением F1;
- `READY_WITH_LIMITS` никогда не маскирует score `>=20%`.

Score — текущий сигнал конкретного сервиса, а не доказательство авторства.
Нельзя обещать прохождение будущей версии модели.

## 2. Выбор сервисов

После выбора F1 всегда задать пользователю отдельный вопрос. Repeatable
no-sign-up профиль для EN:

1. [ZeroGPT](https://www.zerogpt.com/)
2. [Scribbr AI Detector](https://www.scribbr.com/ai-detector/)
3. [GPTinf](https://gptinf.com/detector)
4. [Copyleaks AI Detector](https://copyleaks.com/ai-content-detector)

Для RU default: ZeroGPT, GPTinf и Copyleaks. GPTZero и QuillBot остаются в
registry и предлагаются отдельно: live-проверка 2026-07-30 показала
sign-up/guest-limit вместо повторяемого результата. Исходный профиль из шести
сервисов сохранён как явная опция:
`zerogpt,gptzero,scribbr,quillbot,gptinf,copyleaks`.

Q3 разрешает явно включить или выключить сервисы перед работой. ZeroGPT
сохраняется как обязательный по постоянному предпочтению пользователя. Каждый
оставленный сервис становится обязательным для этого заказа.

Дубли движков всё равно проверять, если они явно оставлены: Scribbr и QuillBot могут
представлять одно семейство и считаются одним голосом только в аналитике.
GPTinf — агрегатор и не заменяет прямой сервис.

## 3. Capability review

Перед первым score создать live capability review:

```bash
python3 scripts/state.py --state workspace/STATE.json template \
  --kind capability_review --out workspace/capability.json
```

Для каждого выбранного сервиса проверить в видимом UI:

- URL и бренд;
- guest, lawful existing authenticated/institutional access или blocked;
- поддержку языка;
- минимальный/максимальный объём;
- модель/версию, если видна;
- численный результат и доступность подсветок;
- дату и конкретное evidence.

`registry_facts` неизменяемы: validator сверяет `kind`,
`independence_group`, `guest_access`, language support, limit и result format с
registry. Не создавать аккаунт, не платить и не обходить ToS ради гейта.

## 4. Полный цикл

На каждом SHA:

1. Прогнать все обязательные service×target.
2. Сохранить challenge-bound observations.
3. Выписать все видимые подсветки.
4. Если подсветок нет, но score не проходит, вручную локализовать конкретные
   AI-like зоны и объяснить механизм.
5. Зарегистрировать `detector_round`.
6. Поставить inline marks в отдельной редакторской working copy.
7. Внести минимальные правки только по меткам.
8. До отправки кандидата проверить fidelity, minimality, стиль и
   source-relative English level. Quality-rejected кандидат не сканировать ради
   «красивого» score и не включать в Pareto/admission.
9. Снова прогнать все обязательные service×target.

Если первый bounded pass не достигает порога, не крутить cosmetic synonyms.
Подсветка и публичное описание признаков сервиса — только гипотезы. Не
превращать `sentence variation`, perplexity, predictability или «AI phrases» в
массовый split/merge/синонимизацию без воспроизводимого cross-text эффекта.
Так же нельзя использовать «более прямой субъект/claim» как detector-рецепт:
калибровочный сигнал `direct_claim_restoration` не перенёсся на
preregistered holdout. Степень прямоты меняется только по редакторской причине
или ради точного соответствия источнику, а не ради предполагаемого score.
При baseline на отображаемом потолке 100% микроправки нельзя ранжировать как
равно неэффективные: сервис просто не показывает разницу. Если качество уже
дрейфует, а score остаётся на потолке, остановить этот механизм.
После зарегистрированного failed result можно расширить edit envelope:

```bash
python3 scripts/state.py --state workspace/STATE.json edit-budget \
  --document 0.70 --paragraph 1.0 \
  --reason "Mandatory detector score stayed above 20% after a bounded pass."
```

История бюджета должна попасть в итоговый отчёт. Из нескольких прошедших
кандидатов выбирать минимальный diff.

Нельзя перепроверить только провалившийся сервис: любая содержательная правка
инвалидирует всю предыдущую матрицу и detector round.

## 5. Detector round

После регистрации всех observations:

```bash
python3 scripts/state.py --state workspace/STATE.json template \
  --kind detector_round --out workspace/evidence/round-R001.json
```

Не менять автоматически заполненные:

- `working_sha256`;
- `required_services`;
- thresholds;
- `service_results`;
- service/target digests и observation hashes.

Заполнить:

- одну `coverage_declaration` на каждый service×target;
- `highlight_map` с уникальными ID, адресом, excerpt, причиной и origin;
- `editor_analysis`;
- `next_action`.

Для каждого failing service×target нужна хотя бы одна
`visible_highlight` или `manual_diagnosis`. Если UI не показывает spans,
зафиксировать `no_highlight_surface`, но всё равно дать ручную диагностическую
зону. `round_status` вычисляется по scores: `requires_edit` при любом
`score >=20`, иначе `pass`.

```bash
python3 scripts/state.py --state workspace/STATE.json artifact \
  --kind detector_round --file workspace/evidence/round-R001.json
```

После правки старый round становится stale. Для финала нужен новый `pass`
после F2/F3/F4 artifacts, даже если эти проверки не изменили текст.

## 6. Long-form

В F1 auto-route переходит к стабильным сегментам с 1,000 слов. Рекомендуемые
границы `400–950` слов укладываются в наименьший общий публичный word limit.

- покрыть все сегменты;
- не использовать `risk_sampled`;
- не менять границы между сервисами одного раунда;
- привязывать score к exact segment SHA;
- service-level итог считать по worst case, а не по среднему;
- после `segment.py sync` перепроверить все изменившиеся SHA и собрать полную
  текущую матрицу.

## 7. Plateau и недоступность

Plateau нужен как диагноз после трёх materially different, fidelity-safe
кандидатов. Он доказывает только воспроизводимый тупик:

- не делает высокий score зелёным или жёлтым;
- не разрешает закрытие;
- отсекает косметические synonym-only варианты;
- помогает выбрать следующую действительно другую гипотезу.

При blocked сервисе:

1. записать blocked в capability review;
2. не пропускать его молча;
3. спросить пользователя, хочет ли он изменить Q3 scope;
4. менять scope только по реальному новому сообщению пользователя;
5. создать новый state с обновлённым Q3 и заново собрать capability, results
   и rounds: завершённый intake локально не редактируется.

Локальный `waive --user-quote` запрещён в `score_mandatory`: локальный процесс
может выдумать цитату.

## 8. Evidence и границы доверия

Bare `--score` не принимается. Observation связывает challenge nonce, current
target SHA, URL, timestamp, видимый score excerpt и SHA screenshot/PDF/raw API
response. Для browser capture дополнительно проверяются настоящий контейнер,
checksums/markers и минимальный размер изображения. Это защищает от случайного
stale evidence, последующего изменения файла и тривиальной подмены
«PNG header + случайные байты».

Локальный агент всё ещё способен нарисовать правдоподобный поддельный
screenshot: структурная проверка не заменяет OCR или подписанный receipt.
Поэтому capture — аудиторский след, а не криптографическое доказательство.
Никогда не выдумывать проценты или выделенные зоны.
