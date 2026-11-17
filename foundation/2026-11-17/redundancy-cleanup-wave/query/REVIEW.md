# Независимый review: query classifier

**ACCEPT.** Проверен точный `modules-query-classifier.patch`, SHA-256
`7cd6be0a178f236c0cfa66162370ed55900701b0f5a155cea1ae4e3d73690da9`,
против Modules `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7`.

## Эквивалентность

- Tokenizer допускает только ASCII alphanumeric, `_` и `-`; точки уже
  являются разделителями. Четыре suffix-проверки недостижимы для любого token.
- Все 23 entries allowlist (22 уникальных; `module` повторён) состоят из
  lowercase ASCII, имеют длину не менее четырёх и отсутствуют в stopwords.
  Поэтому lowercase spellings уже принимает общий predicate, а spellings
  с uppercase принимает code-like predicate. Allowlist не расширяет результат.
- Numeric-only early rejection сохранён: он логически необязателен для
  acceptance, но может экономить последующие scans. Length threshold,
  stopwords, trim, case-insensitive dedup, исходное spelling/order,
  максимум четырёх queries и fallback до 80 Unicode scalar values не менялись.
- `retrieval.rs` и все callers не меняются. Это не новый tokenizer, не
  изменение query quality и не SQLite query patch. Process/security/HOLD
  области, API, manifests и pinned Core `185225a...` не затронуты.

## Тесты и независимая проверка

Все три исходных assertions сохранены; добавлены девять behavioral cases
внутри тех же трёх existing tests, без новых test methods. Проверяются
наблюдаемые queries, не наличие/расположение implementation checks.
Filter `--lib tests::extract_search_queries_` выбирает только эти чистые
функции, без process/HTTP/filesystem вызовов из tests.

Авторские expanded-baseline и candidate logs дают 3/3 PASS. Reviewer отдельно
выполнил `python3 scripts/test.py -p context-pack --lib
tests::extract_search_queries_ --offline`: exit 0, 3 passed, 0 failed,
0 ignored, 20 filtered. Это повторная проверка тех же трёх methods, не три
дополнительных уникальных теста. Полный log сохранён локально как
`independent-repeat.log`.

Независимо проверены diff, unchanged dependency/runner files, exact patch
application к baseline, совпадение candidate bytes и полное reverse
восстановление. Source diff: production −31 LOC, с +28 test LOC общий −3.

Полный context-pack/workspace gate, real retrieval/provider/process,
portable/packaging, hosted CI и benchmarks не запускались. Ускорение не
измерено. Reviewer не менял исходники и ничего не публиковал.
