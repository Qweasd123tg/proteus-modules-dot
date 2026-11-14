# MCP settings: добавление аргумента меняет уже существующие argv и env

2026-11-13. Новый P2-дефект Desktop → профиль → Core MCP process launch. Не rename-state, schema-isolation или catalog-toggle. Production не изменён; публикаций нет.

## Воспроизводимый сценарий

Работающий MCP настроен с CLI-аргументами `--empty`, `""`: явная пустая строка — полноценный аргумент процесса. Пользователь открывает поле Args в Settings и добавляет две строки `--tag`, `new`, не изменяя старые значения.

Desktop удаляет пустой аргумент из всего списка. До правки процесс получал:

```json
["--empty", ""]
```

После правки и Save получает:

```json
["--empty", "--tag", "new"]
```

Окончательная UI model validation возвращает **0 ошибок**, Save отвечает **HTTP 200**, повреждённый список записывается в TOML. Проверочный MCP теперь завершает запуск, потому что у `--empty` больше нет его значения. Раньше в `/addons` был `fixture__echo`, после Save tools пусты и появляется initialize error. Реальный сервер с позиционными аргументами может вместо ошибки продолжить работу с изменёнными параметрами.

Это не ограничение Core или ОС. Контрольный structured payload с корректным добавлением `--tag`, `new` сохраняет пустую строку, Save тоже возвращает 200, тот же MCP продолжает успешно регистрировать tool.

## Одна потеря точных значений, четыре варианта

Все случаи проверены неизменённым production Desktop model layer и настоящим Core HTTP / stdio запуском, каждый в отдельном HOME и workspace.

| Изменение через поле | Старое нетронутое значение | Что получает новый процесс |
|---|---|---|
| Добавить две Args-строки | `--empty`, `""` | пустой argv исчез; MCP не запускается |
| Добавить две Args-строки | `"  alpha  "` | `"alpha"` |
| Добавить две Args-строки | один argv `"first\nsecond"` | два argv `"first"`, `"second"` |
| Добавить `EXTRA=new` в Env | `PREFIX="  synthetic-prefix  "` | `PREFIX="synthetic-prefix"` |

В каждом случае конечная validation=0, Save=200, сохранённый профиль равен отправленному ошибочному payload. Fixture журналирует только синтетические argv и PREFIX, так что результат наблюдается на настоящей process boundary, а не только в DTO.

**Контроли:**
- `ordinary_control`: обычный непустой argv без краевых пробелов сохраняется при добавлении аргумента;
- `api_control`: тот же `--empty`, `""` и тот же synthetic server работают после корректного structured append;
- изменение другого поля (`TimeoutMs`) сохраняет исходные Args и Env без потерь;
- передача **исходного отображаемого текста** назад в `set_mcp_text` уже делает draft dirty для четырёх проблемных случаев, но не для ordinary control. Следовательно, это нарушение round-trip, а не намеренное изменение старых значений.

## Доказанная цепочка

1. Получен настоящий Core `/config/builder` snapshot.
2. `Draft::from_snapshot` и `mcp_text` создают ровно то исходное значение, которое использует редактор.
3. `Draft::set_mcp_text` обрабатывает изменённый текст; `mcp_problems` не обнаруживает ошибок; `Draft::changes` строит штатный request.
4. Настоящий `/config/builder` принимает request; проверяются физический TOML, `/addons` и lifecycle log дочернего Python MCP.
5. На такой же baseline выполняется structured control без потерь.

Три полных повтора финального harness, по шесть HTTP-сценариев, итого **18 Save**:

- `run-1794581986934612773`;
- `run-1794582005966312509`;
- `run-1794582008213894924`.

`verified-1.log` — `verified-3.log`, `verified-runs.json` и каждый `results.json` фиксируют результаты. `repro.py` намеренно утверждает текущую ошибку. Отдельный `expected_invariant.py` проверяет желаемое сохранение значений и на текущем коде ожидаемо падает по четырём инвариантам; `expected-invariant.log` приложен. Успешный diagnostic repro не означает исправления.

## Причина и исходники

- [Desktop сериализует Args через `join("\n")`, Env через `KEY=VALUE` строки](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/settings/mcp.rs#L190-L208).
- [Args parser делает `trim()` и отбрасывает все пустые строки; Env parser делает `trim()` существующих значений](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/settings/mcp.rs#L261-L290). Это формат с потерями для корректных process arguments/environment.
- [Неизменённый callback textarea](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/mcp_editors.rs#L74-L88) отправляет полный текст на каждом Change в [этот model setter](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/mcp_editors.rs#L124-L140).
- [Core передаёт полученные строки в ProcessSpec без дополнительной trim/split обработки](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/mcp.rs#L11-L21). Потери происходят до Core, не в process host.
- [Discovery failures изолируются по серверу](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/tools/mcp.rs#L120-L132), поэтому сломанный запуск не откатывает Save. Эту согласованную runtime-семантику не нужно менять ради починки UI.

## Направление исправления

Сделать представление Args и Env обратимым: отдельные структурированные строки/значения или явно поддерживаемое escaping/JSON, которое сохраняет пустые argv, краевые пробелы и newline внутри значения. Не трактовать argv как shell-command строку. Не использовать один normalizing parser для имён env_allowlist и точных значений Args.

Если текущая форма не умеет показывать некоторые корректные значения, нельзя молча пересохранять их в ином виде при редактировании соседнего элемента. Нужен явно доступный lossless editor либо предупреждение до изменения.

Регрессии: `parse(render(value)) == value`; добавление/удаление соседнего элемента сохраняет остальные байты; round-trip после Undo; UI callback → Save → реальные argv/env. Не ограничиваться тестами обычных непустых слов.

## Версии и ограничения

Повторно сверены upstream `main` через подключённый GitHub REST API:
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`;
- Core `89997df995df7c39b713e16aba216ecb19c8f497`.

Probe компилирует полные **неизменённые** `draft.rs`, `addons.rs`, `mcp.rs` с настоящими Core contract DTO. Каждый файл сравнен побайтово с tracked HEAD. Приложены `source-hashes.json`, `source-verification.txt`, `upstream-heads.json`. Отдельный Cargo target исключает подмену тестового артефакта из соседнего checkout.

Core binary повторно использован из проверенного deployment аудита, SHA256 `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`. Финальный probe SHA256 `5138f6df0635804aed96b83be2ec9972fdb86835843d82f59ae4211402ea61bb`.

Нет native GPUI кликов: источник UI callback связан с выполненным неизменённым model layer; текст и process effects проверены headless. Нет моделей, сетевых MCP, реальных credentials или пользовательских сессий. Full Desktop/Core gate не запускался. Ни production, ни remote не менялись.

В ранней версии только локального harness найден race Python reader closure при переходе к следующему сценарию: старый reader мог положить EOF в новую очередь. Это не ошибка Proteus. Reader получил захваченные per-process параметры и join при завершении; все приведённые финальные 18 сценариев выполнены после исправления harness. Ранние неполные запуски не включены в архив доказательств.

## Повтор

```sh
python3 make_probe.py --desktop /path/Proteus-desktop --core /path/Proteus-core
CARGO_TARGET_DIR="$PWD/target" cargo build --offline --manifest-path probe/Cargo.toml
python3 repro.py --core /path/Proteus-core --binary /path/built/proteus
python3 expected_invariant.py run-.../results.json  # expected exit 1 before fix
```

Для offline build нужны cached dependencies. Core path нужен также для штатного Python component runtime и allow-all policy fixture. Workflow не вызывается, ни один turn не стартует.
