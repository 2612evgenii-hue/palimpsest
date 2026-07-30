# Первичные источники и рабочие выводы

Дата среза: 2026-07-30.

## GPTZero

- [GPTZero: Robust Detection of LLM-Generated Texts](https://arxiv.org/abs/2602.13042)
  описывает hierarchical multi-task deep-learning architecture и red teaming.
- [Официальное пояснение GPTZero](https://support.gptzero.me/articles/9585228410-how-do-i-interpret-burstiness-or-perplexity)
  прямо говорит, что с осени 2023 года perplexity и burstiness больше не
  используются для AI detection.

Вывод: старое правило «добавить burstiness» не может быть основанием для 4.0.
Коммерческий GPTZero нужно проверять как меняющийся classifier.

## Copyleaks

- [V10 testing methodology](https://copyleaks.com/ai-detector/testing-methodology)
  описывает отдельные human/AI наборы, API-тестирование, ROC-AUC, TPR/TNR и
  минимальную длину 350 символов.
- [How the detector works](https://copyleaks.com/ai-detector) перечисляет
  frequency ratios, parts of speech, syllable dispersion и hyphen usage.
- [AI Logic](https://copyleaks.com/ai-detector/ai-logic) добавляет AI Phrases и
  AI Source Match как отдельные сигналы.

Вывод: единичная замена синонима не обязана сдвигать многослойный результат.
Тестировать нужно полный документ, естественные операции и переносимость.

## Scribbr / QuillBot family

- [Официальное описание Scribbr](https://help.scribbr.com/hc/en-us/articles/39232894253719-How-does-the-AI-Detector-work)
  называет predictability, variation in sentence structure and length и
  категории AI-generated / AI-refined / human-written.

В live-интерфейсе 2026-07-30 Scribbr сообщил model `v7.1.0`. Это одна связанная
семья, а не независимый голос сверх QuillBot.

## Turnitin

- [Как читать AI Writing report](https://guides.turnitin.com/hc/en-us/articles/27139000787853-How-should-I-review-the-AI-Writing-report)
  предупреждает, что score не должен использоваться как самостоятельный
  окончательный вывод.
- [Product updates](https://guides.turnitin.com/hc/en-us/articles/29645383597965-Turnitin-product-updates)
  подтверждают обновляемость моделей и отдельное обнаружение AI-paraphrased /
  bypassed content.

Вывод: Turnitin важен как institutional reference, но без доступного
повторяемого режима не может быть live-сервисом Palimpsest по умолчанию.

## Независимые исследования

- [Are AI-Generated Text Detectors Robust to Adversarial Perturbations?](https://arxiv.org/abs/2406.01179)
  показывает уязвимость ряда detector families к небольшим word/character
  perturbations и отдельно подчёркивает cross-domain/cross-genre проблему.
- [Paraphrasing Attack Resilience of Various AI-Generated Text Detection Methods](https://arxiv.org/abs/2605.14240)
  показывает компромисс между исходной точностью и устойчивостью к paraphrase.
- [MAGE dataset](https://huggingface.co/datasets/yaful/MAGE) предоставляет
  multi-domain human/machine corpus; исследование фиксирует revision и SHA
  каждого используемого текста.

Вывод: perturbation, сработавшая один раз, является наблюдением о хрупкости,
а не профессиональным правилом редактирования. Для допуска нужны repeats,
human controls, independent groups и holdout.
