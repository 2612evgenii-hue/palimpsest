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

Текущие claims должны опираться на `pilot-03-canonical.json`, а не на эту
таблицу.

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
