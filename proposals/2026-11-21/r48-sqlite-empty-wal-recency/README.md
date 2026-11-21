# SQLite: чтение больше не поднимает старую сессию вверх списка

[Патч](candidate.patch) для [Proteus-modules 9469e3b](https://github.com/Proteus-harness/Proteus-modules/commit/9469e3b12529d08b1f4a76882693e2065e842c51). Публичный `OpenSnapshot` открывает read-only транзакцию SQLite. При отсутствии WAL SQLite может создать пустой `journal.sqlite-wal` с текущим временем изменения, не добавляя записи. Метки источника уже игнорировали файл нулевой длины, но `sessions::open` использовал его mtime в `updated_at_ms`. Поэтому просмотр старой сессии мог переставить её выше недавно записанной, даже при попадании в кэш.

Изменение только в расчёте времени: игнорировать WAL **нулевой длины только для SQLite**. Непустой WAL по-прежнему участвует в сравнении с mtime базы. JSONL, запасное время каталога, использование времени создания, правила сортировки при равенстве, журнал, метки источника, проверка blob, sidecar v1 и прочие проверки не менялись. Дополнительных файловых обращений нет: длина доступна в уже загруженной metadata. Это исправление порядка, не оптимизация задержки.

## Проверка настоящим процессом

Два обычных SDK worker точного пина, синтетические базы во временных каталогах. Сессии A (старше) и B (новее) содержат по 8 настоящих записей. Порядок в таблице от свежей к более старой.

| Операция | Исходник | Патч |
|---|---|---|
| WAL отсутствуют, `ListCandidates` | B → A | B → A |
| Нативный `OpenSnapshot` удерживает транзакцию A и создаёт WAL ровно 0 байт, `ListCandidates` | A → B | B → A |
| Строгий cold List при тех же пустых WAL, без sidecar | A → B | B → A |
| Снова List в памяти и List в новом процессе при поднятии только mtime пустого WAL A | A → B | B → A |
| Реальный Commit в A при удерживаемой читающей транзакции, WAL 8272 байта | A → B | A → B |

В сценарии кэшей побайтный checksum файла и его inode/mtime/ctime не меняются от поднятия mtime пустого WAL. Отдельно новый worker прочитал **старый индекс v1, реально записанный stock worker со старым неверным timestamp**: вернул B → A и сохранил байты и метки sidecar. Миграция не нужна.

После настоящего Commit свежий List показал 9 записей в A, а старый нативный `ReadRecords` вернул исходные sequence 1–8. Параллельная SQLite read-only транзакция, открытая стандартным Python `sqlite3`, также видела 8. Это не тест искусственно написанного непустого WAL; он получен обычным Commit. В некоторых вспомогательных этапах fixture устанавливает mtime явно для воспроизводимого порядка; начальный WAL A создаёт настоящий SDK `OpenSnapshot`.

[Исходный процесс](stock-repro.log) · [Процесс с изменением](fixed-repro.log) · [Протокол тестов](validation.txt).

## Проверки и повторение

- Новый Rust-тест выставляет известные времена обычного журнала и пустого файла: без патча падает в SQLite (20 000 вместо 10 000 мс), с патчем проходит. Для JSONL тест ожидает прежние 20 000 мс. Прямой locked-прогон на Linux: **64 unit + 2 process passed**, 1 штатный ручной тест пропущен. Полный workspace и Windows не запускали.
- На точном пине: `git apply candidate.patch`, затем `python3 scripts/test.py -p session-storage -p proteus-session-storage-module`. На Linux host-only offline кэше обёртке не хватило Android-пакета на стадии cargo metadata. Прямое тестирование: `cargo test --offline --locked -p session-storage -p proteus-session-storage-module` с `PROTEUS_TEST_HARNESS_ROOT` на checkout закреплённого Core `0c1b757`.
- Собрать `cargo build --locked -p proteus-session-storage-module` в разных target dirs для точного пина и пина с патчем. Затем `python3 repro.py /path/stock --behavior stock` и `python3 repro.py /path/fixed --behavior fixed --reference-worker /path/stock`. Запускали на Linux x86-64; реальные пользовательские данные, услуги и конфиг не нужны.
