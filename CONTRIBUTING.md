# Участие в разработке

Спасибо за интерес к Palimpsest.

## Принцип

Исправление должно устранять воспроизводимую проблему, а не увеличивать
количество декларативных проверок.

## Перед pull request

1. Создайте issue или опишите failing case в PR.
2. Добавьте regression test, который падает до исправления.
3. Внесите минимальное изменение.
4. Выполните:

```bash
python3 -m compileall -q scripts evals
python3 evals/selftest.py
```

5. Обновите README, reference или changelog, если контракт изменился.

## Требования к PR

- не смешивать независимые изменения;
- не добавлять paid/login-only сервис в default core;
- не заявлять detector accuracy без общего корпуса и raw results;
- не ослаблять semantic, fidelity и immutable-source gates ради score;
- не добавлять «humanization tricks» вроде homoglyphs и намеренных ошибок;
- явно описывать false positives и trust boundary.

## Стиль кода

- Python 3.10+;
- stdlib-first;
- deterministic output;
- понятные return codes;
- SHA-bound evidence;
- тесты без сетевой зависимости.
