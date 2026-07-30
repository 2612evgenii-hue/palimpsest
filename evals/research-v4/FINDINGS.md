# Текущие результаты исследования 4.0

Статус: calibration, не правила production-skill.

## Superseded: B1 essay pilot-02

В `pilot-02-b1.json` были стабильные результаты, но forward-test Sapling
обнаружил trailing spaces в upstream AIGC text и service-specific
нормализацию contenteditable. Pilot проверял SHA до scan, а не после terminal
state. Поэтому таблица ниже сохраняется только как история и не является
evidence для 4.0:

| Кандидат | Edit cost | ZeroGPT | Scribbr v7.1.0 | Исторический результат |
|---|---:|---:|---:|---|
| Human control, ICNALE B1 | 0 | 25.5% ×3 | 0% ×3 | подтверждён FP ZeroGPT |
| AI baseline, DeepSeek | 0 | 51.0% ×3 | 28% ×3 | baseline |
| Merge двух предложений | 0.15% | 50.6% ×3 | 32% ×4 | отвергнуто: cross-detector regression |
| Локальная правка тезиса | 1.77% | 53.6% ×3 | — | отвергнуто |
| Split balanced frame | 2.26% | 52.4% ×3 | — | отвергнуто |
| Remove agreement frame | 1.76% | 60.3% ×3 | — | отвергнуто |

Все просканированные варианты сохраняли B1 по консервативному экрану и прошли
deterministic fidelity screen. Rhetorical-to-declarative вариант не был
просканирован: fidelity screen отметил `NEGATION_CHANGED`; до семантической
проверки такой кандидат не допускается.

## Что pilot-02 позволил обнаружить

1. Подсвеченная детектором фраза не является надёжной инструкцией по
   редактированию. Изменение одного такого участка может повысить общий score.
2. Реакции сервисов направлены по-разному. Локальное снижение одного score
   нельзя превращать в правило без независимой cross-detector проверки.
3. Human control обязателен: на реальном B1 learner text ZeroGPT превысил
   production-порог, хотя связанный Scribbr дал 0%.
4. Минимальность должна учитывать символы и spans, а не только слова:
   пунктуационная перестройка имела word ratio 0, но не была нулевой правкой.
5. Corpus и browser runner обязаны канонизировать transport whitespace и
   проверять SHA только после terminal state.

## Что пока утверждать нельзя

- что merge/split, удаление frame или замена риторического вопроса обычно
  уменьшает AI score;
- что ZeroGPT 25.5% является стабильным FP на других B1 текстах;
- что нулевой наблюдаемый разброс сохранится в другой день или версии модели;
- что найден путь к `<20%` при малом бюджете.

Текущие claims должны опираться на `pilot-03-canonical.json`,
`pilot-04-b1-canonical.json` и `pilot-05-tech-canonical.json`, а не на эту
историческую таблицу.

## Current: scientific abstract pilot-03

Все тексты приведены к `plain_text_v1`; SHA проверен после terminal state.

| Кандидат | Edit cost | ZeroGPT | Scribbr v7.1.0 | Sapling | Решение |
|---|---:|---:|---:|---:|---|
| Human control | 0 | 0% ×3 | 0% ×3 | 100% ×1 | Sapling false positive |
| AI baseline | 0 | 25.3–26.0% | 20% ×3 | 99.6% ×1 | baseline fail |
| S2 split mechanism | 0.73% | 0% ×3 | 19% ×3 | 99.6% ×1 | не допущено |

S2 — первый кандидат с edit cost `<1%`, который одновременно прошёл ZeroGPT
и Scribbr. Но Sapling не сдвинулся, поэтому это не cross-family правило и не
доказательство решения F1. Особенно важен human control: Sapling дал 100% на
реальном научном abstract, тогда как два других сервиса дали 0%.

Варианты S1/S5 с edit cost около 0.5–0.63% не прошли ZeroGPT/Scribbr. Более
глубокие S3/S4 дали низкие scores в двух сервисах, но не являются
least-changed candidate и пока имеют недостаточно повторов.

## Current: B1 transfer and highlight pilot-04

`pilot-04` повторил B1-пару после `plain_text_v1` и проверял SHA только после
terminal state. В исходный план добавлены пять новых вариантов: четыре внутри
подсветки ZeroGPT и один location control вне подсветки.

| Кандидат | Edit cost | ZeroGPT | Scribbr v7.1.0 | Sapling | Решение |
|---|---:|---:|---:|---:|---|
| Human control, ICNALE B1 | 0 | 25.5% ×3 | 0% ×3 | 99.5% ×1 | два тяжёлых FP |
| AI baseline | 0 | 51.0% ×3 | 28% ×3 | 100% ×1 | baseline fail |
| S4 punctuation merge | 0.15% | 50.6% ×3 | 32% ×3 | 100% ×1 | отвергнуто: regression |
| S10 outside-highlight control | 2.0% | 50.0–50.1% | 27% ×3 | 100% ×1 | малый эффект, не pass |

Четыре новые допустимые правки внутри подсвеченных предложений дали ZeroGPT
`51.4–55.3%`, то есть не улучшили baseline. Контроль вне подсветки стабильно
снизил ZeroGPT примерно на 0.9 пункта и Scribbr на 1 пункт, но остался далеко
выше `<20%` и не сдвинул Sapling.

Практический вывод: подсветка — место статистического подозрения сервиса, но
не причинная инструкция «редактировать здесь». Для каждой такой гипотезы нужен
outside-highlight control. Human controls также показали, что score нельзя
интерпретировать как авторство: Sapling почти не разделил human и AI
(`99.5%` против `100%`), а ZeroGPT дал человеческому B1-тексту `25.5%`.

S3 был ошибочно включён в первичный ZeroGPT screen при известном
`NEGATION_CHANGED`. Результат сохранён для аудита, помечен
`quality_rejected_exploratory` и исключён из Pareto и admission.

## Current: technical C1 saturation pilot-05

`pilot-05` использует связанную human/DeepSeek пару из одной строки
AIGC-text-bank. AI-текст — техническое объяснение объёмом 191 слово; при
отсутствующем внешнем референсе он сам служит style reference. Целевой уровень
зафиксирован как C1.

| Кандидат | Edit cost | ZeroGPT | Scribbr v7.1.0 | Sapling | Решение |
|---|---:|---:|---:|---:|---|
| Human control | 0 | 38% ×3 | 0% ×3 | 99,1% ×1 | тяжёлый FP в Sapling, FP ZeroGPT |
| AI baseline | 0 | 100% ×3 | 100% ×3 | 100% ×1 | saturated baseline |
| 8 допустимых single-factor | 0,15–2,36% | 100% ×1 | 100% ×1 | — | нет измеримого эффекта |
| P2: punctuation + verb | 0,52% | 100% ×3 | 100% ×3 | 100% ×1 | baseline доминирует |
| P4: + two splits | 1,55% | 100% ×1 | 100% ×1 | — | rejected: CEFR drift |
| P6: + frame removals | 5,04% | 100% ×1 | 100% ×1 | — | rejected: CEFR/style |
| P7: + analogy removal | 7,32% | 100% ×1 | 100% ×1 | 100% ×1 | rejected: CEFR/style |

ZeroGPT отметил все 11 предложений baseline. Поэтому highlight map не дал
локальной гипотезы: «редактировать подсвеченное» означало бы редактировать весь
текст. Восемь прошедших quality screen микроправок — пунктуация, локальный
глагол, удаление мета-перехода, parenthetical structure, два split,
снятие аналогии и прямое начало — не сдвинули ни ZeroGPT, ни Scribbr с потолка
100%.

Progressive bundles были диагностическим ceiling/cliff probe, а не попыткой
обойти критерий допуска комбинаций. Уже P4 вышел за допустимый C1 drift, P6/P7
дали style distance выше 30, но score всё равно не изменился. Практический
вывод: на таком saturated sample эскалацию нужно остановить раньше потери
уровня и почерка. Правила «менять пунктуацию», «делить предложения» или
«удалять AI-like frame» из этого пилота не допускаются.

Copyleaks принял точный human-control текст в публичную форму, но после submit
вернул `scan limit reached`; score не записан и не восстановлен догадкой.

## Holdout-01: перенос scientific sentence split

Holdout был опубликован отдельным commit `0adc161` до live-scores. Он проверял
единственную confirmatory-гипотезу из pilot-03: минимальный split, отделяющий
механизм/следствие, переносится на два зарезервированных PubMed AI-текста.
`citation-first` и удаление generic/synthesis frame были заранее объявлены
только как exploratory comparators.

Confirmatory H1 остановился на quality gate:

| Sample | Edit cost | Грубый CEFR | Reading grade Δ | Style distance | Решение |
|---|---:|---:|---:|---:|---|
| PubMed-03 H1 | 0,48% | C2 → C2 | −1,697 | 26,6 | rejected до detector scan |
| PubMed-04 H1 | 1,48% | C2 → C2 | −1,320 | 23,9 | rejected до detector scan |

Одинаковая метка C2 скрывала source-relative упрощение выше допустимого
reading-grade threshold. По preregistration отклонённые H1 не отправлялись в
детекторы и не могли поддержать transfer независимо от потенциального score.

Live baselines и компараторы:

| Sample / кандидат | ZeroGPT | Scribbr v7.1.0 | Sapling |
|---|---:|---:|---:|
| PubMed-03 human | 0% ×3 | 0% ×3 | 96,4% ×1 |
| PubMed-03 AI baseline | 100% ×3 | 100% ×3 | 100% ×1 |
| PubMed-03 H2/H3 | 100% ×1 | 100% ×1 | — |
| PubMed-04 human | 42,9% ×3 | 0% ×3 | 100% ×1 |
| PubMed-04 AI baseline | 100% ×3 | 100% ×3 | 100% ×1 |
| PubMed-04 H2/H3 | 100% ×1 | 100% ×1 | — |

Copyleaks принял полный PubMed-03 human control с точным SHA, но более 50 секунд
оставался в disabled loading-state и не выдал score. Результат — `error`, не
число.

Итог: успешных holdout samples `0/2`; перенос `sentence_length_variation` не
подтверждён. В skill добавлен только отрицательно подтверждённый guardrail:
не использовать blanket split/merge как detector-рецепт и не сканировать
quality-rejected кандидат ради благоприятного процента.

## Baseline scout-01: окно для измерения микроправок

Scout был заморожен и опубликован commit `534eda9` до первого нового score.
Он не проверял правки: пять заранее выбранных EN human/AI пар сканировались,
чтобы найти тексты без пола/потолка. Критерий resolvability также был закреплён
заранее: AI `20–90%`, human `≤40%`, разрыв минимум 20 пунктов в одном primary
service.

| Pair | ZeroGPT human → AI | Scribbr human → AI | Решение |
|---|---:|---:|---|
| B2 learner essay, AI-native | 0% → 10,6% | 0% → 0% | ниже окна |
| Scientific abstract, AI-polish | 0% → 63,7–63,8% | 0% → 100% | выбран через ZeroGPT |
| Formal news, AI-polish | 0% → 76,3% | 0% → 0% | выбран через ZeroGPT |
| PubMed-02 | 89,6% → 100% | 0% → 100% | FP + потолок |
| PubMed-05 | 22,3% → 94% | 0% → 100% | вне окна |

ZeroGPT-повторы выбранных ячеек были почти детерминированы: scientific
`63,7 / 63,8 / 63,7`, news `76,3 / 76,3 / 76,3`; оба human controls дали
`0 / 0 / 0`. Copyleaks не предоставил число: scientific scan вернул
`scan limit reached`, news более 50 секунд оставался с 16 loading-индикаторами.

Практический вывод: два текста пригодны для следующего однофакторного
эксперимента именно как измерительные мишени ZeroGPT. Это не означает, что
найден ZeroGPT-рецепт, и тем более не означает cross-detector эффект:
Scribbr поставил тем же AI-polish текстам противоположные крайние оценки
`100%` и `0%`. Следующий вариантный план должен быть снова опубликован до
scores, а результат обязан сохранить fidelity, source-relative C2 и жанр.

## Micro-01: source directness на несатурированных AI-polish текстах

План шести однофакторных вариантов был опубликован commit `e61d817` до первого
micro-score. Во всех вариантах сохранены C2, исходный строгий жанр, claims и
source-as-reference style; edit cost составил `0,30–4,29%`.

| Фактор / sample | Edit cost | ZeroGPT baseline → вариант | Scribbr baseline → вариант | Экран |
|---|---:|---:|---:|---|
| remove evaluative frame / arxiv | 0,30% | 63,7% → 64,0% | 100% → 100% | fail |
| remove evaluative frame / news | 0,50% | 76,3% → 76,2% ×3 | 0% → 0% ×3 | local only |
| direct subject / arxiv | 1,28% | 63,7% → 63,5% ×3 | 100% → 100% ×3 | formal pass |
| direct subject / news | 1,14% | 76,3% → 76,2 / 0 / 0% | 0% → 0% ×3 | unstable |
| direct claim / arxiv | 4,29% | 63,7% → 62,7 / 61,3 / 61,3% | 100% → 100% ×3 | formal pass |
| direct claim / news | 4,11% | 76,3% → 0% ×3 | 0% → 0% ×3 | formal pass |

По заранее замороженному критерию `direct_subject_restoration` и
`direct_claim_restoration` являются calibration screen successes: первый
ZeroGPT score улучшился сверх baseline noise на обоих текстах, Scribbr не
ухудшился, обязательные повторы завершены. Это всё ещё не cross-detector
эффект: Scribbr был насыщен на arxiv и находился на полу для news, поэтому не
подтверждает величину ZeroGPT response.

Same-SHA диапазон `0–76,2` у news/direct-subject нельзя маскировать медианой.
Он помечен как severe instability и делает «−76,3 пункта при 1,14% правок»
непригодным для продуктового обещания. Следующий эксперимент обязан дождаться
явного перехода UI от предыдущего результата к loading/terminal state и
повторить этот фактор на новом holdout. Даже более стабильный direct-claim
пока остаётся гипотезой: два calibration-текста из одного AI-polish режима и
движение только одной detector family недостаточны для admission.

Один технический timeout дал восстановимые UI scores, но потерял структурную
запись события; он сохранён отдельно и исключён из анализа. Copyleaks получил
точный SHA самого дешёвого advancing-кандидата и вернул
`scan_limit_reached`; score отсутствует. Screenshot capture также отсутствует.
Итог: `rule_admission = none_holdout_required`.

## Holdout-02: перенос direct claim отвергнут

План был опубликован commit `659edea` до первого score. Он заморозил два новых
строгих AI-polish текста, их human controls, одну точную
`direct_claim_restoration` на образец, SHA всех текстов, три повтора и
transition-safe инструментирование. Все 36 включённых сканов привязаны к
точному SHA и имеют доказанный переход от предыдущего результата; один timeout
до submit сохранён отдельно и исключён.

| Sample | Edit cost | ZeroGPT human | ZeroGPT AI → candidate | Scribbr AI → candidate | Verdict |
|---|---:|---:|---:|---:|---|
| arxiv-polish-02 | 7,81% | 0% ×3 | 0% → 0% ×3 | 27% → 25% ×3 | ineligible: ZeroGPT floor |
| news-polish-02 | 2,76% | 41,6% ×3 | 41,6% → 41,7% ×3 | 0% → 0% ×3 | failed: no effect above noise |

Заранее заданный критерий требовал baseline ZeroGPT не ниже 20%, снижение
строго больше same-SHA range и 1 п.п., range не выше 5 п.п. и отсутствие
Scribbr regression больше 5 п.п. Ни один образец не прошёл: итог `0/2`.
Scientific-ячейка не доказывает пользу правки, потому что измерительный сервис
был на полу. Formal-news ячейка не различила human и AI baseline и после
правки ухудшилась на 0,1 п.п.

Следствие для skill отрицательное, но прикладное:
`direct_claim_restoration` не является detector-рецептом. Более прямое
утверждение допустимо только как source-supported редакторская или fidelity
правка. Калибровочный успех `micro-01` не переносится и правило в production
не допускается. Полный результат:
[`holdout-02-result.json`](holdout-02-result.json).

## Baseline-scout-02: стабильное cross-family окно

Шесть новых AI-polish/human пар, порядок, exact SHA и пороги были опубликованы
commit `c45afb3` до первого score. Scout не содержал edit-вариантов. Первичная
матрица включила все 24 pair×role×service ячейки; для трёх пар, где хотя бы
один сервис прошёл frozen usable-cell rule, обе human/AI ячейки обоих сервисов
повторены до `n=3`. Всего включено 48 exact-SHA scans с transition signal.
Scores считаны из terminal DOM state; screenshot-capture отсутствует. Поэтому
результат годится для внутреннего выбора calibration scope, но имеет более
слабую evidence-доказательность и не используется как внешний accuracy claim.

| Pair | ZeroGPT human → AI | Scribbr human → AI | Same-SHA AI range | Класс |
|---|---:|---:|---:|---|
| arxiv-polish-03 | 0% → 25% | 0% → 6% | 0 / 0 п.п. | single-family diagnostic |
| arxiv-polish-04 | 0% → 0% | 0% → 0% | 0 / 0 п.п. | unusable floor |
| news-polish-03 | 17,5% → 22,3% | 0% → 0% | 0 / 0 п.п. | AI−human gap too small |
| news-polish-04 | 30,3% → 46,7% | 0% → 29% | 0 / 0 п.п. | stable cross-family |
| essay-b1-polish-02 | 26,3% → 100% | 0% → 100% | 0 / 0 п.п. | unusable ceiling |
| qa-polish-02 | 0% → 47,2/46,3/40,6% | 0% → 51% | 6,6 / 0 п.п. | cross-family, unstable |

Frozen selection формально выбрал `news-polish-04` и `qa-polish-02`, но общий
протокол заранее запрещает использовать same-SHA range больше `5 п.п.` для
admission. Валидатор поэтому отдельно вычисляет stable scope:
только `news-polish-04`. Подделка next-experiment scope, SHA, repeat policy или
transition signal отклоняется.

Практический вывод: впервые есть строгий EN-текст, где малое изменение можно
измерять одновременно в ZeroGPT и Scribbr без пола, потолка и видимого шума.
Это всё ещё не правило гуманизации и не detector accuracy claim. Следующий
однофакторный план должен быть опубликован до scores и сохранять factual
content, formal-news genre, current C2 envelope и source-as-reference style.
Полный результат:
[`baseline-scout-02-result.json`](baseline-scout-02-result.json).
