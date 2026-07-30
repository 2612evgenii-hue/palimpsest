# Changelog

## Research 4.0 — в работе, версия skill не повышена

- добавлена hash-pinned human/DeepSeek пара технического EN-текста;
- проведён `pilot-05`: human controls, три baseline repeats, десять
  однофакторных правок и progressive ceiling/cliff probe;
- при edit cost до 7,32% ZeroGPT и Scribbr остались на насыщенных 100%;
- human control получил 38% в ZeroGPT, 0% в Scribbr и 99,1% в Sapling;
- Copyleaks зафиксирован как `blocked`, без подстановки выдуманного score;
- правило в production-skill не допущено: четыре объединённые правки уже
  нарушали C1-envelope, а измеримого detector response не появилось;
- research builder поддерживает несколько точных hash-bound replacements в
  одном прогрессивном кандидате;
- добавлен preregistered PubMed holdout: confirmatory split отклонён на обоих
  текстах из-за source-relative C2 drift до detector scan;
- добавлен preregistered baseline scout на пяти EN-парах: два AI-polish текста
  выбраны только как несатурированные ZeroGPT-мишени, а Scribbr на тех же SHA
  расходится до противоположных `100%` и `0%`;
- новый `research_scout.py` заново вычисляет frozen selection, repeat policy,
  SHA binding и отклоняет подделанное решение scout;
- завершён preregistered `micro-01`: шесть source-preserving EN-правок на двух
  AI-polish текстах, первичный screen и обязательные повторы;
- `direct_subject_restoration` и `direct_claim_restoration` формально прошли
  calibration screen ZeroGPT, но не допущены в skill: Scribbr не дал
  подтверждающего движения, а одна same-SHA ячейка ZeroGPT имела диапазон
  `0–76,2%`;
- новый `research_micro.py` проверяет preregistration/commit binding, SHA
  кандидатов, frozen repeat policy, Copyleaks scope и заново вычисляет эффекты;
- Copyleaks micro-диагностика снова записана как `scan_limit_reached`, без
  выдуманного score;
- завершён transition-bound `holdout-02` на двух новых строгих EN-текстах:
  перенос `direct_claim_restoration` отвергнут (`0/2`);
- на formal-news human control и AI baseline получили одинаковые `41,6%`
  ZeroGPT, а кандидат — `41,7%`; scientific ZeroGPT baseline оказался на полу;
- новый `research_holdout.py` заново проверяет preregistration/commit binding,
  exact-SHA матрицу, три повтора, transition signals, technical exclusions и
  вычисляет verdict, не доверяя заявленному analysis;
- production skill прямо запрещает использовать «сделать claim прямее» как
  detector-рецепт; это допустимо только по смысловой/редакторской причине;
- завершён `baseline-scout-02` на шести новых
  AI-polish/human EN-парах, из которых четыре относятся к строгому
  scientific/formal-news письму;
- стабильное cross-family окно найдено на `news-polish-04`: ZeroGPT
  human/AI `30,3/46,7%`, Scribbr `0/29%`, все повторы без шума;
- technical pair исключён из следующего scope из-за ZeroGPT same-SHA range
  `6,6 п.п.`, хотя первичный двухсервисный baseline прошёл;
- scout v2 требует transition signal, повторяет полную двухсервисную матрицу,
  заново вычисляет стабильный scope и отклоняет его подделку;
- до новых scores заморожен `micro-02` на стабильном formal-news окне: восемь
  source-grounded факторов с edit cost `0,188–6,61%`, один заранее исключён
  quality-first style screen;
- micro v2 требует свежие human/AI start controls, transition-bound evidence,
  эффект больше `2 п.п.`, cross-family success после `n=3` и автоматически
  выбирает самый дешёвый полный успех;
- завершён live `micro-02`: 34 exact-SHA scans, стабильные start controls и
  два cross-family успеха; минимальный `f7-quote-date` (`0,188%`) дал ZeroGPT
  `46,7→39%`, Scribbr `29→15%`, оба range `0`;
- более глубокое восстановление цитаты (`6,61%`) дало `38,1%/15%` и проиграло
  минимальному кандидату; другой date-removal повысил ZeroGPT до `71,3%`,
  поэтому общий date-removal factor отклонён;
- до новых scores заморожен `holdout-03` на трёх untouched formal-news парах:
  только exact source quote restoration, edit cost `3,97–7,26%`, C2 и
  source/plan/candidate SHA binding;
- confirmatory scope holdout-03 использует ZeroGPT + Copyleaks, Scribbr как
  guardrail и Sapling только как human-controlled diagnostic; registry group,
  guest access и repeat policy проверяются отдельным prereg validator;
- partial run holdout-03 отклонил перенос `quote_integrity_restoration` во всех
  трёх ZeroGPT ячейках (`100→100`, `49,8→51,5`, `50→50,5`); Copyleaks был
  blocked на guest scan limit, поэтому multi-service holdout не объявлен
  завершённым, а потерянные timestamps/captures не были восстановлены;
- `research_holdout.py --partial-result` заново проверяет exact-SHA ZeroGPT
  slice, frozen repeats, blocked Copyleaks attempt, evidence limitations и
  отрицательный verdict;
- Copyleaks переклассифицирован из безусловно repeatable в
  `guest_quota_sensitive`; стартовый список теперь явно называется
  no-account candidate profile и всегда требует live capability review;
- добавлен privacy-first `shadow_case.py` для реальной работы: default
  `delivery_only`, отдельное consent для private aggregate research,
  digest-freeze кандидатов до scores, terminal exact-SHA observations и
  complete-case Pareto;
- один real-work case не допускает detector-рецепт; raw client text, captures
  и shadow JSON запрещено коммитить;
- variant builder связывает editorial justification с exact reference SHA,
  буквальным source excerpt и заранее вычисленным candidate SHA;
- исправлен false positive fidelity screen: союз после года (`1919 but`) больше
  не принимается за единицу измерения, при этом известные unit changes остаются
  hard findings;
- skill запрещает blanket split/merge по vendor-подсказке и требует
  quality-first screening до live recheck;
- полный selftest расширен новыми holdout/scout/anti-forgery слоями.

## 3.5.0 — 2026-07-30

Версия возвращена к исходному пользовательскому контракту F1.

### Добавлено

- явный `score_mandatory` по умолчанию с F1;
- hard pass `every mandatory score <20%`, target `<15%`;
- repeatable no-sign-up EN core: ZeroGPT, Scribbr, GPTinf, Copyleaks;
- исходный профиль ZeroGPT, GPTZero, Scribbr, QuillBot, GPTinf, Copyleaks как
  явная Q3-опция;
- digest-bound `detector_round` с полной score matrix и highlight map;
- durable GOAL с функциями, стилем, English level и detector scope;
- F1 auto-longform от 1,000 слов и полный service×target coverage;
- тесты strict boundary, recheck-after-edit, blocked service, no sampling и
  plateau blocker.
- воспроизводимый live EN forward edit-cycle: 63,1/100/100/100% →
  5,3/0/0/0% на repeatable core.

### Изменено

- ровно 20% теперь fail;
- plateau `>=20%` остаётся red/open и не создаёт success with limits;
- local waiver запрещён в `score_mandatory`;
- `detector-policy --services` не может локально сузить mandatory scope:
  требуется новый explicit Q3 intake;
- `risk_sampled` запрещён в F1;
- каждая substantive edit требует полного повторного detector pass;
- final detector round обязан быть зарегистрирован после F2/F3/F4;
- F1 default edit budget расширен до 0.30/0.60, fidelity сохранён;
- добавлен evidence-bound `edit-budget` с историей и верхней границей 0.85;
- GPTZero и QuillBot вынесены из no-sign-up default после live sign-up limits,
  но сохранены в registry и original-six profile;
- explicit English level теперь авторитетнее noisy source estimate;
- exact semantic review может снять только lexical
  `CLAIM_DROPPED`/`CLAIM_ADDED`, но не hard fidelity codes;
- `authorized_change` теперь оставляет G7 red до нового immutable baseline;
- Q1–Q4 блокируются после завершения intake: F1 и detector scope нельзя
  локально переписать после неудачного результата;
- browser evidence проходит структурную проверку PNG/JPEG/WebP/PDF и
  минимального размера screenshot;
- README, SKILL и references переписаны под check→mark→edit→recheck.

### Сохранено

- challenge/raw capture binding;
- immutable original, language anti-forge и registry integrity;
- semantic source-unit mapping и fail-closed authorized-change provenance;
- fidelity, minimality, style и English-level screens;
- anti-overlap, long-form sync, bounded memory;
- запрет force-close и fake accept-limits.

## 3.2.0 — 2026-07-30

- Challenge-bound detector evidence и hardened capability registry.
- Source-as-reference, English-level preservation и explicit detector Q3.
- Broad regression, adversarial acceptance и 15k+ word stress.
