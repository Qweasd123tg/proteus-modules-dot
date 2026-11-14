# DS-2: ACK журнала не включает durability его filesystem dependencies

## Статус и границы

**Source-only кандидат P2 только при требовании OS/power-crash durability.** Если продукт обещает лишь process-crash recovery, сначала нужно согласовать более сильный контракт. В текущих документах найдено описание process crash/kill recovery (`runtime-and-events.md:1341–1353,1733–1738`), но явного обещания OS/power-loss durability review не обнаружил. Поэтому это не доказанное нарушение уже описанной продуктовой гарантии. Исходники показывают отсутствие нужных file/directory barriers. Не воспроизведён power loss, reboot, filesystem fault, пропажа blob, потеря данных или отказ живого Proteus. Иллюстративная модель не является runtime evidence и не включена в пакет.

**Условность контрактная, не только экспериментальная.** Независимый reviewer нашёл в `runtime-and-events.md:1587–1595` описание committed state после `sync_data`, а в `1341–1353, 1733–1738` recovery после **process crash/kill**, но не явное обещание OS/power-loss durability. Поэтому DS-2 — P2 candidate **если power-crash durability является требованием**, не подтверждённое нарушение явно описанного product contract. Обычная process-cancellation гарантия этим finding не опровергается.

База: Core upstream `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89; дерево `00a3c04a70d7927d1688ea155142025f596a2874`. PR91 прочитан и не меняет production. Rust toolchain отсутствует. Runtime/source patches не делались.

## Главный новый случай: успешный большой append в существующую session

Условие специально исключает незавершённую первоначальную материализацию: существующие session directory, `session.json`, `journal.jsonl`, `blobs/` уже durable. Добавляется новый уникальный payload, который попадает в blob (штатный threshold 256 KiB).

1. `append_record`, `core/session_journal/storage/append.rs:100–106`: сначала проверяет candidate и вызывает `write_blob`.
2. `write_blob`, `core/session_journal/storage.rs:262–303`: создаёт temporary в `blobs/`, записывает bytes, вызывает `file.sync_data()`, затем `rename(temp, blobs/<sha>.json)`. На успешной ветке **нет sync directory `blobs/`**.
3. `append_record:119–159`: добавляет полную JSONL-строку со ссылкой на final blob name; `journal.sync_data()` проходит, rollback disarm-ится, writer state/usage/model_context обновляются, возвращается `Ok(record)`.
4. Linux file fsync не гарантирует сохранение directory entry; для этого нужен отдельный directory fsync. Это проверено по [Linux man-pages, fsync(2)](https://man7.org/linux/man-pages/man2/fsync.2.html). Следовательно, barriers в коде **не устанавливают** инвариант `ACK journal reference ⇒ durable final blob name`. Определённая FS может сохранить namespace побочно, но общей гарантии нет.
5. Допустимый в абстрактной модели crash-state: journal со всей подтверждённой строкой сохранился; bytes blob были flushed, но final name не сохранился. Это вывод из отсутствующего порядка durability, а не наблюдённое состояние ext4/XFS/NFS.
6. При cold resume `initialize::recover` (`storage/initialize.rs:47–64`) сначала `repair_unterminated_tail`, затем полное чтение/validation. `repair_unterminated_tail` (`storage/recovery.rs:21–24`) не трогает newline-terminated запись. `hydrate_entry` (`storage.rs:320–360`) требует размер/bytes/hash файла по final name и возвращает ошибку при его отсутствии.

Результат при таком crash-state: продолжение и строгие чтения всей session не проходят, хотя старый корректный prefix может оставаться на диске. Обычный каталог способен скрыть unusable session с warning, а audit сообщает ошибку (`session_store/catalog.rs:141–183`). Это **availability/recovery failure**, не доказательство необратимой потери всей старой истории. Наличие bytes во временном имени/другой копии и возможность ручного ремонта отдельно не проверялись.

## Та же граница при первом сохранении

- `session_store/writer.rs:169–177, 202–205` создаёт ancestors/session directory без directory barrier.
- `session_store/identity.rs:228–244` записывает `session.json` через `std::fs::write`, без sync file и без atomic temporary installation.
- Первое создание `journal.jsonl` в `append.rs:127–141` sync-ит файл, но не добавление его имени в session directory.

Поэтому первый успешный append не доказывает crash-durability всей identity/path chain. Это дополнительное проявление одного отсутствующего dependency-commit contract, а не второй новый defect count. Обнаруженный ранее **PERSIST-1** касается обычного частичного write failure и retry на повреждённом metadata; здесь обсуждается успешный ACK без write error и последующий системный crash. Общая зона исправления пересекается, что нужно сохранить в дедупликации.

## Почему существующие гарантии не закрывают эту цепочку

- `spawn_blocking` + writer mutex удерживают admitted operation после отмены awaiter; это process-lifetime/cancellation safety, не disk barrier.
- OS writer lease исключает cooperating writers, но не flush directory state.
- `AppendRollback` исправляет замеченный write/sync error. В описанном случае все вызовы вернули success и guard disarmed.
- Строгий reader правильно отвергает отсутствующий dependency; ослабить hydration/пропускать строку было бы неправильным исправлением.
- Повторное чтение после ACK не доказывает durability: его обслуживает тот же page cache.
- Graceful restart и SIGKILL одного процесса не равны потере kernel page cache. Поэтому обычный kill/reopen regression не доказывает power-crash contract.
- В отличие от blob path, `runtime/images.rs:75–77` уже sync-ит **свою** attachment directory после rename. Это полезная локальная модель порядка, но её нельзя объявлять полной durable path chain для newly-created ancestors.

## Предлагаемое системное упрощение

Один явный invariant для canonical writer: **до публикации journal reference все новые referenced files и directory edges должны быть подтверждены storage-слоем; до внешнего ACK должен быть подтверждён и journal append**.

Минимальный разрез не требует нового subsystem или storage format:

1. Небольшой локальный helper «install durable file», который владеет temp cleanup, file sync, rename и parent-directory sync. Blob и initial identity должны использовать согласованный contract, а не похожие независимые write sequences. Image helper можно сравнить/переиспользовать только после проверки её отдельной semantics.
2. Отдельный helper для directory chain: sync новых/ещё неподтверждённых directory entries до первого canonical ACK. Он должен учитывать и directories, уже существующие после предыдущей failed попытки materialization/sync; отслеживать только `mkdir` текущей попытки недостаточно. Простое добавление fsync только `blobs/` решает главный existing-session случай, но не newly-created ancestors.
3. Повтор после ошибки directory sync обязан снова подтвердить durability, даже если final name уже существует и bytes совпадают. Нельзя заменить проблему на «failed fsync; retry sees exists; skips barrier; ACK».
4. Не применять durability cost автоматически к `.read-*.sqlite`: это disposable cache с иной обещанной семантикой. Не распространять canonical writer contract на все event logs/preferences без отдельного решения.
5. На неподдерживаемой platform/fs явно определить гарантию и ошибку. Не скрывать directory sync error под best-effort, если API обещает durable ACK.

Ожидаемый выигрыш в одном месте реализации durability ordering/cleanup, не в измеренном ускорении или снижении LOC. Устанавливать format/compatibility migration для этого не требуется.

## Предлагаемые проверки, НЕ ЗАПУЩЕНЫ

- **Syscall-order contract:** existing durable session; new blob. Observer должен увидеть blob write → blob file sync → rename → blobs-directory sync → journal write/sync → ACK. Отдельно проверить reuse existing durable blob и normal inline append. Это проверка ordering, не power-loss evidence.
- **Directory-sync fault:** fault после rename и до journal append; никакого ACK нового record, old journal hash прежний. Повтор с уже существующим final file обязан повторить barrier и только затем commit.
- **Initial materialization:** сбои каждого directory/file barrier; нельзя ACK-нуть session с неподтверждённой identity/path chain. Не разрешать автоматическую перезапись произвольного чужого/старого damaged metadata.
- **Strict-read oracle:** в отдельной синтетической копии создать complete record с отсутствующим referenced blob; reader должен возвращать ошибку и не менять journal. Это доказывает последствия constructed prefix, не origin power crash.
- **Настоящий durability gate:** отдельная разрешённая disposable VM/filesystem fault harness с power-cut emulation; закрепить filesystem/mount/storage settings и cut points. Не использовать пользовательский workspace. SIGKILL-only test не называть этим gate.

Отдельная иллюстративная таблица crash-state предпосылок (не включена в пакет) формализует только независимость file-content и directory-name durability и сохранение полной строки при tail recovery. Она показывает один permitted bad state и controls, но не измеряет filesystem behavior и не доказывает частоту crash outcome.

## Дедупликация и триаж

- PR91 DS-1 — доступность page/tool-state при cap fingerprint, не crash durability. TC-1/TC-2 не затрагиваются.
- PERSIST-2 — orphan temp **на ошибке записи**, здесь — отсутствующая namespace barrier **на success**. Общий helper может закрыть оба, но набор regression различен.
- PERSIST-1 пересекается с initial identity подслучаем; основной DS-2 intentionally проверяется на уже durable session и new blob.
- PR90 — завершение live effects при shutdown; не обеспечивает power-loss flush ordering.
- В извлечённом полном тексте PR84 выполнен поиск `fsync`, `sync_data`, `sync_all`, `write_blob`, attachment/image-store и релевантных durability разделов; соответствующего finding не обнаружено. Это не повторное полное построчное чтение всех 91 страниц.
- Возможная отдельная проблема проверки bytes существующего image по SHA рассмотрена, но **не повышена до finding**: пока не показан штатный producer изменения immutable attachment; corruption/tampering сам по себе недостаточен для новой приоритетной задачи.

Независимый source review выполнен: PASS только в условной source-only границе. Поправка о retry для уже созданных, но неподтверждённых directories внесена. Перед реализацией требуется согласовать обещаемый crash-durability contract. Ни runtime-подтверждённый дефект, ни исправление здесь не заявлены.

## Закреплённые source anchors

Пути `core/...` выше относительны `crates/proteus-core/src/`. Ключевые production-файлы не изменены delivery PR87–89.

- [core/session_journal/storage.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/storage.rs#L262-L303)
- [core/session_journal/storage/append.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/storage/append.rs#L100-L159)
