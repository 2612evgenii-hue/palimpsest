# Ограничения и модель доверия

## Что Palimpsest действительно проверяет

- актуальность file digests;
- неизменность original относительно init SHA;
- deterministic fidelity anomalies;
- edit ratio;
- целостность сегментной карты;
- registry facts и independence groups;
- наличие и SHA detector captures;
- полноту source-unit reconciliation;
- измеримый English/style drift в заявленных границах.

## Что он не может доказать

### Авторство текста

Ни ZeroGPT, ни Copyleaks, ни любой другой detector не доказывает, кто написал
текст. Score — только сигнал конкретной версии сервиса.

### Подлинность screenshot

Challenge-bound capture можно проверить на актуальность и неизменность, но
мотивированный локальный агент способен создать поддельное изображение.

### Личность автора согласия

Строка с quote или message ID в локальном JSON не аутентифицирует пользователя.
Поэтому yellow gates не закрываются через CLI, а `authorized_change` остаётся
yellow.

### Точный CEFR

Readability и lexical/syntactic signals не заменяют сертифицированную оценку.
Screen ищет drift относительно source, а не выдаёт диплом уровня.

### Полное совпадение голоса

Style metrics измеряют отдельные признаки. Короткие samples слишком шумны для
числового threshold и остаются advisory.

### Population accuracy detector core

Текущий EN pilot 3+3 подходит для выявления грубых провалов, но не для оценки
точности на популяции. RU workflow provisional.

## Этическая граница

Skill нельзя использовать для:

- скрытия плагиата;
- фабрикации авторства или evidence;
- удаления обязательных citations;
- намеренной порчи текста ради прохождения detector;
- обхода правил учебного заведения.

Palimpsest помогает редактировать текст качественно и прозрачно, а не
подделывать происхождение.
