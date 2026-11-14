# Desktop: старые чаты и потерянное уведомление о выходе Core

Дата: 2026-11-13. Проверены local/origin Desktop HEAD `75bf201764278eac4b50d156650edcf1429101ff`.

Две новые цепочки восстановления, **не повторяют** ранее подтверждённые зависшие `opening`/`sessions_loading`. Production-код не изменялся, публикаций нет. Ни настоящий Core, ни native GPUI не запускались.

## RCS-1 [P2]. Новый Core уже работает, но существующие root-чаты остаются на умершем подключении

### Последовательность

1. Открытый чат A получает `Api` первого собственного backend и его SSE pump. Реальный TCP/SSE stream подключён.
2. Backend process внезапно завершается. Pump получает реальный EOF; `Chat::apply`/`Session::stream_disconnected` ставят `connected=false`. Backend watcher отдельно получает настоящий process exit.
3. `WindowGroup::server_stopped` успешно освобождает global Core slot и сбрасывает `Workspace.api`.
4. Следующее действие, требующее Core, успешно запускает второй backend: **другие port, token и connection_id**. Workspace получает новый `Api`; новый чат B действительно подключается к нему.
5. Пользователь возвращается в A. `open_chat` видит существующий entity и не делает resume. `insert_chat` тоже возвращается до проверки/замены старого `Api`. Результат: A продолжает retry только старого адреса.
6. Даже обычное закрытие и повторное открытие **root chat tab** здесь не заменяет entity: `sync_chats` специально сохраняет владельца root-area, хотя его собственная вкладка закрыта.

Наблюдение: второй backend жив, B connected; A остаётся `connected=false`, его `Api.connection_id` старый; число запросов A ко второму backend равно **0**. Следующая реальная попытка SSE reconnect также заканчивается `Disconnected` на прежнем адресе. Три повтора открытия и close/reopen root tab не вызывают нового resume.

Это не обычный краткий сбой SSE на том же endpoint. Finding относится к **замене собственного процесса Core**, который запускается с новым ephemeral port и токеном. История сессии в этом probe не хранится и не повреждается. Нельзя обещать, что обычное закрытие/открытие root tab исправит ситуацию. Полное пересоздание Workspace/клиента или явный rebind может восстановить её; этот workaround не проверялся как native UI-сценарий.

Отправка из отключённого чата по исходникам останавливается на `!self.session.connected`. UI send не исполнялся в headless adapter: непосредственно проверены состояние подключения, неизменность адресата, отсутствие resume и реальные неуспешные HTTP/SSE обращения старого `Api`.

### Связь исходников

- [Создание Chat с закреплённым Api и pump](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/mod.rs#L236-L261).
- [Pump повторяет обращения через один захваченный Api](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/connection.rs#L154-L201).
- [Exit cleanup меняет только Workspace.api, не Chat](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/windows.rs#L242-L255).
- [Открытие существующего chat entity обходит resume](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L133-L146); [insert_chat также переиспользует entity без сверки connection](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L368-L382).
- [Закрытый root tab не освобождает chat owner](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L604-L608).
- [Send guard отключённой сессии](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/actions.rs#L101-L108).

### Направление исправления

Связать живые Core-чаты с поколением WindowGroup connection. При восстановлении делать resume/rebind соответствующей durable session, заменять Api и старый pump, но сохранять пользовательский composer/drafts и корректно fence-ить поздние callbacks прежнего поколения. Нельзя просто удалить все chat entities: это теряет UI-состояние. Здесь нет проверенного production patch.

## RCS-2 [P2, узкое окно]. Занятый mutex превращает подтверждённый exit в потерянное одноразовое уведомление

### Последовательность

1. Собственный backend реально завершился. `BackendGuard.exited` содержит один отчёт о выходе.
2. В момент UI delivery `core` mutex удерживается другим потоком. Такой lock берётся обычным `drivers::core`, в том числе при возврате существующего Api. Этот обычный критический участок короткий; тест **детерминированно удерживает реальный MutexGuard** именно на время delivery, а не измеряет вероятность гонки в GPUI.
3. `WindowGroup::server_stopped` получает `WouldBlock` от `try_lock` и сразу возвращается. Он не ставит retry и не сохраняет отчёт.
4. `watch_backend` забирает один `recv`, вызывает `server_stopped` один раз и заканчивается. После освобождения mutex повторной retirement нет.
5. Следующий `drivers::core` видит `Some(CoreConnection)` и отдаёт Api уже мёртвого backend, **не проверяя process liveness**. Новые обращения снова не запускают сервер.

Наблюдение: после подтверждённого exit и освобождения mutex пять обращений сохраняют один connection_id, все HTTP `/sessions` заканчиваются ошибкой, число запусков backend остаётся **1**. Workspace.api тоже не сброшен. Контроль без contention освобождает slot и запускает второй работоспособный процесс.

Это другой дефект, чем старый stale-result guard: здесь **само глобальное соединение умершего процесса не выведено из обращения**. Ни opening ticket, ни загрузка списка не нужны для воспроизведения.

### Связь исходников

- [Одноразовая доставка отчёта](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/windows.rs#L174-L191).
- [Безвозвратный return на занятом mutex](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/windows.rs#L221-L234).
- [Последующее переиспользование непустого slot](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/drivers.rs#L19-L33).

Дополнительный контроль подтвердил тот же ошибочный принцип в `has_core_connection`: при удерживаемом mutex он возвращает `false` для текущего connection, после отпускания снова `true`. Это не оформлено отдельным finding, чтобы не размножать следствия одной причины. Возврат `false` для неизвестного из-за contention состояния способен преждевременно отсечь валидный UI completion, но полный такой RPC interleaving здесь не прогонялся.

### Направление исправления

Отделить состояния «другое поколение/нет Core» и «сейчас не удалось прочитать slot». Exit retirement должна гарантированно повторяться или выполняться через безопасный сериализованный путь, не теряя проверку connection_id. **Не заменять вслепую `try_lock` на UI-blocking `lock`:** `drivers::core` удерживает lock во время запуска, который способен долго ждать readiness. Контроль late-old-exit должен продолжать защищать уже установленное новое поколение.

## Проверка и ограничения

Настоящие, неизменённые исходники:

- весь `Api`, HTTP transport/proxy/SSE parser;
- `Backend`, process launch/readiness, child exit watcher и shutdown;
- `connection` с реальным SSE thread/reconnect;
- `proteus-tabs`, `proteus-client-common`, desktop-pinned contracts `5e8b6ae63fd6f50611129b19687b158621359706`.

Весь control flow методов `WindowGroup::{server_stopped,set_core,has_core_connection,core_slot}`, `drivers::core`, `Workspace::{open_chat,insert_chat,sync_chats}`, `Chat::{new,apply}`, `Session::{stream_connected,stream_disconnected}` извлечён без изменения тела; меняется только visibility. `extraction.json` фиксирует строки/хеши. `source-sha256.json` и `source-verified.txt` подтверждают **52** исходных файла; license symlinks материализованы отдельно и обозначены.

Вместо Core используется **собственный synthetic Python HTTP process**, говорящий нужный публичный DTO subset: `/resume`, `/sessions`, SSE heartbeat. Он слушает только loopback, добровольно завершает себя по `/fixture/exit`, не вызывает модель/инструменты и не читает существующие сессии. Сам Desktop Backend запускает его, получает port/token, отслеживает настоящий exit и создаёт replacement. Probe запрещает PROTEUS_BIN, отличный от его `fixture_core.py`.

GPUI `Context/Entity`, window/focus/paint, Chat base-поля и не относящиеся к проверке службы заменены минимальными адаптерами. Native async scheduler не выполняется. Доставка настоящего exit из receiver в полный production `server_stopped` выполняется вручную. Аналогично установка нового Workspace.api моделирует успешный Workspace callback; resume adapter синхронно использует реальный Api, а не production UI job scheduler. Close action представлен его изменением TabLayout + настоящим `sync_chats`, а не кликом native UI. Эти границы не позволяют назвать тест native end-to-end, но network/process break, адресация, lease retirement, reuse decisions и проверяемая state transition не симулируются.

Результаты:

- Новые observations/controls: **5 passed**, 2 desired-invariant tests ignored в основном прогоне.
- Весь focused probe вместе с исходными API/connection/context tests: **17 passed, 2 ignored**, exit 0.
- Отдельный запуск двух желаемых инвариантов: **2 failed, exit 101**, как ожидается на текущем HEAD. Это воспроизведения, не результаты применённого исправления.
- Native GUI, production Core/runtime, нагрузочная вероятность contention, полный Desktop suite и portable не запускались.

## Воспроизведение

Нужны Rust 1.95+ и Python 3. Первый Cargo запуск может потребовать загрузки публичных registry dependencies; при заполненном кэше подходят команды:

```sh
python3 make_probe.py
export PROTEUS_BIN="$PWD/probe/fixture_core.py"
export CARGO_TARGET_DIR="$PWD/target"
cargo test --offline --manifest-path probe/Cargo.toml -- --nocapture
# Ожидаемый exit 101:
cargo test --offline --manifest-path probe/Cargo.toml regression_ -- --ignored --nocapture
```

`probe/runs/` создаёт только синтетические журналы запусков и HTTP requests. Токены не записываются. Архив не содержит target/cache и не является portable-приложением.
