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
- полный selftest расширен до 114 тестов.

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
