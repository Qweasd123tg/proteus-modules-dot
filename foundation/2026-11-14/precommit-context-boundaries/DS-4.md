# DS-4: complete JSONL prefix до commit становится named display revision

## Статус и границы

**P2 source-only кандидат, условие: concurrent read и journal append failure после full write, до commit, с успешным rollback.** Не power-loss сценарий и не dropped-run finding. Rust/runtime/HTTP/fault-injection не выполнялись. Ни частота окна, ни проявление ошибки на реальной filesystem не измерены. Отдельная абстрактная Python-модель только иллюстрирует transitions и в пакет не включена.

Приоритет предполагает **committed-only contract именованной history revision**. Source comments называют такие views completed, а rollback прямо считает строку uncommitted. Если продукт намеренно разрешает speculative/aborted rows в этом API, требуется прежде уточнить контракт; stale-cache support сам по себе не является дефектом.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. PR91/92 прочитаны; это документация, production-база ими не изменена. Core не менялся.

## Две разные границы, принятые за одну

Writer считает mutation committed после `sync_data`, а lock-free reader считает весь complete newline-terminated prefix пригодным для canonical/display projection. Fingerprint доказывает стабильность файла между наблюдениями, но не завершение writer transaction.

1. `core/session_journal/storage/append.rs:125–159`: `AppendRollback` armed; `file.write_all(&line)` записывает полную JSONL-строку вместе с newline; затем `flush` и `sync_data`. Только после успеха выполняются `rollback.commit()` и обновление `state.validation`/`committed_offset`. Ошибка `sync_data` ещё может привести к удалению всей строки.
2. `storage/recovery.rs:46–109` восстанавливает предыдущий committed offset. Существующий source-test `armed_guard_removes_even_a_complete_uncommitted_record` (`134–142`) прямо различает complete и committed; тест здесь не запускался.
3. `JournalReadSnapshot::open`, `storage/read.rs:58–85`, выбирает boundary через `metadata.len()` и `complete_jsonl_offset`. Он не читает writer committed offset и не берёт writer transaction lock. Typed validation и повторное SHA-сравнение доказывают семантику/стабильность увиденного prefix, но не его commit.
4. `SessionStore::open` получает общий writer Arc, однако ни `open`, ни `project_read_model` (`session_store/read_model.rs:160–172`) не берут этот mutex. Поэтому успешный source read может полностью уложиться между full write и последующим sync failure/rollback.

Документация тоже разделяет эти понятия неявно: `docs/guides/runtime-and-events.md:1587–1595` говорит, что ошибка записи не меняет committed state до успешного sync; `1502–1518` описывает свежие canonical cold reads и именованную **завершённую** display revision. DS-4 относится к publication isolation, не обещает больше power-crash durability, чем описано в продукте.

## Связь с HTTP paging и disposable cache

Проблема не ограничена прямым Rust read:

- `app_server/http/sessions.rs:232–251`, `history_page_json`, открывает `SessionStore` и disk paging **без проверки live server**, в отличие от `/conversation`. Поэтому данный source path существует и для active session; это не утверждение о частоте UI-запросов в нужном окне.
- `app_server/read_model.rs:67–121`, `transcript_page`/`rebuild_transcript`, при отсутствии свежего индекса строит проекцию, сверяет source fingerprint до/после и возвращает revision.
- `project_read_model` сохраняет view через `session_store/read_model/sqlite/save.rs`. Если writer paused после full write, fingerprint всё это время стабилен. Cache gates и SQLite transaction не являются writer transaction gate.
- Renderer вызывается с `live_turn_id=None`; `app_server/transcript/journal.rs:144–159` в этом режиме не исключает user `HistoryMutated::Append` текущего turn. Минимальный store fixture может использовать append с `turn_id=None`, чтобы отдельно изолировать publication boundary.
- После sync failure и successful rollback file fingerprint становится другим. **Fresh** reads должны отвергнуть этот индекс и перестроить current state.
- Но `session_store/read_cache/sqlite.rs:112–116`, `Reader::finish`, возвращает сохранённый source и `fresh=false`, а не безусловный cache miss. `session_store/read_model/sqlite.rs:150–180`, `page_inner`, сознательно разрешает stale view при explicit matching `expected` revision. Это сохраняет прежние completed pages во время нового turn, но здесь удерживает view, которая никогда не была committed.

SQLite fsync не исправляет эту границу: даже если физически помогает записать journal bytes, он не disarm-ит `AppendRollback` и не делает mutation committed в writer state. Последующий штатный rollback всё равно truncates её.

## Минимальный причинный сценарий

1. Есть корректная durable session с H. Cache отсутствует либо соответствует H; маленький inline append A не требует новых blobs.
2. Append A проходит semantic validation, полностью записывает newline-terminated строку, затем worker удерживается **до journal sync/commit**. Writer state остаётся H, journal bytes читаются как H+A.
3. Параллельный `/history/page` без `revision` видит неизменный fingerprint, строит H+A, успешно сохраняет view и возвращает named revision R. Typed validation проходит: A сама по себе корректна.
4. Journal-specific/transient injected sync failure приводит к успешному `AppendRollback`. Append возвращает ошибку, canonical journal и writer state снова H.
5. До замены индекса запрос `/history/page?...&revision=R` возвращает cached H+A: `expected` совпадает с cached revision, хотя `fresh=false`. Прямой strict current read возвращает H.

Следствие: read/cache consumer может получить сообщение или display state из **отклонённой** mutation как именованную завершённую ревизию. Это не потеря canonical H, не постоянная порча journal, не доказанный повтор tool effect. Следующий fresh rebuild способен заменить view; execution resume по-прежнему проходит собственную строгую validation и не должен считать stale display execution authority.

## Ограничения и negative controls

- Нужна ошибка после full newline write: partial unterminated write reader отрезает, это другой случай.
- Для расширенного cache-сценария cache publication и rollback должны успешно завершиться. Тотальный отказ filesystem, мешающий всем трём операциям, не является предлагаемой fixture.
- При successful append раннее чтение само по себе не доказывает ошибку конечного state: A позже действительно committed. Воспроизводимый regression должен включать failed outcome.
- Если rollback изменил файл во время validation/render/fingerprint check, read может отказать. Нужен barrier, удерживающий writer **до конца** первого read/cache save.
- Existing exact old committed revision R0 должна по-прежнему читаться во время нового append. Исправление не должно просто запретить все stale revision или все live-session reads.
- `/conversation` live path имеет другие locks и здесь не используется как trigger. Current cache reads после rollback не объявляются постоянно stale.
- Ни process crash, ни OS power cut, ни caller abort для цепочки не нужны.

## Предложенный deterministic regression, НЕ ЗАПУЩЕН

1. В существующий append test seam добавить ограниченный barrier **после `write_all`/`flush`, перед `sync_data`** и one-shot journal-sync failure. Нынешний `AppendPause::before_write` стоит слишком рано и не доказывает этот сценарий.
2. Создать маленькую persistent fixture H без внешних modules/model/tool. Запустить append A; дождаться after-full-write signal. Все waits bounded, cleanup гарантированно отпускает worker.
3. Через `history_page_json` или тот же `transcript_page` получить current page и revision R, сохранив индекс. Observational oracle текущего source: page включает A. Desired contract после исправления: publication либо ждёт settlement, либо возвращает только прежний committed prefix; нельзя ACK-нуть A как completed.
4. Отпустить worker с однократным sync failure; rollback sync должен succeed. Дождаться append error. Сравнить исходные journal bytes, store history/revision с H.
5. До fresh rebuild повторить named page R. После исправления R с A не должна существовать как committed revision. Нельзя считать current observational PASS исправлением.
6. Контроли: normal success; partial unterminated failure; read до full write; read после rollback; stable старый committed R0 во время новой transaction; current read после rollback; cold process read для cross-process design.

Не включённая в пакет абстрактная Python-модель отдельно моделирует только visible bytes, committed history, frozen cached rows и выбор expected/fresh. Она не вызывает Rust, SQLite, HTTP или filesystem I/O faults и не подтверждает scheduling.

## Направление упрощения

Назвать один publish frontier: **complete bytes не равны committed prefix**. Snapshot/fingerprint/checksum отвечают за согласованность прочитанного набора; нужен отдельный факт, что набор завершён writer-ом.

- Same-process путь может брать стабильный writer-authorized committed boundary под коротким lock, а не заново выводить commit из EOF. Это не автоматически решает cross-process cold reads.
- Для cross-process гарантии нужен согласованный механизм публикации или короткий transaction read/write gate. Нельзя механически дать readers shared lock на существующий lifetime writer lease: тот удерживается до закрытия session и заблокирует все cold reads active session.
- Если выбран writer-published committed view/frontier, определить crash/lost-ACK semantics прежде, чем добавлять sidecar/marker. Новый marker не должен превращать полную восстанавливаемую запись после потери ACK в автоматически отбрасываемую.
- Либо явно выделить provisional display response, не выдавая его за completed revision. Простое игнорирование `fresh=false` нельзя менять глобально: оно обслуживает полезную поддержку старых действительно committed pages.
- Сохранять existing strict semantic validation; усиление read isolation не оправдывает пропуск damaged rows. Не добавлять универсальный storage framework ради одного gate.

Качественное упрощение — одна проверяемая publication boundary вместо предположения о commit в EOF, fingerprint и cache freshness одновременно. Выигрыш LOC/RSS/latency не измерен.

## Дедупликация и review

PR91 DS-1 касается fingerprint cap; PR92 DS-2 power-crash dependency barriers и DS-3 direct-run lifetime. Здесь successful full write **до failed transaction/rollback** наблюдается read-only consumer, даже без caller drop или crash.

Поиск по 97 ранее выгруженным audit reports выполнен отдельным audit-агентом: `uncommitted`, `precommit`, `watermark`, `rollback`, `dirty read`, `lineariz`, `sync_data` не выявили прямого совпадения. В полном PR84 extracted text выполнен targeted поиск этих понятий; это не построчное повторное чтение 91 страницы. PERSIST-1 metadata partial failure и PERSIST-2 orphan temporary не совпадают с этим publication path.

Независимый source review выполнен: PASS как read-isolation/publication candidate в указанном conditional scope. Уточнения о targeted journal fault, successful cache/rollback, bounded lifetime view и новом post-write seam включены. 13 source hashes записаны и сверены автором; это не runtime test. Source review и abstract model не являются runtime evidence.

## Закреплённые source anchors

Пути `core/...` относительны `crates/proteus-core/src/`. Ключевые production-файлы не менялись delivery PR87–89.

- [core/session_journal/storage/append.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/storage/append.rs#L119-L159)
- [core/session_journal/storage/read.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/storage/read.rs#L58-L85)
- [core/session_store/read_model/sqlite.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store/read_model/sqlite.rs#L150-L180)
- [app_server/http/sessions.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/http/sessions.rs#L232-L253)
