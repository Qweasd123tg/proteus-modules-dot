# Независимый exact review: SQLite literal query spans

## Verdict

Source-level blocker в exact candidate не найден. Исправление C2 обосновано общей boundary query→FTS: tool и context provider используют один store.recall→recall_impl→fts_match_expression. Нового Rust tokenizer/framework/migration нет. Это не compile/test/runtime PASS.

## Semantics и intentional changes

Остаётся split_whitespace и AND между принятыми spans. Новый any(alphanumeric/_/-) filter логически эквивалентен прежнему условию nonempty после char deletion, но оставляет исходный span для tokenizer. Поэтому punctuation-only/quote-only/NUL-only запросы сохраняют empty-expression recent fallback; отдельные '-'/'_' по-прежнему не фильтруются и остаются пустыми FTS phrases. Это legacy поведение, не обещание полезного поиска по самим знакам.

Punctuation больше не склеивает соседние слова: src/config.rs передаётся как quoted phrase, а не srcconfigrs. Старая joined-token matching намеренно изменена. Prefix относится только к последнему токену span; внутри phrase требуется последовательность/соседство, а не набор независимых слов. Сохранение underscore/hyphen в старом коде уже делегировало аналогичные compound phrases SQLite. Newline/tab/Unicode whitespace по-прежнему разделяются Rust split_whitespace; это не произвольный FTS query-language interface.

Embedded quote удваивается, NUL заменяется пробелом внутри span. NUL не поддерживается буквально: выбран separator без склеивания слов. Это устраняет найденный design blocker raw quoting, где parser видел конец строки до closing quote. Combining marks больше не удаляются Rust-filter и передаются tokenizer. Не заявляется универсальное Unicode equivalence или поддержка custom tokenizer: scope — существующая default schema.

SQLite docs подтверждают quoted-string escaping, tokenizer-driven phrases и prefix последнего токена. [FTS5 query syntax](https://sqlite.org/fts5.html#full_text_query_syntax). Проверенный parser fts5ExprGetToken рассматривает input как NUL-terminated и внутри quoted string выдаёт unterminated-string error на NUL. [SQLite parser source](https://raw.githubusercontent.com/sqlite/sqlite/master/ext/fts5/fts5_expr.c). Это primary-source reasoning, не выполнение linked bundled engine.

## Caller/docs scope

Provider и tool вызывают общий typed store.recall; query.limit==0 ранний return, empty-expression id DESC fallback, params binding, ORDER BY rank, SQL limits и schema не изменены. «Ранжирование не меняется» в docs следует читать как unchanged ranking algorithm/ORDER BY, не прежние scores, порядок или набор результатов при изменившемся query. Literal FTS-фраза не означает exact punctuation/string matching, что docs прямо объясняют.

## Compile-shape и proposed tests

Inline `mod tests { mod recall; }` в src/lib.rs корректно направляет в src/tests/recall.rs. Child использует super::* для private fresh_conn, Mutex/Connection, remember_impl/recall_impl и MemoryItem; existing tests уже используют тот же in-memory schema. Test fixtures задают kind/content/metadata и text/limit в прежнем DTO shape. Новые dependencies не требуются по source.

Прочитаны шесть новых tests и один обновлённый assertion. Они предлагают проверить punctuation против joined distractors; last-token prefix/adjacency; whitespace AND и старые compounds; combining mark; NUL separator; recent fallback и '-'/'_' пустые phrases. Результаты с несколькими ranking candidates явно sort-ятся, fallback использует deterministic id DESC. Test combining mark проверяет self-match, а не полную Unicode normalization equivalence. В proposed source не найдено обязательного дополнительного test blocker.

Tests не запускались. SQL assertions остаются непроверенными на bundled SQLite; нет ToolModule/process integration, custom tokenizer/preexisting altered-schema coverage или exhaustive Unicode corpus. Primary source docs не заменяют compilation/runtime verification конкретного build.

## Exact hashes и ограничения

Все четыре SHA256 независимо пересчитаны и совпали:
- patch: 333558ca5742e39adeeb10347c8382dce78c0ff14cbe6b3e455cd48b9bd00a95
- lib.rs: 354eda439aa308e8725af95a7ef8ddeb6d349c2375601ee9cce6dfe544f135b7
- tests/recall.rs: 42ad1d36853861e0d776fc171ad75b375b08cbde93f5f7066789c980a233d379
- docs/reference.md: 4c250f915d90a2837e4636f3284ab03ff3f4aaaa09ba5f4fed84ad7e9cb35c93

Coordinator сообщает 14 verified Modules blobs и text apply-check. Baseline Modules c035142558f0fca43e9772fc0e50ca293abf1531. Reviewer прочитал exact diff/caller references/current schema и upstream documentation/parser, не повторял весь catalog verification.

Rust/compiler/formatter/tests/runtime/SQL execution/project scripts/install не запускались. Production, refs и публикации не менялись. Performance не измерялся; новый functional incident не заявляется.

## Addendum: later authorized Python representation probe

После исходного source-only review coordinator сообщил разрешённый bounded Python sqlite3 probe. Предыдущие утверждения «runtime/SQL execution не запускались» описывают раннюю стадию и действия reviewer, а не этот последующий coordinator run.

Независимо прочитаны весь python_fts5_probe.py, сохранённые 27 cases в PYTHON-FTS5-RESULTS.json и обновлённый REPORT.md. Probe использует explicit MATCH expressions и in-memory content/kind FTS5 tables; Rust normalizer не импортирует и не портирует. Fixtures согласованы с заявленной representation boundary. Recent fallback проверяется отдельным SQL branch, не выдаётся за результат пустого MATCH. Raw NUL negative control и normalised-space phrase разделены. Небольшой собственный read-only JSON consistency check подтвердил, что сохранённые actual/error действительно соответствуют expected во всех 27 cases; сам SQL probe reviewer не повторял.

Существенного representation overclaim в report не найдено. Case comparisons сортируют обычные MATCH results: это set/content evidence, не доказательство rank ordering. Отдельный recent case проверяет порядок id DESC. Combining-mark case — только self-match. Evidence указывает Python 3.12.14 / linked SQLite 3.53.1, не bundled rusqlite engine; Rust selection/normalization и proposed tests по-прежнему не выполнены. Исходный source verdict и необходимость actual Rust/bundled regression gate не изменяются.

Independently verified SHA256:
- python_fts5_probe.py: `8e0cff6936c9a45b1114cd0b460cb15472396948701bdb10c6d1ff75e5642375`
- PYTHON-FTS5-RESULTS.json: `edf943b46b11f7b399dc48d81f04ad70126d10c8da3d26b39df607fb9013b3a5`
- REPORT.md: `80ae420fec5ace3d573f559fbc87fdd247cfcf615e7f3ed4fddc863563c7330a`
- unchanged patch: `333558ca5742e39adeeb10347c8382dce78c0ff14cbe6b3e455cd48b9bd00a95`

Reviewer не запускал Rust/compiler/project tests, SQL probe или provider calls и не менял candidate/production/publication state.
