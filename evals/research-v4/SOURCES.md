# Первичные источники и рабочие выводы

Дата среза: 2026-07-30.

## ZeroGPT

- [Публичная страница ZeroGPT](https://www.zerogpt.com/) описывает
  DeepAnalyse™ как многоэтапную deep-learning методологию от macro- к
  micro-level, обученную на интернет-текстах, educational datasets и
  proprietary synthetic data. Точные признаки, версия модели и benchmark
  protocol на странице не раскрыты.

Вывод: подсветка предложений показывает вклад по мнению black-box сервиса, но
не раскрывает причинный edit rule. В pilot-05 ZeroGPT пометил все 11
предложений, а восемь разных микроправок сохранили 100%; на таком потолке
highlight нельзя использовать как локальный навигатор.

## GPTZero

- [GPTZero: Robust Detection of LLM-Generated Texts](https://arxiv.org/abs/2602.13042)
  описывает hierarchical multi-task deep-learning architecture и red teaming.
- [Официальное пояснение GPTZero](https://support.gptzero.me/articles/9585228410-how-do-i-interpret-burstiness-or-perplexity)
  прямо говорит, что с осени 2023 года perplexity и burstiness больше не
  используются для AI detection.
- [Технологическая страница GPTZero](https://gptzero.me/technology) описывает
  mixed classification и Advanced Scan, который ранжирует вклад участков
  документа, но не утверждает, что локальная правка подсветки причинно снизит
  итоговый score.

Вывод: старое правило «добавить burstiness» не может быть основанием для 4.0.
Коммерческий GPTZero нужно проверять как меняющийся classifier.

## Copyleaks

- [V10 testing methodology](https://copyleaks.com/ai-detector/testing-methodology)
  описывает отдельные human/AI наборы, API-тестирование, ROC-AUC, TPR/TNR и
  минимальную длину 350 символов. Методология также публикует три sensitivity
  levels; extra-sensitive режим заявлен специально для текстов после
  humanizer/text spinner.
- [How the detector works](https://copyleaks.com/ai-detector) перечисляет
  frequency ratios, parts of speech, syllable dispersion и hyphen usage.
- [AI Logic](https://copyleaks.com/ai-detector/ai-logic) добавляет AI Phrases и
  AI Source Match как отдельные сигналы.

Вывод: единичная замена синонима не обязана сдвигать многослойный результат.
Тестировать нужно полный документ, естественные операции и переносимость.
Публичные vendor benchmarks нельзя переносить на наш UI-run: они получены
через API на закрытых наборах и не раскрывают score каждого текста.

## Scribbr / QuillBot family

- [Официальное описание Scribbr](https://help.scribbr.com/hc/en-us/articles/39232894253719-How-does-the-AI-Detector-work)
  называет predictability, variation in sentence structure and length и
  категории AI-generated / AI-refined / human-written; страница отдельно
  предупреждает, что результат не является стопроцентной гарантией.

В live-интерфейсе 2026-07-30 Scribbr сообщил model `v7.1.0`. Это одна связанная
семья, а не независимый голос сверх QuillBot.

## Sapling

- [Официальный AI Detector](https://sapling.ai/ai-content-detector) описывает
  Transformer token probabilities, отдельные sentence perplexity scores,
  guest limit 2000 символов и прямо предупреждает о false positives.

Вывод: Sapling полезен как дополнительная research-family для коротких EN
текстов, но human control обязателен. В pilot-03 он дал 100% на человеческом
scientific abstract, а в pilot-05 — 99,1% на человеческом technical control.
В holdout-01 ещё два человеческих PubMed-текста получили 96,4% и 100%.
Поэтому единичный Sapling score нельзя трактовать как авторство, а
vendor-оценка общего false-positive rate не заменяет жанровый контроль.

## Turnitin

- [Как читать AI Writing report](https://guides.turnitin.com/hc/en-us/articles/27139000787853-How-should-I-review-the-AI-Writing-report)
  предупреждает, что score не должен использоваться как самостоятельный
  окончательный вывод.
- [Using the AI Writing Report](https://guides.turnitin.com/hc/en-us/articles/22774058814093-AI-writing-detection-in-the-new-enhanced-Similarity-Report)
  требует минимум 300 слов qualifying prose и скрывает точные значения 1–19%,
  потому что в этом диапазоне выше риск false positives.
- [Product updates](https://guides.turnitin.com/hc/en-us/articles/29645383597965-Turnitin-product-updates)
  подтверждают обновляемость моделей и отдельное обнаружение AI-paraphrased /
  bypassed content.

Вывод: Turnitin важен как institutional reference, но без доступного
повторяемого режима не может быть live-сервисом Palimpsest по умолчанию.
Короткие пилоты на 100–200 слов также нельзя выдавать за proxy для Turnitin:
они не проходят его опубликованный minimum-length contract.

## Независимые исследования

- [Are AI-Generated Text Detectors Robust to Adversarial Perturbations?](https://arxiv.org/abs/2406.01179)
  показывает уязвимость ряда detector families к небольшим word/character
  perturbations и отдельно подчёркивает cross-domain/cross-genre проблему.
- [Paraphrasing Attack Resilience of Various AI-Generated Text Detection Methods](https://arxiv.org/abs/2605.14240)
  показывает компромисс между исходной точностью и устойчивостью к paraphrase.
- [MAGE dataset](https://huggingface.co/datasets/yaful/MAGE) предоставляет
  multi-domain human/machine corpus; исследование фиксирует revision и SHA
  каждого используемого текста.
- [AIGC-text-bank](https://huggingface.co/datasets/bmbgsj/AIGC-text-bank)
  предоставляет связанные human/AI версии разных жанров и метаданные
  non-native essays, а также отдельный AI-polish subset. Исследование использует
  pinned DeepSeek JSONL revision
  `38d3e0e23fc9997d26929f1fecf9b46eeae567be`, exact row id и SHA каждого поля;
  лицензия источника — CC BY-NC-SA 4.0. Upstream SHA сохраняется отдельно от
  канонической plain-text формы, чтобы транспортные trailing spaces не
  становились частью detector-эксперимента.

Вывод: perturbation, сработавшая один раз, является наблюдением о хрупкости,
а не профессиональным правилом редактирования. Для допуска нужны repeats,
human controls, independent groups и holdout.

В baseline-scout-01 AI-polish рассматривается как отдельный режим реального
совместного письма, а не как заранее успешная «гуманизация». Один найденный
B2 AI-polish-кандидат был исключён до detector scores: upstream metadata
указывала B2, но локальный source-relative screen оценил переход B2 → C2.
В scout включён другой AI-native essay, у которого исходная и AI-версии обе
остаются в измеряемой полосе B2.

Holdout-02 использует отдельный hash-bound manifest, чтобы не изменять уже
замороженный `corpus-manifest.json`. До live scores выбраны две ранее
непроверенные строки AI-polish subset: `arxiv_001213` и `news_004384`.
Критерии выбора были содержательными, а не detector-facing: строгий научный
abstract и formal news, полный связанный human source, достаточная длина и
возможность одной source-supported meaning-equivalent правки. Upstream
revision остаётся тем же pinned commit; SHA human/AI полей и canonical form
записаны в `holdout-02-corpus-manifest.json`.

Baseline-scout-02 также использует отдельный supplemental manifest и шесть
ранее не сканированных строк того же pinned AI-polish revision:
`arxiv_008467`, `arxiv_003842`, `news_002334`, `news_003652`,
`essay_nonnative_002622` и `qa_007837`. Четыре первых образца дают основной
строгий scientific/formal-news слой; learner essay с upstream B1 metadata и
technical explanation проверяют жанровую переносимость измерительного окна.
Все human/AI поля и canonical forms связаны SHA до первого detector score.
Scout отбирает не «лучшие тексты», а только те, где обе доступные независимые
семьи способны измерять локальное изменение без пола/потолка и с наблюдаемым
разрывом AI−human.

В завершённом scout-02 стабильное окно найдено только на formal-news паре
`news_003652`: ZeroGPT human/AI `30,3/46,7%`, Scribbr `0/29%`, повторные
same-SHA scores не менялись. Technical pair `qa_007837` не допущен к
редактированию из-за диапазона ZeroGPT `6,6 п.п.`. Все 48 включённых
наблюдений имеют exact-SHA и transition signal, но не screenshot-capture;
это ограничивает результат ролью калибровки.
