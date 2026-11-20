# Реальный HTTP-клиент Desktop для контроля R20

Источник: [Proteus-desktop `7ccb6c8634c4`](https://github.com/Proteus-harness/Proteus-desktop/tree/7ccb6c8634c40f450d83bb6e9eff891dc776ee6b). Здесь не запускалось окно GPUI и не измерялось время от клика до отрисовки. Драйвер использует без правок **сам код Desktop**: `Api::new`, `initial_history_page`, `history_page`, штатный ureq/transport, общую политику proxy/timeout и typed-декодирование `AppTranscriptPage`. В headless-режим не включены DNS/прокси другой машины или произвольные клиентские таймауты. Для недостижимого из пробы `resume` при компиляции подключена только настоящая константа `READY_TIMEOUT`, извлечённая из того же git-объекта. Никаких изменений в Core/Desktop в этом каталоге не требуется.

`build.py` получает исходники из указанного коммита; использует существующий полный dependency cache Desktop `cargo test --locked --no-default-features --bin proteus-native --no-run` с Rust 1.95.0. По fingerprint native Cargo target отдельно подбирает точные rlib/type identities, а не первые файлы с похожими именами. `build-identity.json` фиксирует закреплённые коммиты, SHA-256 исходников протокола, Cargo.lock, драйвера и результирующего бинарника. Модель контроля: один экземпляр Api, один общий connection pool, параллельные вызовы из отдельных фоновых потоков.

```sh
python3 build.py /path/to/Proteus-desktop /path/to/desktop-target --rustc /path/to/rustc
python3 test_loopback.py
# Успех: {"ok":true,"api_ms":…,"page":{…}}; ошибка: exit 2 с исходным сообщением.
./client http://127.0.0.1:PORT /path/to/saved-session
./client http://127.0.0.1:PORT /path/to/saved-session 50 REVISION
```

Запросу к локальному серверу без авторизации не нужны секреты. Когда синтетический стенд сам задал токен, его принимает переменная `PROTEUS_BENCH_TOKEN`. Токен не передаётся в аргументах командной строки и не сохраняется в отчётах. Клиент принимает только loopback origin.

`test_loopback.py` проверяет, что latest и pinned выбирают верные параметры /history/page, используют bearer и десериализуют настоящий DTO. Два отрицательных теста выполняются параллельно: один не отдаёт заголовки, другой сразу отдаёт заголовки и отправляет байт каждые 460 ms. Оба запроса обрываются по настоящему глобальному дедлайну. Отправка байтов сбрасывает idle-таймер, но не глобальный. Это синтетические проверки клиента, не замеры Core.

Для интеграционного стенда `DesktopApi(origin).page(dir,before=...,revision=...)` делегирует в независимый Rust-процесс. Лимит в 60 s в Python-обёртке страхует только зависание драйвера; реальный ureq возвращает свой ответ или ошибку сам. `api_ms` отмерено вокруг вызова Rust Api, включая проверку/декодирование DTO, но без сериализации обратно в Python. `ms` во внешнем стенде включает также Python↔Rust IPC. Процесс Desktop-драйвера не включается в PSS серверного дерева.
