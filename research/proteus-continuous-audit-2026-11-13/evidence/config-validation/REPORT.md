# Proteus Core: успешный Save записывает профиль, который больше нельзя загрузить

Дата: 2026-11-13. Core HEAD: `89997df995df7c39b713e16aba216ecb19c8f497`.
Свежий `git ls-remote origin HEAD` исходного checkout подтвердил тот же HEAD. Изолированная копия: `config-runtime-round12`. Production-код не изменён, публикации нет.

## Подтверждённый дефект, P2

`POST /config/builder` принимает неизвестный ключ slot в `module_config`, возвращает HTTP 200 и сохраняет значение на диск и в live snapshot. Но штатный loader тот же ключ запрещает. Поэтому последующие Save и cold load падают, а watcher показывает reload error.

Минимальный payload на первоначально корректном профиле:

```json
{"module_config":{"unknown_slot":{"unselected":{"audit":1}}}}
```

Дальнейший полностью корректный запрос:

```json
{"permission_mode":"plan"}
```

получает HTTP 400:

```text
unknown module_config slot "unknown_slot"
```

Воспроизведено без параллельного внешнего редактора или гонок. Это отдельная ошибка согласованности validation и persistence, не повтор ранее найденного external edit → Save.

## Причина и связи

1. [Save загружает и валидирует старый профиль](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L154-L162).
2. [Затем произвольно добавляет ключи `module_config` из запроса](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L199-L221). Проверка TOML означает представимость значения, а не допустимость slot. `prepare_assembly` этого ключа также не отвергает.
3. [Новый профиль публикуется и записывается](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L228-L238).
4. При следующем чтении [loader вызывает `validate_module_config_slots`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/loading.rs#L79-L100) и отказывает. Следующий Save не доходит до исправляющего изменения, поскольку начинает с того же loader.
5. [HTTP handler](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/http.rs#L383-L392) действительно возвращает успех первого Save и BAD_REQUEST следующего.

## Прогоны

Три новых диагностических теста: **3 passed**. Они намеренно проверяют наблюдаемое неправильное поведение, это не исправление.

- Настоящий `AgentAppServer` и штатный процессный Python fixture `tests/fixtures/process_commands.py`.
- TOML и JSON: Save OK → ACK/live содержат неизвестный slot → `AppConfig::load` отвергает записанный файл → попытка исправления через Save также отвергнута → штатный watcher публикует reload error.
- Контроль: те же значения под допустимым `tool` сохраняются, читаются холодным loader, последующий Save проходит в обоих форматах.
- Настоящий HTTP router, JSON decode и session-auth helper: неизвестный slot → HTTP 200; следующий корректный permission-mode Save → HTTP 400. Это in-process route test, не реальный сетевой socket.
- Существующий `load_rejects_unknown_module_config_slot`: **1 passed**, подтверждает, что отказ loader является уже закреплённым контрактом.
- `cargo fmt --all --check`, `git diff --check`: проверены отдельно; см. приложенные логи.

Команды (после применения `reproducer.patch` на указанный HEAD):

```bash
CARGO_TARGET_DIR=/tmp/proteus-config-validation-target CARGO_PROFILE_DEV_DEBUG=0 \
  cargo test --locked -p proteus-core --lib audit_round12 -- --nocapture
CARGO_TARGET_DIR=/tmp/proteus-config-validation-target CARGO_PROFILE_DEV_DEBUG=0 \
  cargo test --locked -p proteus-core --lib load_rejects_unknown_module_config_slot -- --nocapture
```

Использован отдельный Cargo target. Проверены реально запущенные уникальные имена тестов. Напрямую запущен scoped Cargo target, поскольку эти тесты используют штатный Python process fixture, а не reference-module, который общий runner собирает вместе с unrelated packages.

## Ограничения и исправление

- Обычная форма Settings, вероятно, не генерирует неизвестный slot: это ошибка backend/API validation для ошибочного клиента, расширения или ручного API-запроса. Не утверждается, что обычный клик в UI воспроизводит её.
- GPUI, реальный HTTP socket, живые модельные провайдеры, полный Rust gate не запускались.
- Cold reload проверен через точный production `AppConfig::load`; целый новый app-server не запускается, поскольку этот prerequisite уже возвращает ошибку.
- Нужна единая semantic validation изменённого `AppConfig` **после** применения request и **до** подготовки/History/persistence. Regression должен требовать отказ первого запроса и неизменные disk/live/history, затем успешный корректный Save.
- Нельзя просто сериализовать live config и прогнать `load` как универсальную проверку: resolved instructions имеют отдельную семантику text/file. Лучше выделить и повторно использовать текущую semantic validation.
- Уже испорченный профиль можно восстановить ручным удалением неизвестного `module_config` slot из исходника. API Save сам себя сейчас исправить не может.
