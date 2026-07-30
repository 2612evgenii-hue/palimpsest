# Ограничения и модель доверия v3.5

## Что проверяется машинно

- immutable original SHA и current working SHA;
- source language binding;
- current service×target detector matrix;
- strict `<20%` и soft `<15%`;
- полнота detector round и highlight coverage;
- staleness после правки;
- порядок final round после F2/F3/F4;
- fidelity anomalies, edit ratio, style/CEFR drift;
- segment coverage, overlap и source-unit reconciliation;
- registry facts, observation и raw-capture hashes.

## Что не доказывается

### Авторство

Ни один AI-detектор не доказывает, кто написал текст. Palimpsest добивается
пользовательского порога на текущем выбранном наборе, но не называет score
доказательством.

### Будущие результаты

Сервисы, модели, доступ, лимиты и scores меняются. Релиз не гарантирует
необнаружимость будущими версиями.

### Подлинность screenshot

Challenge связывает capture с текущей задачей и обнаруживает изменение файла.
Валидатор отклоняет повреждённые и фиктивные контейнеры, включая «PNG header +
случайные байты», а также слишком маленькие screenshot. Это не OCR и не
подписанный vendor receipt: мотивированный локальный агент всё ещё может
создать правдоподобное поддельное изображение.

### Согласие пользователя

Локальный JSON не аутентифицирует цитату. Поэтому blocked mandatory service
нельзя снять `waive`; реальный пользователь должен изменить Q3 scope.

### Точный CEFR и полный голос

Readability/style metrics — экраны drift. Короткие тексты шумны, поэтому style
screen использует более широкий, но всё равно блокирующий ceiling (а не
автоматический pass). Нужна side-by-side редакторская проверка. Явно выбранный
пользователем уровень авторитетнее автоматической source estimate;
`infer_from_source` сохраняет строгий source-relative envelope.

### Shadow-case и согласие на research

`shadow_case.py` связывает план digest и хранит SHA цитаты согласия, но не
аутентифицирует человека и не расширяет его права на чужой текст. Поэтому
default — `delivery_only`; raw project text, candidates, captures и case JSON
остаются локальными и не коммитятся. Один consented case не доказывает перенос
правила.

### Guest-доступ

No-account profile — стартовый список, не SLA. Например, Copyleaks ранее
возвращал guest results, а затем показал `scan limit reached` без score.
Capability review обязателен для каждой работы; blocked не интерпретируется
как процент.

### Population accuracy

Имеющийся EN pilot и один успешный forward edit-cycle не являются population
benchmark. Они доказывают работоспособность процесса на конкретном образце, а
не гарантируют любой будущий текст. RU corpus остаётся provisional. Registry
фиксирует наблюдения, а не вечный рейтинг сервисов.

## Поведение при несовместимых целях

Если `<20%` нельзя достигнуть без потери смысла, фактов или обязательного
почерка:

1. зарегистрировать materially different attempts и plateau;
2. показать scores, изменения и fidelity findings;
3. оставить F1 open;
4. запросить у пользователя изменение scope/F1 либо продолжить новой
   смыслобезопасной гипотезой.

Plateau не является успехом.

## Этическая граница

Нельзя использовать skill для скрытия плагиата, фабрикации evidence, удаления
обязательных citations, нарушения правил учебного заведения или искусственной
порчи текста. F4 требует оригинального выражения и корректной атрибуции.
