# Desktop projection, pass 8

## P2: временная ошибка загрузки вложения переживает восстановление соединения

Desktop HEAD/main: `75bf201764278eac4b50d156650edcf1429101ff`.
Core HEAD/main ранее сверены: `89997df995df7c39b713e16aba216ecb19c8f497`.

Условие: изображение уже сохранено в истории; первый HTTP fetch превью возвращает временную ошибку (сброс соединения, timeout или 5xx). Ожидание: после восстановления соединения/по явному retry сохранённое изображение снова доступно. Факт: для того же объекта Api, сессии, image ID и масштаба `SentImages::missing()` больше не включает изображение в очередь.

Связь исходников:
- `src/ui/chat/images/schedule.rs:99-126`: transport и decode ошибки без различения становятся `Stored::Failed`.
- `src/ui/chat/images.rs:117-118`: Failed пропускается без повторной попытки, срока жизни или retry-флага.
- `src/ui/chat/pump.rs:74-84`: восстановление SSE обновляет Session и config, но не сбрасывает ошибочные previews.
- `src/connection.rs:156-194`: reconnect повторяет `api.events` на том же Api; `src/api/mod.rs:30-56`: connection_id назначается только в Api::new.
- `src/ui/chat/images.rs:65-77` и `pump.rs:265-278`: reconciliation сохраняет slot, пока image ID остаётся в отображаемой истории. Новый snapshot не лечит Failed.
- `src/ui/chat/images.rs:226-237`: Failed отрисовывается ImageOff с tooltip, без кнопки retry.

Воспроизведение: `source /workspace/shared/proteus-toolchain/env.sh; python3 run_image_probe.py`.

Результат: 4/4 tests passed, подтверждающие текущий дефект и контроли. За 100 повторных проверок того же ключа retry не возникает; retain authoritative snapshot сохраняет Failed. Изменение connection ID/размера thumbnail либо eviction с возвращением, напротив, снова делает image missing.

Граница evidence: тест компилирует неизменённый production source `images.rs:23-140`, с minimal stubs для пустого successful bitmap cache, ImageRef/Entry и очереди. Он проверяет настоящие `missing`/`retain`, но не запускает GPUI, HTTP или пользовательский reconnect end-to-end. Связь со сбоем HTTP и SSE reconnect подтверждена чтением исходников, а не GUI прогоном. Это баг восстановления превью, не потеря оригинального вложения.

Направление исправления: различить transport/decode ошибки; для временных ошибок добавить ограниченный retry/backoff или сброс при reconnect плюс явное действие «повторить». Не превращать каждый render в горячий retry loop. Production не менялся, remote не публиковался.

## P2: canonical message identity не является уникальным UI row identity

**Проверенное последствие: «Копировать ответ» может молча вернуть только текст до tool-call, потеряв текст после него.**

Законный canonical assistant message `[Text("Before tool"), ToolCall, Text("After tool")]` превращается Core в три строки. Обе text-строки несут один `message_id`.

Связь исходников:
- Core `app_server/transcript.rs:33-65,231-250`: flush при ToolCall/ToolResult/HostedToolActivity делит текст, а каждый flush использует `message.id`.
- Core `app_server/transcript/journal.rs:359-390`: актуальная journal проекция пользуется этим же append_transcript_parts, не только legacy helper.
- Modules `model/model-pack/src/adapters/anthropic/{response.rs:30-88,stream.rs:288-335}`: ordered text/tool blocks собираются в один CanonicalMessage. Тестовый вход не требует некорректного wire формата/дубликата provider call ID.
- Desktop `src/transcript/mod.rs:79-103,511-520`: reset сводит identity в HashMap по message_id. Из двух старых строк остаётся ключ последней, который при reset передаётся первой новой строке.
- Desktop `src/transcript/mod.rs:154-169`: append_page для каждой новой строки берёт первый known entry с этим message_id, создавая два одинаковых Entry.key.
- Реальный paging entry point: `src/ui/chat/history.rs:241-263,288-298`. Newer page может пересекать начало live-tail, поэтому код overlap достижим.
- Desktop `src/ui/chat/turn_copy.rs:102-150`: copy plan ищет end_key через `.position()`, т.е. попадает на первую строку с повторённым key, и не включает последнюю часть ответа. `turn_footer.rs:49-58,73-78` передаёт end_key в этот метод.

Результаты 5 новых тестов:
1. Реальный Core projector выдаёт два text rows с одним message_id.
2. Одинаковый snapshot перестраивает keys на каждом reset: `[1,2,3] -> [3,2,6] -> [6,2,9] ...`, вместо `Change::None`.
3. Страница истории с live-overlap получает keys `[1,2,1]` при разных текстах первой и последней строки.
4. Настоящий production `turn_copy_plan` / Parts (с минимальным Chat/API/History shell, ветка истории не вызывается, т.к. user boundary есть в fixture) возвращает `Before tool`, ожидается `Before tool\n\nAfter tool`.
5. Контроль с отдельными canonical message IDs сохраняет ключи и возвращает `Change::None`.

Repro: `source /workspace/shared/proteus-toolchain/env.sh; python3 run_transcript_probe.py` (поддерживает `DESKTOP_ROOT`, `CORE_ROOT`, обычный `CARGO_TARGET_DIR`). Для текущей среды использован заранее существующий cache target, но новый уникальный package `desktop-projection-round8-probe`; в логе проверены имена всех новых тестов, stale binary не использовался.

Граница evidence: compiled production projection/reset/append_page/copy logic, не GPUI и не реальный clipboard. Обрезание copy payload воспроизведено. UI flicker, scroll jumps или panic не заявлены как проверенные. Производственный код и remote не менялись.

Направление исправления: задать устойчивый row identity, различающий сегменты одного canonical message; не считать message_id уникальным для rows. Исправлять reset и overlap paging вместе, проверить copy endpoint, идентичный snapshot и page boundary внутри одного сообщения. Новый UUID на каждый snapshot уберёт collision, но сломает стабильность, это не подходящее исправление.

## Общие проверки и ограничения

- Final isolated suite: **69 passed, 1 ignored** (installed Codex app-server smoke сознательно не запускался), 0 failed. Это subset, включённый в минимальный probe package, а не полный Desktop/Core workspace gate.
- Отдельный image state probe: **4 passed**.
- Новые row identity/copy симптомы: **5 passed** в observation/reproducer tests; tests утверждают наличие текущего дефекта, не его исправление.
- В конце сверены remote main: Desktop `75bf201764278eac4b50d156650edcf1429101ff`, Core `89997df995df7c39b713e16aba216ecb19c8f497`.
- Не проводился полный построчный охват всего Desktop/Core; просмотрены transcript/projection/history/copy/image-recovery/child read-only boundaries. Нет заявлений о GUI e2e, живом provider run или полном green gate.
