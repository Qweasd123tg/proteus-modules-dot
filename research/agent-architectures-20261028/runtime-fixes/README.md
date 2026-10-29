# Небольшие правки runtime и component packaging

Эти patches нужно применять отдельно к указанным исходным ревизиям. Они не меняют репозитории пользователя автоматически. Компиляция и исполнение не выполнялись.

## Cancellation во время admission

- Файл: [admission-cancellation.patch](admission-cancellation.patch).
- База: Proteus-core `125a9eb4088991513e9f61d899469be2076e266c`.
- Изменяется только `crates/proteus-core/src/process_adapters/client.rs`.

Существующий polling отмены теперь работает и пока `.start()` ожидает admission/restart handshake. При замеченной отмене pending future освобождается; используется уже существующая обработка закрытого terminal receiver. Ошибки admission и post-ACK путь сохраняются.

Это не мгновенное прерывание handshake и не rollback: если ACK/activation уже произошли до наблюдения отмены, запрос мог быть отправлен. Интервал остаётся прежним — 10 ms.

## Публикация и reuse выбранного модуля

- Файл: [module-package-publication.patch](module-package-publication.patch).
- База: Proteus-modules `5fa8978684a37e8083c64f4d6cf0289e72450c6a`.
- Изменяется `package.py`; публичные команды и layout сохраняются.

Новые binary/notices/metadata подготавливаются до замены опубликованных файлов. Digest считается по той staged-копии, которая будет установлена. При обработанной ошибке публикации восстанавливаются предыдущие выбранные файлы; если rollback тоже не удался, recovery backup сохраняется с диагностикой. Соседние пакеты не обновляются.

Build index сохраняет SHA-256. `--no-build` отказывает при несовпадении bytes, version или exports; старый index без digest требует rebuild. Изменения только source code всё ещё разрешены как намеренный режим без проверки свежести. Expected digest передаётся до staged install/ZIP, чтобы смена artifact между reuse и копированием не была незаметной.

Ограничения: это rollback при перехваченных ошибках, а не cross-file crash transaction или lock конкурентных installers. Не гарантируется snapshot исходников при параллельном редактировании/сборке; неуспешная подготовка может оставить пустые созданные каталоги.

## Snapshot существующего skill-каталога

- Файл: [portable-skill-catalog-snapshots.patch](portable-skill-catalog-snapshots.patch).
- База: `proteus-modules-dot` commit `ea7409b30edec9a84a842a36d6ec56d0fbdd3059`, пример `examples/portable-skill-catalog`.

У каждого provider export собственный immutable snapshot с локальной revision, single-flight discovery и максимальным возрастом 30 секунд по monotonic clock. Cache hit заново проверяет текущие disabled IDs, roots и открывает сохранённые SKILL.md через прежние path/read guards, но не читает их содержимое. Ошибка revalidation возвращает обычное discovery. Snapshot с diagnostics не кэшируется.

Явный catalog refresh и каждый load остаются свежими; load сохраняет проверку path/hash/disabled. Ожидание cache lock проверяет cancellation с интервалом 10 ms. Файловые syscalls не становятся прерываемыми; metadata и новые entries могут оставаться устаревшими до expiry. Это cache внутри одного export, не shared memory между процессами и не замена read authority.

## Один разбор terminal SSE JSON вместо двух

- Файл: [terminal-sse-parse.patch](terminal-sse-parse.patch).
- База: Proteus-modules `5fa8978684a37e8083c64f4d6cf0289e72450c6a`.

Обычный OpenAI stream уже разобрал `response.completed` в `Value`. Этот объект передаётся в finalizer вместо повторного разбора той же JSON-строки. Repair/output/usage/error обработка сохранена. Два существующих test call sites только адаптированы к сигнатуре; новые тесты не добавлялись и тесты не запускались.

Эффект подтверждён только структурой исходника: один вызов JSON parser удалён с terminal-пути. Прирост скорости и RAM не измерялся.
