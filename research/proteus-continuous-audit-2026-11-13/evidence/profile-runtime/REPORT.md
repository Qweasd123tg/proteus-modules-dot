# Proteus: опубликованный профиль расходится с launch-time сервисами

Исследование 2026-11-13. Только изолированная копия и test-only patch. Production-код, пользовательские данные и удалённые репозитории не изменялись; commit/push/PR не выполнялись.

Core: `89997df995df7c39b713e16aba216ecb19c8f497`; официальный process fixture из Modules: `3270dc0f894eaf4d0360306052b806099b8f5351`. Оба upstream HEAD повторно проверены через `git ls-remote`; локальные source checkout совпадают с указанными ревизиями. Три новых воспроизводящих теста демонстрируют два разных launch-time сервиса, пропущенных публикацией профиля.

## 1. P2: hot reload event_log меняет читателя телеметрии, но не writer

**Подтверждено реальным app-server, production watcher, process fake-model и process workflow `coding.single_loop`.** Внешняя правка валидного TOML получает `ModulesReloaded` с новым epoch; reload error отсутствует.

### Смена пути журнала

1. Запустить профиль с `event_log.path = events-a.jsonl`, выполнить обычный turn. Context Map содержит `latest_usage` и `latest_context`.
2. В том же файле профиля заменить путь на `events-b.jsonl`. Дождаться настоящего watcher reload, без прямой подмены внутреннего состояния.
3. Выполнить следующий turn и запросить Context Map.

Наблюдение:

```text
epoch: 1
published config: events-b.jsonl
old log bytes: 8964 -> 17509
new log exists: false
latest_usage: Some -> None
latest_context: Some -> None
diagnostics: event log not found; using session history only
```

Writer продолжает писать исключительно A. Reader уже берёт путь B из нового опубликованного профиля, поэтому статистика контекста исчезает и для нового turn. Это не потеря canonical conversation journal: история сообщений остаётся отдельным источником. После cold launch того же профиля новый turn создаёт B, и Context Map снова получает usage.

### Смена фильтра дельт

Оба направления проходят reload, но filter сохраняет значение с запуска:

| Изменение | Дельты до/после hot reload | Cold control |
|---|---:|---:|
| `persist_deltas: false -> true` | 0 -> 0 | 0 -> 10 |
| `persist_deltas: true -> false` | 10 -> 20 | 20 -> 20 |

Таким образом, включение диагностики не начинает запись, а выключение не прекращает дополнительную запись до перезапуска.

Причина и источники:
- [Writer path и filter фиксируются при launch](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server.rs#L497-L516).
- [Context Map читает новый config.event_log.path](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server.rs#L350-L410).
- [Публикация заменяет assembly/config, но не event sink](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile.rs#L45-L68).

Направление исправления: явно отделить restart-required поля и не сообщать, что они успешно применены live, либо обновлять writer/filter и reader согласованно. При динамической реализации сохранить snapshot текущего turn и определить, где ищется телеметрия более ранних turns после смены пути. Просто переключить reader раньше writer недостаточно.

## 2. P2: новый вопрос после hot reload продолжает использовать старый timeout

**Подтверждено через полный model -> workflow -> `request_user_input` -> app-server forwarder, без прямой регистрации pending question в тесте.** Все вопросы синтетические; внешние сообщения или файловые действия не исполнялись.

1. Запустить профиль с `app_server.approval_timeout_ms = 50`.
2. Изменить значение на `0` (без timeout) и дождаться `ModulesReloaded`.
3. Только после reload запустить новый turn, в котором fake-model вызывает штатный `request_user_input`.
4. Не отвечать на вопрос.

Опубликованный config содержит `0`, однако приходит `UserInputResolved` через **51 ms**, pending исчезает и tool получает пустой ответ. Это не сохранение таймера вопроса, начавшегося до reload: вопрос создан уже после публикации.

Cold control с тем же config `0`: вопрос остаётся pending после 200 ms и turn не завершён; затем тест явно отвечает через `respond_user_input`, чтобы штатно закончить сценарий.

Причина и источники:
- [Timeout один раз извлекается при launch](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server.rs#L518-L525).
- [Один launch-time Duration передаётся обоим forwarders](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server.rs#L572-L583).
- [User-input forwarder использует захваченный timeout для всех новых запросов](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/user_inputs.rs#L32-L55).
- [Expiry завершает вопрос пустым ответом](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/user_inputs.rs#L125-L140).

Та же конструкция видна в approval forwarder, но отдельный permission-approval end-to-end сценарий здесь **не запускался**. Подтверждённый вывод относится к user input. Направление исправления: новые запросы должны фиксировать timeout актуальной опубликованной настройки, либо поле должно явно требовать restart. Уже pending запросы требуют отдельно выбранной стабильной semantics.

## Проверки и ограничения

Реальны reader, fingerprint/debounce watcher, assembly preparation/publication, event log, Context Map, user-input forwarder, process model/workflow/context, холодный повторный launch. Модель локальная `fake`; внешние API, живые credentials и GUI не использовались. Это не доказательство проблем model provider и не полный аудит всех профилей.

`repros.patch` добавляет только тестовый модуль и его подключение. Assertions фиксируют наблюдаемое неверное поведение как reproducer; после исправления их нужно заменить правильными инвариантами. Использован собственный `CARGO_TARGET_DIR`, исключающий артефакты параллельных audit checkout.

Команда проверки на чистом pinned Core после применения patch:

```sh
export PROTEUS_TEST_REFERENCE_MODULE=/path/to/current/proteus-reference-module
cargo test --offline --locked -p proteus-core --lib app_server::profile_watch -- --nocapture
```

Полный workspace gate и production fix не выполнялись. Финальный target: **6 passed, 0 failed**, включая 3 новых reproducer и 3 существующих watcher-сценария; лог `profile-watch-suite.log`. `git diff --check` и применение patch к чистому pinned checkout проверены отдельно.

Контракт hot reload описан как применение всего профиля в [configuration.md](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/configuration.md#L1477-L1492); [timeout=0 документирован как отсутствие deadline](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/configuration.md#L1381-L1395).
