# Проверен ранее опубликованный патч #213

[Предложение #213](https://github.com/Qweasd123tg/proteus-modules-dot/pull/213) было опубликовано без проверки Rust. Здесь не создаётся новый вариант патча. Проверен [исходный patch-файл](https://github.com/Qweasd123tg/proteus-modules-dot/blob/5655378a0a6c6c2867d8c84d228cee32f7ede830/proposals/2026-11-18/cache-snapshot-isolation/cache-snapshot.patch) на Modules `37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979`.

* Сначала наложен только раздел теста (`storage/session-storage/src/tests/metadata.rs`). Он скомпилировался и на неизменённой реализации упал в `conversation()`: `snapshot handle expired or unknown`. При проверке кеша один из 32 открытых снимков преждевременно вытеснен.
* В ту же копию добавлены два оставшихся раздела прежнего патча. `cargo test --locked -p session-storage --lib`: **30 passed, 0 failed, 1 ignored** (штатный ручной замер). Тест перебирает JSONL и SQLite, актуальный и устаревший кеш, все 32 прежних дескриптора и вытеснение при явном 33-м открытии.
* Дополнительно наложен [новый SQLite-патч](sqlite/sqlite-journal-reads.patch) этого прохода: **31 passed, 0 failed, 1 ignored**, включая оба регрессионных теста. Штатный проигнорированный замер затем запущен отдельно: **1 passed**; в 100 тёплых итерациях на каждом backend при 16 МиБ истории счётчики повторного декодирования и хеширования остались нулевыми. Изменения не конфликтуют в этом пакете.

Использованы Rust 1.95.0, Linux x86_64 и исходный Cargo.lock. Compile-time Core у Modules закреплён на `4c032eeb` и отличается от runtime-пина Desktop. Это квалификация исправления в пакете на конкретной ревизии, не наблюдение из GUI и не внедрение в upstream.

Воспроизведение в чистом временном checkout Modules на указанном SHA (переменные указывают на локальные файлы):

```sh
git apply --check "$PATCH_213"
git apply --include='storage/session-storage/src/tests/*' "$PATCH_213"
cargo test --locked -p session-storage --lib cache_writes_leave_public_snapshot_handles_alone
# Выше на исходной реализации ожидается ненулевой статус с указанной ошибкой.
git apply --exclude='storage/session-storage/src/tests/*' "$PATCH_213"
cargo test --locked -p session-storage --lib
git apply "$SQLITE_PATCH"
cargo test --locked -p session-storage --lib
cargo test --locked -p session-storage --lib sixteen_mib_history_warm_snapshot_and_head_publication_cost -- --ignored --nocapture
```
