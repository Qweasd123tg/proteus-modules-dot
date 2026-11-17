# Один classifier поисковых слов вместо поглощённых проверок

Узкий Modules proposal от 2026-11-17. [Patch](modules-query-classifier.patch)
и [независимый review](REVIEW.md). **Upstream production не изменён.**

## Упрощение и сохранённый контракт

`context/context-pack/src/search_queries.rs` содержит две лишние группы условий:

1. Все 23 entries `REPO_SEARCH_ALLOWLIST` (22 уникальных слова) уже проходят
   общий predicate: ASCII lowercase, длина ≥4, не stopword. Если исходное
   написание содержит uppercase, его уже принимает code-like predicate.
   Словарь не добавляет ни одного допустимого query и удалён целиком.
2. Четыре `ends_with` для `.rs`, `.toml`, `.md`, `.json` всегда false:
   tokenizer ещё до этих проверок делит строку по точке.

Это не security allowlist, а эвристика выбора слов для repo search.
Сохранены tokenizer, short-token и numeric-only ранние отказы, stopwords,
case-insensitive dedup, первое написание и порядок, лимит четырёх queries,
trim и fallback до 80 Unicode scalar values. Numeric-only guard логически
не обязателен, но может экономить последующие scans; его не удаляли.

Файлы по-прежнему разбиваются как раньше: `Parser.rs` → `Parser`,
`config.toml` → `config`, `toml`. Это не новая семантика поиска и не исправление
качества retrieval. Provider, byte budgets, storage, API и callers не меняются.

Production −31 строка. В трёх существующих тестах сохранены все исходные
assertions и добавлены девять наблюдаемых behavioral cases (+28 строк).
Итого −3 строки, без новых test methods, suites, framework или проверок текста
исходников. Выигрыш здесь в одной реализации классификации, не в числе PR.
Замеренного ускорения/снижения памяти нет.

## Базы, дедупликация и реальные проверки

- Modules: `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7`.
- Фактический Core pin: `185225a7103088c444788374ca425d230060f55a`.
- Свежий Core main: `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`, не тестируемый pin.
- Delivery при дедупликации: `99b88e2dd2be8d38a2d407756cfd903ed49de990`.
- Patch SHA-256: `7cd6be0a178f236c0cfa66162370ed55900701b0f5a155cea1ae4e3d73690da9`.

PR165/166 и позднейшие опубликованные patches не содержат этого cut.
SQLite tokenization и typed-memory HOLD не переоткрывались. Два независимых
исследования нашли один и тот же кандидат и объединены, не опубликованы копиями.

Rust/Cargo 1.95.0, штатный runner, без overlays и изменений Cargo.toml/lock:

```sh
python3 scripts/test.py -p context-pack --lib tests::extract_search_queries_ --offline
rustfmt --check --edition 2024 --config skip_children=true context/context-pack/src/search_queries.rs context/context-pack/src/tests.rs
```

Pristine baseline: **3/3 PASS**. Сначала расширены существующие тесты:
expanded baseline **3/3 PASS**, затем удалены лишние условия: **3/3 PASS**.
Независимый повтор exact candidate: **3/3 PASS**. В каждом запуске 20 других
тестов отфильтрованы; повторные запуски не являются новым уникальным покрытием.
Проверены domain words, file-like punctuation, code identifiers, short/numeric
tokens, stopwords/fallback, пустой ввод, Unicode limit, dedup, spelling и cap.
Changed-file rustfmt, diff check, exact apply/reverse: PASS.

**NOT RUN:** весь context-pack/workspace, реальные retrieval/provider,
filesystem/git/process/security fixtures, portable/packaging/install, hosted CI
и benchmarks. Скомпилированный lib test target не означает исполнение остальных
fixtures. Публикация в dot хранит кандидат и evidence, не интегрирует upstream.
