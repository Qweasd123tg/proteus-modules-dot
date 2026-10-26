# evidence.verify_spans

Небольшой внешний **Rust tool/v6** для одного практического сценария: проверить точную цитату исследовательского отчёта против разрешённого локального source artifact. Реализация не зависит от Core и не содержит browser/network/FS fallback.

**Состояние проверки:** source-reviewed CI candidate. `Cargo.lock` закреплён; runtime validation этой ветки пока pending. Нельзя считать 39 authored Rust tests пройденными до exact-head CI и проверки artifact. См. `VALIDATION.md`.

## Сквозное использование

1. Оператор сохраняет разрешённый source snapshot и задаёт `source_id → relative path` в config. Origin/commit pin проверяется отдельно выбранным процессом получения файла.
2. Исследователь создаёт quote request с ожидаемым SHA256 **всего** файла и half-open byte offsets.
3. Tool **сам** вызывает host `read_file({path: configured_path})`, проверяет полный reader result, digest и все quote spans против **одного** returned buffer.
4. Reviewer получает byte-match witness. Смысл утверждения, авторство источника и актуальность внешней страницы оцениваются отдельно.

Authored fixture `fixtures/source.txt`:40 UTF-8 bytes; SHA256 `8d01afa7f92eb5599e57a9a627240c2827135cdc842d30b19c11aeeb789a2bd5`. `fixtures/request.json` проверяет «Привет 🌍» по bytes[6,23) и combining-accent fragment по[24,27). Fixture специально различает UTF-8 bytes, code points и Unicode normalization.

Config:

```json
{"schema_version":1,"sources":[{"id":"research-artifact","path":"fixtures/source.txt"}]}
```

Request:

```json
{"source_id":"research-artifact","expected_sha256":"8d01afa7f92eb5599e57a9a627240c2827135cdc842d30b19c11aeeb789a2bd5","claims":[{"claim_id":"greeting","start_byte":6,"end_byte":23,"quote":"Привет 🌍"}]}
```

Модель не выбирает path, reader, read range, policy, permissions или собственный verification result. Незнакомый source_id отклоняется до callback. Path относится к invocation cwd, не каталогу executable. `profile.fragment.toml` дополняет существующий профиль; он не заменяет policy и не регистрирует/разрешает reader автоматически.

## Что именно подтверждает ответ

Успех содержит metadata `proteus.example.evidence_spans`:

- `status=exact_byte_match`, `scope=observed_host_read_bytes`;
- source_id, configured_path и observed_path;
- config_sha256 (typed serde serialization), content_sha256 и source_bytes;
- verifier_call_id и независимый reader_call_id;
- verified_claims:claim_id,start_byte,end_byte,quote_sha256;
- **origin_verified=false**, **semantic_entailment=not_evaluated**.

Quotes и полный source не копируются в успешный receipt. Module-generated validation diagnostics не содержат цитат; trusted host error text может сохраняться в ограниченном виде. Это не обещание redaction ошибок host. Receipt не использует generic Hermes verification key и не означает «тесты пройдены». Совпавший digest — equality binding, не подпись автора. Если модель сама придумала expected hash, успех говорит только о совпадении с independently returned bytes, не о доверии к pin.

Любая ошибка одной claim запрещает positive witness для всего invocation. Нет fuzzy search, skip, trim, newline conversion, CRLF normalization или NFC/NFD normalization. Другие scopes (PDF text extraction, live DOM, source origin authentication) намеренно не поддержаны.

## Граница доверия reader

Модуль использует existing host callback, поэтому не обходит Core policy/approval/cancellation. Reader convention закреплена в `SOURCES.md`: full read, matching call ID/path/tool, success без error/structured content, точные line counts, `truncated=false`, отсутствие неподдержанных metadata.

Общий `checked-read-support` — **pure validator** над canonical ToolResult. Он не открывает файлы, не вызывает host, не выдаёт права и не знает quote/JSON-assertion semantics. Max-output cap передаёт caller; raw callback JSON cap принадлежит caller до typed parse.

Core `AfterTool` может изменить output при сохранённой metadata. Поэтому в доверенную вычислительную базу входят выбранный reader и hook chain. Ответ подтверждает только наблюдавшиеся returned bytes, **не raw filesystem origin, отсутствие symlink, atomic snapshot или свежесть внешнего источника**. Lexical allowlist — выбор источника, не filesystem sandbox.

Никакой memory mutation/CAS или persistent receipt store здесь нет. Следующий consumer исправления фактов потребует собственного реального backend/authorization/idempotency/recovery design. Этот модуль их не создаёт.

## Ограничения

| Данные | Bound |
|---|---:|
| Config |64KiB;1–64 sources |
| Source/claim IDs |1–64 ASCII `A-Z a-z 0-9 _ - .` |
| Configured path |1–512 UTF-8 bytes;relative normal segments |
| Cwd |absolute lexical-normal UTF-8≤4096 bytes |
| Verifier call ID |1–128 bytes |
| Request JSON после SDK decode |64KiB |
| Claims per call |1–32;unique claim IDs |
| Quote |1–4096 UTF-8 bytes;aggregate≤16384 |
| Source output |64KiB |
| Raw reader callback JSON |512KiB |
| Serialized successful ToolResult |16KiB |

Config/request byte limits применяются к serialization после существующей SDK allocation/parse в Value, а не при transport admission. Bounds checked module-side не отменяют уже выполненную allocation. Config/request unknown fields, negative/fractional offsets, empty/reversed/out-of-range spans и UTF8 splits отклоняются. Overlapping spans разрешены: это проверка bytes, не их семантической независимости.

Cancellation проверяется до read, после callback, в claim loop и перед success. Race после последней poll принадлежит host commit/settlement. Tool объявлен ReadOnly, parallel opt-in=false и timeout60s; это не OS sandbox.

## Workspace и проверка

- Main crate: `proteus-example-evidence-spans`;
- neutral helper: `support/checked-read` (`checked-read-support`);
- `tests/policy.rs`: synthetic ToolModuleHost, реальная проверка bytes/hashes/receipts;
- `tests/wire.rs`: наш executable+SDK framing с authored reader callback;
- `examples/authored_quote_audit.rs`: offline demonstration, **synthetic host**, не actual Core/read_file run.

Команды с подготовленным lock (Rust1.95.0):

```sh
cargo test --locked --workspace -j2
cargo run --locked --example authored_quote_audit
cargo run --locked --example authored_quote_audit -- --wrong-quote
cargo fmt --all -- --check
```

Actual Core registry invocation и настоящий read_file остаются отдельным gate: нельзя назвать synthetic callback filesystem integration. SDK pinned3f36a003; current Core1fc3ef2 прочитан отдельно, relevant source slices identical, но это не runtime pass against1fc.

Никакие upstream OpenHands/Letta/Strands tests/scripts, browser actions, external model calls или пользовательские hooks не выполняются этим example.
