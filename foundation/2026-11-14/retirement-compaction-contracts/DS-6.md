# DS6: retirement не закрывает два cached-read пути SessionStore

## Статус и граница

**Узкий source-only API/документационный consistency finding, предварительно P3.** Это не потеря данных, не восстановление удалённого чата, не дефект безопасности и не доказанный GUI/HTTP-сбой. Если намеренный контракт допускает исторические diagnostic snapshots на уже retired handle, надо сузить соответствующее обещание документации вместо изменения поведения. Независимый source review подтвердил узкую границу; его ограничения учтены.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. Production исходники не менялись. Rust toolchain отсутствует; Rust/HTTP/GUI, проектные scripts и тесты не запускались. Запущена только собственная абстрактная Python-модель двух ветвей ниже.

## Обещание и причинная цепочка

`docs/guides/runtime-and-events.md:1355–1359` описывает owned delete: оставшиеся handles прежнего writer больше не могут читать его write-state или писать/воссоздавать session. Код уже реализует это для execution-state reads и всех mutations.

1. `core/session_store/deletion.rs:41–47,79–90`: owned deletion захватывает общий writer mutex, вызывает `retire_for_delete`, отпускает mutex, удаляет каталог, закрывает OS lease и возвращает результат. Сохранённый clone `SessionStore` разделяет тот же writer.
2. `core/session_journal/storage.rs:179–184`: retirement ставит `retired=true` и переносит lease/completion tail. Он не сбрасывает `initialized`, validation или usage.
3. `core/session_store/writer.rs:23–26,45–49,65–69`: `model_context_before_turn`, `committed_history`, `execution_state` проверяют `ensure_active` до чтения cached write-state. Это положительный контроль intended boundary.
4. В отличие от них, `core/session_store/usage.rs:7–14` читает `writer.usage_snapshot(...)` и затем cached read metadata без `ensure_active`. `storage.rs:222–230` проверяет только `initialized`.
5. `core/session_store.rs:167–177` аналогично отдаёт `cached_history_revision` или `CachedReadMetadata.revision` без active guard.
6. Дополнительная ветвь Unix: `hibernate_writer` в `writer.rs:5–14` переносит revision/usage в `read_metadata` и сбрасывает decoded writer state. Retirement не очищает этот cache. Поэтому только очистка `writer.usage/validation` при удалении не закрывает все старые reads.

После полностью завершённого owned delete новая операция на сохранённом handle может получить `Ok(old_usage)`/`Ok(old_revision)`, тогда как `execution_state` на том же handle возвращает `session writer generation is retired`. Для этого не нужны crash, fault injection, отмена или гонка.

## Достижимость и ограничения

- `SessionStore::usage_snapshot` является публичным Rust API. `history_revision` имеет `pub(crate)` scope.
- Публичные `AgentRuntime::usage_snapshot` (`runtime.rs:444–448`) и `AppServerHandle::usage_snapshot` (`app_server/usage.rs:5–7`) просто делегируют в store. Retained `AppServerHandle` остаётся пригодным для этого чтения после его `delete_workspace_session`, хотя admission уже закрыт (`app_server.rs:276–306`).
- HTTP `/delete-session` удаляет server из map до удаления каталога (`http/lifecycle.rs:129–135`). Новый обычный `/usage` после удаления идёт в cold `SessionStore::open` и не получает сохранённый handle (`http/sessions.rs:217–230`). **Поэтому не заявляется, что последовательный продуктовый HTTP-клиент продолжает читать удалённую usage.** Возможный ранее начатый overlapping read не требуется доказательству и не считается отдельным дефектом.
- Возвращаются только ранее накопленные accounting/revision facts. История на диске не воссоздаётся, live execution/writes остаются запрещены; не заявляются утечка, неправильное списание или provider call.
- Этот вывод не требует менять разрешённые cold inspection semantics или ретроспективные snapshots, уже явно полученные до deletion. Речь о новом вызове API на retired writer handle.

## Предлагаемый будущий regression (не выполнен)

Расширить существующий `core/session_store/deletion.rs::tests` или `app_server/ownership_tests.rs`:

1. Создать synthetic session. Записать непустую историю и один полностью завершённый synthetic model exchange с known usage; сохранить clone store. Можно использовать шаги уже существующего `usage_tests.rs::usage_tracks_exchanges_and_matches_read_only_cold_journal`, не вызывать provider.
2. Зафиксировать ожидаемые revision и usage до удаления.
3. В первом варианте оставить initialized writer. Во втором Unix варианте вызвать test-visible `hibernate_writer()` перед удалением, чтобы данные остались только в `CachedReadMetadata`.
4. Выполнить owned delete и дождаться успешного результата; проверить отсутствие каталога.
5. На retained clone вызвать `execution_state`, `history_revision`, `usage_snapshot`. Контроль первого должен отказать. По текущему source два последних возвращают старые значения.
6. При принятии documented запрета будущие assertions должны ожидать retired error у всех трёх. При выборе отдельного historical-read контракта нужно явно назвать возвращаемые данные и обновить docs/tests.
7. Контроли: fresh unsaved active session по-прежнему читается без материализации; active warm и cold usage остаются эквивалентны; declined delete scope не делает writer retired; retained stale handle не пишет и не воссоздаёт каталог.

Прочитаны полные существующие `usage_tests.rs`, `deletion.rs::tests`, `lifecycle_tests.rs` и `app_server/ownership_tests.rs`. Они закрепляют no-materialization cold read, active warm/cold usage equality, отменоустойчивое удаление, writer lease retention, отказ stale writes и закрытие admission. Явного assertion, разрешающего cached usage/revision read после retirement, там не найдено. Это не заявление об отсутствии любой такой проверки во всём репозитории.

## Упрощение общей границы

Минимальная правка при выборе documented semantics: проверять active lifecycle под тем же writer mutex **до всех** writer/read-metadata fast paths. Один только сброс `initialized` при retirement недостаточен из-за Unix metadata fallback.

Более системный локальный разрез: отделить lifecycle (`Active`/`Retired`) от active residency (`Cold`/`Ready`) и предоставлять read helpers только через проверенный active guard. Это делает отличие cold cache miss от terminal retirement явным. Не обязательно вводить новый public trait/slot или большой refactor; сначала общий закрытый accessor для нескольких store read paths. Preserve mutex ordering, independent removal worker и OS lease transfer. Новое enum состояние не должно автоматически выдавать fresh generation или разрешать старым handles воссоздавать удалённый session.

## Дедупликация

- PR91–94 не повторяются: нет cap fingerprint, power-loss barrier, dropped run future, precommit visibility или mixed clear snapshot. Здесь завершённая deletion и последующий read без concurrency.
- Полностью прочитаны опубликованные `initial-persistence/REPORT.md`, `runtime-state/README.md`, `state-install/REPORT.md`; их materialization/blob/path, clear-child projection и config roundtrip findings не описывают этот guard mismatch.
- По полному доступному PR84 DOCX  выполнен targeted поиск retirement/usage/delete. Прямого совпадения не найдено.
- Не заявляется exhaustive дедуп всех 97 отчётов.
- Отвергнутая на этом проходе replay ID normalization гипотеза уже описана в опубликованном `hooks-replay/H2`; не включена как новая находка.

## Локальная проверка

Отдельная абстрактная модель (не включена в пакет) моделирует только observed control flow. Обе ветви (initialized writer, hibernated metadata) сохраняют прежние значения после abstract retire/delete; guarded control отказывает. Это не исполнение production Rust и не файловый/HTTP reproducer. Авторские source SHA-256 сверены; production не менялся.

## Закреплённые source anchors

Пути `core/...` относительны `crates/proteus-core/src/`. Ключевые production-файлы не менялись delivery PR87–89.

- [core/session_store/usage.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store/usage.rs#L7-L14)
- [core/session_store.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store.rs#L167-L177)
