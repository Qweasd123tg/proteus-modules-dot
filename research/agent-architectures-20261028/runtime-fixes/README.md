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
