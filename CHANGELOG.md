# Changelog

## 3.5.0 — 2026-07-30

Версия возвращена к исходному пользовательскому контракту F1.

### Добавлено

- явный `score_mandatory` по умолчанию с F1;
- hard pass `every mandatory score <20%`, target `<15%`;
- стартовый набор ZeroGPT, GPTZero, Scribbr, QuillBot, GPTinf, Copyleaks;
- digest-bound `detector_round` с полной score matrix и highlight map;
- durable GOAL с функциями, стилем, English level и detector scope;
- F1 auto-longform от 1,000 слов и полный service×target coverage;
- тесты strict boundary, recheck-after-edit, blocked service, no sampling и
  plateau blocker.
- воспроизводимый live EN smoke-report для полного набора из шести сервисов.

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
- browser evidence проходит структурную проверку PNG/JPEG/WebP/PDF и
  минимального размера screenshot;
- README, SKILL и references переписаны под check→mark→edit→recheck.

### Сохранено

- challenge/raw capture binding;
- immutable original, language anti-forge и registry integrity;
- semantic source-unit mapping и authorized-change hardening;
- fidelity, minimality, style и English-level screens;
- anti-overlap, long-form sync, bounded memory;
- запрет force-close и fake accept-limits.

## 3.2.0 — 2026-07-30

- Challenge-bound detector evidence и hardened capability registry.
- Source-as-reference, English-level preservation и explicit detector Q3.
- Broad regression, adversarial acceptance и 15k+ word stress.
