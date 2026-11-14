# MCP catalog: обычное включение сервера блокирует обновление и удаление из каталога

2026-11-13. Новый ограниченный P2 workflow-дефект, не packaging и не ранее найденный wrapper inventory. Production не изменён, публикаций нет.

## Условие и результат

Каталог поставляет валидный `server.json` с `enabled=false`. Пользователь устанавливает сервер, затем включает его штатным переключателем на странице MCP и сохраняет профиль. После этого каталог отказывается как обновлять, так и удалять сервер, считая его изменённым вручную:

```text
Update: Сервер изменён вручную; сначала удалите его на странице MCP
Remove: Сервер изменён вручную; удалите его на странице MCP
```

Даже повторное выключение тем же переключателем не восстанавливает работу обновления. Обход действительно есть: удалить подключение на странице MCP и установить заново. Потери данных, отказ самого работающего MCP-сервера или проблема всех каталогов не заявляются. Условие касается серверов, изначально поставляемых выключенными.

## Подтверждённая цепочка

1. Неизменённые `install::prepare` и `install::connect` Desktop читают синтетический каталог и формируют payload с `enabled=false`.
2. Настоящий Core HTTP `/config/builder` принимает установку: **200**.
3. Неизменённые `Draft::from_snapshot`, `Draft::set_mcp("demo", true)` и `Draft::changes` формируют ровно то изменение, которое вызывает штатный UI switch. Настоящий Core сохраняет его: **200**, запись `enabled=true` подтверждена также физическим TOML.
4. Повторно читается настоящий snapshot Core, затем выполняется каталоговый `connect` с новой версией и старым receipt. Получена ошибка выше до HTTP-запроса; draft не повреждён.
5. `disconnect` с тем же receipt также отклонён. Дополнительный `set_mcp(false)` оставляет поле сервера `enabled=true` и записывает имя в disabled-list, поэтому повторный update всё ещё отклонён.

Два итоговых повтора в новых HOME/workspace прошли одинаково: `run-2.log`, `run-3.log`. Итоговые fixture-директории:
- `run-1794580709438676269`;
- `run-1794580710619259242`.

Первый подготовительный `run-1.log` также воспроизвёл результат, но использовал другой ранее собранный Core binary; основной вывод опирается на два последующих прогона с уже проверенным бинарником.

### Контроли

- Поставленный выключенным сервер без пользовательского toggle обновляется успешно и остаётся выключенным.
- Сервер, поставленный включённым, после обычного выключения обновляется успешно и остаётся выключенным; после включения также обновляется успешно.
- Настоящее изменение `command` продолжает корректно блокировать перезапись.
- Неуспешные update/remove не изменяют draft.

## Root cause

Receipt хранит исходный целый `ConfiguredMcpServerConfig`. Обычное включение переводит его локальное поле `enabled` из false в true, но не обновляет receipt. В `install::connect` два сравнения `current == old`, а в `disconnect` такое же полное сравнение, не отделяют пользовательский on/off state от вручную изменённой идентичности/команды. У серверов с начальным true обычное выключение хранится только в `disabled_mcp_servers`, поэтому ошибка асимметрична.

Проверенные HEAD через GitHub:
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`;
- Core `89997df995df7c39b713e16aba216ecb19c8f497`.

Источники:
- [Штатный MCP switch вызывает set_mcp](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/mcp.rs#L150-L164).
- [set_mcp меняет enabled при включении, но не возвращает false при выключении](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/settings/addons.rs#L54-L80).
- [Полное сравнение receipt перед обновлением](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/catalog/install.rs#L202-L235).
- [Аналогичный отказ удаления](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/catalog/install.rs#L243-L255).

## Направление исправления

Разделить проверяемую идентичность/параметры catalog binding и пользовательское включение. При замене сохранять эффективный on/off state, не снимая защиту от реальных ручных изменений `command`, args, env и cwd. Просто проигнорировать `enabled` при сравнении недостаточно: новый `server.json` с false снова выключит ранее включённый пользователем сервер. Нужен regression на установку false → UI enable + Save → update, и контроль настоящего ручного изменения команды.

## Границы доказательства

Настоящие: Core HTTP/profile persistence, чтение настоящих contract DTO, Desktop prepare/connect/disconnect/Draft functions, локальные filesystem операции, запуск простого MCP fixture (initialize + пустой tools/list). Нет модели, provider API, внешней сети во время repro, чужих профилей или инструментов MCP с побочными эффектами.

Headless probe, а не native GUI/click. UI switch сопоставлен с реальным вызовом функции по исходникам. Source download/build, полный Desktop/Core gate и packaging не запускались. Проверяемые MCP ветви не переписаны; лишь неиспользуемые source-build, extension-manifest и process-component ветви заменены fail-fast заглушками для сборки вне GPUI. `make_probe.py` показывает все замены, `source-hashes.json` содержит SHA256 оригиналов.

Core binary SHA256 итоговых прогонов: `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180` (повторно использован проверенный бинарник предыдущего deployment repro, новая сборка Core не делалась).

## Повтор

```sh
python3 make_probe.py --desktop /path/Proteus-desktop --core /path/Proteus-core
CARGO_TARGET_DIR="$PWD/target" cargo build --manifest-path probe/Cargo.toml
python3 repro.py --core /path/Proteus-core --core-binary /path/built/proteus
```

В текущей среде сборка probe выполнена offline. Все проверки намеренно утверждают наблюдаемое дефектное поведение, их успех не означает исправления. Для будущего regression ожидания update/remove следует инвертировать.
