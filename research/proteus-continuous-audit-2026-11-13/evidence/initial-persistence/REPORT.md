# Proteus persistence / recovery audit

Проверен Core `89997df995df7c39b713e16aba216ecb19c8f497`; main повторно совпал в конце проверки. Это найденные актуальные дефекты, не доказательство, что они появились в последнем коммите.

Production-код не изменялся. В отдельную копию добавлен только изолированный integration probe. Три диагностических теста **подтвердили дефекты** (их assertions намеренно описывают текущее ошибочное поведение). Настоящий SessionStore и его production-функции скомпилированы и выполнены. Никакие модули/провайдеры/сеть не используются.

## PERSIST-1 — P2: частичная первая запись метаданных делает чат непригодным для повторной попытки

`materialize_for_write()` создаёт session directory и необратимо переводит `may_create=false`. `write_metadata()` затем пишет непосредственно в `session.json` через `std::fs::write`, без временного файла/rollback. Если запись частично завершается ошибкой, повторная операция выбирает ветку существующего каталога и требует parse уже повреждённого JSON.

Воспроизведено: только тестовому процессу временно задан RLIMIT_FSIZE=64, SIGXFSZ игнорируется. Это настоящий отказ файловой записи EFBIG, не подмена production-функции. Lock-файл успевает сохраниться, session.json остаётся 64 байта. После восстановления предыдущего лимита append и SessionStore::open продолжают возвращать `EOF while parsing a string`. До сбоя никакой ранее принятой истории не было; не утверждается потеря существующих сообщений.

Рекомендуемое направление: transactional materialization под уже существующим lease, atomic metadata write и явная безопасная обработка провала собственной незавершённой инициализации. Не следует автоматически чинить/перезаписывать произвольный ранее повреждённый session.json.

Источники:
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store/writer.rs#L182-L258
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store/identity.rs#L228-L244

## PERSIST-2 — P2: сбой записи blob оставляет незавершённый временный файл

`write_blob()` создаёт `.SHA.tmp.UUID`, но cleanup есть только в ветках ошибки rename. Ошибка `write_all`, `flush` или `sync_data` выходит через `?` до cleanup.

Воспроизведено на уже рабочей сессии: сообщение 300 000 символов переключает payload в blob; RLIMIT_FSIZE=65 536 приводит к частичной записи и EFBIG. Остаётся временный файл 65 536 байт. После снятия лимита повторный append успешно сохраняет payload, но прежний temp остаётся. Предыдущая история сохраняется, итоговая история содержит две записи. Повторные отказы создают новые уникальные temp-имена; это может усугублять нехватку диска. ENOSPC/EDQUOT отдельно не инъецировались.

Рекомендуемое направление: RAII cleanup guard на temp-файл с момента создания до успешной установки, включая ранние ошибки write/sync.

Источник:
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/storage.rs#L260-L298

## PERSIST-3 — P2: обычный длинный workspace path нельзя использовать с сохранением сессий

Абсолютный workspace path кодируется целиком в один компонент имени каталога (`parts.join("|")`). Это переносит ограничение NAME_MAX с каждой исходной папки на весь путь, плюс percent-encoding может дополнительно увеличить его длину.

Воспроизведено: существующий путь длиной 259 байт, каждый из четырёх вложенных компонентов по 60 ASCII-символов, успешно создан ОС. Encoded component = 258 байт. SessionStore::new проходит (путь пока не материализован); первый durable append падает `File name too long (os error 36)` при создании session parent. В обычных Linux FS NAME_MAX=255 при PATH_MAX существенно больше.

Рекомендуемое направление: bounded workspace key (например hash + проверяемые metadata), без объединения произвольного абсолютного пути в единственный filename. Это изменение storage layout; не добавлять скрытую совместимость вопреки правилам проекта.

Источники:
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store/workspace_dir.rs#L7-L37
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store.rs#L84-L90

## Воспроизведение

В отдельной копии указанного SHA поместить `persistence_edge_audit.rs` в `crates/proteus-core/tests/` и выполнить:

```
cargo test --locked -p proteus-core --test persistence_edge_audit -- --nocapture --test-threads=1
```

Тесты меняют RLIMIT_FSIZE/SIGXFSZ только внутри своего отдельного процесса и восстанавливают прежние значения до проверок. Не включать параллельное исполнение с другими тестами в том же процессе.

В этой проверке первоначальный Cargo invocation подготовил библиотеки, но выявил неверные импорты моего probe (`domain` / `model_standard` приватны в proteus-core). Импорты исправлены на proteus-contracts. Чтобы не удерживать общий Cargo lock другой проверки, итоговый probe собран `rustc --test` с уже собранными библиотеками той же копии и SHA; фактический результат в `probes-result.log`. Это не полная повторная проверка workspace, CLI или GUI.
