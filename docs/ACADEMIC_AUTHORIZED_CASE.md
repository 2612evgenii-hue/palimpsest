# Авторизованный academic long-form case

Это анонимизированный delivery-case, а не population benchmark и не
production-рецепт обхода детекторов. Исходник, кандидат, разрешение, captures
и document SHA остаются в приватном workspace и не публикуются.

## Условия

- formal EN dissertation draft;
- `source_as_reference`;
- 6 297 слов в исходнике, 146 Word paragraphs;
- разрешение представлено пользователем и сохранено как
  `user_supplied_unverified_external_document`;
- цель — наименьший meaning-safe diff при full editable-prose coverage;
- библиография exact-mapped, но защищена от detector-driven rewrite.

## Результат

Правка затронула 37 из 146 абзацев; word change ratio — `19,53%`, объём
изменился на `6 297 → 6 284` слов (`−0,2%`).

| Prose target | Words | ZeroGPT | Scribbr | GPTinf |
|---|---:|---:|---:|---:|
| P001 | 911 | 19,0% | 4% | 4% |
| P002 | 904 | 18,6% | 0% | 5% |
| P003 | 905 | 18,7% | 8% | 0% |
| P004 | 904 | 10,7% | 13% | 0% |
| P005 | 1 060 | 11,9% | 4% | 4% |

Все доступные сервисы дали strict `<20%` на каждом prose target. Soft target
`<15%` не достигнут в ZeroGPT. Copyleaks остановился на guest scan limit и
остаётся blocker для исходного four-service scope; его score не придуман и не
заменён другим сервисом.

## Quality evidence

- 54 reference entries сохранены точно;
- multiset из 80 in-text citation occurrences совпал;
- все 112 numeric tokens совпали;
- 146 paragraphs, sections, tables, inline shapes и Word styles сохранены;
- average sentence length: `19,88 → 19,37`;
- estimated Flesch–Kincaid grade: `15,89 → 15,19`.

## Что case изменил в skill

1. `minimality.py` больше не схлопывает DOCX extraction с одиночными переносами
   в один фиктивный paragraph.
2. `segment.py` ставит hard boundary перед `REFERENCES`, сохраняет 100%
   character coverage и маркирует bibliography как protected non-prose.
   Tiny tail ниже `--min` объединяется в пределах 1 200-word public limit,
   поэтому неизменённый 147-word остаток не превращается в шумный отдельный
   target.
3. `state.py` считает `full` как все detector-eligible prose targets; отчёт
   обязан говорить **full prose coverage**, а не whole-file pass.
4. Academic F1 доступен только через digest-bound
   `academic_authorized_ai_revision`; permission artifact не выдаётся за
   независимо аутентифицированный.

Машиночитаемая сводка:
[`academic-authorized-case-anonymized.json`](../evals/research-v4/academic-authorized-case-anonymized.json).
