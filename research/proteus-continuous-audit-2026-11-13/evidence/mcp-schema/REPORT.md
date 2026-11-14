# MCP: ошибка схемы одного сервера блокирует весь cold launch

2026-11-13. Новый ограниченный P2-дефект изоляции ошибки discovery. Core main и локальный checkout сверены: `89997df995df7c39b713e16aba216ecb19c8f497`. Production не менялся, публикаций нет.

## Что подтверждено

Если один enabled MCP отдаёт `tools/list` с JSON-объектом `inputSchema`, содержащим невалидную JSON Schema, например `properties.message.type = "invalid-type"`, Core завершает холодный запуск до `http_ready`. Хороший независимый MCP-сервер тоже становится недоступен, хотя его discovery успешно. Это не паника: startup штатно возвращает ошибку всей сборки.

```text
Error: tool 'bad__echo' has invalid input schema: "invalid-type" is not valid under any of the schemas listed in the 'anyOf' keyword
```

При добавлении того же сервера через настоящий HTTP `/addons` Core отвечает **400**. Профиль не повреждается, прежняя конфигурация сохраняется. Холодный запуск уже существующего профиля с таким сервером не проходит.

Это поведение контрастирует с соседней error boundary: неправильная форма `inputSchema` (массив вместо JSON-объекта) и неправильный `initialize` изолируются корректно. В этих случаях Core стартует, `/addons` содержит ошибку только плохого сервера и зарегистрированный `good__echo`. Сохранять подключение с неправильной wire-формой через `/addons` можно, ответ **200**, ошибка видна в его состоянии.

## Проверки и контроли

Реальный Core executable, реальный stdio MCP и HTTP loopback. Три одинаковых полных повтора в отдельных HOME/workspace:

- `run-1794581176176891293`;
- `run-1794581223547742619`;
- `run-1794581225440661254`.

В каждом прогоне:

| Вход | Наблюдение |
|---|---|
| Два правильных MCP | Core готов, tools доступны в registry snapshot |
| Хороший MCP + плохой initialize | Core готов, хороший tool зарегистрирован, плохой сервер имеет error |
| Хороший MCP + `inputSchema=[]` | Core готов, хороший tool зарегистрирован, плохой сервер имеет error |
| Хороший MCP + неверный nested schema type | Core startup exit 1, HTTP не готов |
| Тот же malformed-schema MCP выключен | Core готов, хороший tool зарегистрирован |
| POST /addons с `inputSchema=[]` | 200 и server-local error |
| POST /addons с неверным nested schema type | 400, сохранённый профиль не меняется |

`repro.py` проверяет наблюдаемое дефектное поведение: его успешный exit не означает исправления. `expected_invariant.py` проверяет желаемую изоляцию и намеренно падает на текущих данных.

## Причина

- [`register_mcp_tools`, строки 119–130](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/tools/mcp.rs#L119-L130): ошибки spawn/initialize/list/conversion превращаются в `state.error` и пропускают только этот сервер.
- [Там же, строки 132–143](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/tools/mcp.rs#L132-L143): регистрация в общем registry идёт после этого catch; ошибка пробрасывается через `?` наружу.
- [`mcp_tools_from_list`, строки 28–39](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/tools/mcp/discovery.rs#L28-L39): schema переносится как JSON, семантической проверки тут нет.
- [`ToolRegistry`, строка 346](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/contracts/tool.rs#L338-L346): именно регистрация компилирует validator и возвращает ошибку невалидной схемы.
- [Документированная граница изоляции](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/configuration.md#L1212-L1217) обещает изолировать ошибки start/handshake/list; блокирующим исключением отдельно названа name collision. В repro коллизии имён нет.

## Направление исправления

Проверять все discovered schemas внутри server-local preparation до изменения общего registry. При невалидной schema не регистрировать ни одного tool этого сервера, вернуть его error, продолжить независимые MCP. Не ловить слепо все ошибки register: name collision должен остаться документированной блокирующей ошибкой. Не оставлять частично зарегистрированный сервер, когда невалидным оказался второй tool. Нужны regressions: invalid nested schema; valid tool затем invalid tool; independent good server; disabled server; collision сохраняет прежнюю семантику.

## Границы

Нет model calls, provider API, чужих данных, сети вне loopback, MCP side effects или GUI. Model-free workflow используется только для сборки profile, turn не запускается. Проверено наличие tools в настоящем `/addons` registry snapshot, исполнение `good__echo` не заявляется. Полный Core gate и новая сборка в этом проходе не выполнялись: использован уже проверенный production executable предыдущего deployment аудита. SHA256: `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`.

Не считаются новыми багами: задокументированное завершение всей MCP generation при cancel/timeout; snapshot-health вместо непрерывного health мониторинга; name collision как fatal error. Catalog enabled toggle и ACP session-overlay watcher сюда не входят.

## Повтор

```sh
python3 repro.py --core /path/Proteus-core --binary /path/built/proteus
python3 expected_invariant.py run-.../results.json  # ожидаемый exit 1 до исправления
```

`--core` нужен для штатных Python component-runtime/policy fixtures. Профили, loopback-token и данные полностью синтетические. Инструкция не требует внешнего MCP или настоящих credentials.
