# MCP: посимвольное переименование меняет переключатели двух серверов

2026-11-13. Новый P2 workflow-дефект Desktop → Core. Не catalog receipt/toggle и не schema-isolation. Production не изменён, публикаций нет.

## Воспроизводимый пользовательский сценарий

В профиле два сервера: `db` выключен обычным UI-переключателем, `db2` включён. Обе записи имеют `enabled=true`, а `addons.disabled_mcp_servers=["db"]`, как после штатного выключения Desktop.

1. Пользователь переименовывает `db` в `db20`, дописывая сначала `2`, затем `0`.
2. Промежуточное имя `db2` временно конфликтует со вторым сервером. UI показывает проблему, но продолжает редактирование.
3. Итоговое имя `db20` уникально, ошибок проверки больше нет.
4. После Save **ранее выключенный сервер `db20` включается**, а **неизменявшийся `db2` выключается**.

Даже обратное редактирование `db20 → db2 → db` возвращает исходные имена, но оставляет переключатели перевёрнутыми. Draft остаётся dirty только из-за disabled-list. Это не ожидаемое последствие переименования, и на сервере нет способа отличить ошибочный payload от намеренного переключения.

Контроль: одношаговая замена имени `db → db20` (например, замена всего текста) сохраняет `db20=off, db2=on`. Итог зависит от промежуточных текстов, а не от окончательного имени.

## Подтверждённая цепочка

- В headless probe скомпилированы **полные неизменённые** Desktop `src/settings/draft.rs`, `addons.rs`, `mcp.rs` и настоящие Core contract DTO. Проверяемые функции не переписаны и не заменены заглушками.
- `Draft::from_snapshot` получает настоящий `/config/builder` snapshot Core.
- Вызываются ровно `Draft::set_mcp_text(0, McpText::Name, ...)` на последовательности значений, которую штатный input передаёт на каждом Change.
- `mcp_problems` после конечного имени возвращает пустой список. `Draft::changes` формирует обычный payload.
- Настоящий Core `/config/builder` отвечает **200**. Физический TOML и `/addons` подтверждают сохранённую перестановку состояний.
- Журнал настоящих синтетических stdio MCP-процессов подтверждает: до Save `original_db` не запускался; после stepped/undo Save запускается именно он. При прямом rename контроле он остаётся выключен.

Три полных одинаковых повтора в независимых HOME/workspace:

- `run-1794581466190848924`;
- `run-1794581492141944819`;
- `run-1794581493787132474`.

В каждом три HTTP-сценария:

| Путь редактирования | После Save | Новый запускаемый процесс |
|---|---|---|
| `db → db20` | `db20=off`, `db2=on` | existing_db2 |
| `db → db2 → db20` | **`db20=on`, `db2=off`** | **original_db** |
| `db → db2 → db20 → db2 → db` | **`db=on`, `db2=off`** | **original_db** |

Все Save возвращают 200. Все конечные names проходят проверки. Все данные синтетические; единственный эффект MCP fixture — запись собственного lifecycle log.

## Причина

[`set_mcp_text`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/settings/mcp.rs#L110-L122) сразу заменяет имя и переносит disabled-list через `follow_rename`. [Перенос](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/settings/mcp.rs#L177-L186) проверяет лишь наличие **старого** имени у другого profile server, но не идентичность строки/владельца состояния.

На `db → db2` disabled-list превращается из `[db]` в `[db2]`, временно отключая обе совпавшие записи. На `db2 → db20` функция видит вторую запись с именем `db2` и прекращает перенос: disabled остаётся на чужом сервере, а переименованный включается.

[UI действительно вызывает изменение на каждом InputEvent::Change](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/mcp_editors.rs#L95-L100), передавая текст непосредственно в [set_mcp_text](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/mcp_editors.rs#L124-L140).

Core после Save корректно [применяет disabled-list к каждому имени](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/module_catalog/tools.rs#L74-L83). Дефект возникает раньше, при редактировании Desktop.

## Направление исправления

У состояния on/off должна быть стабильная связь с редактируемой строкой, а не с каждым промежуточным текстом. Можно держать raw name отдельно и атомарно применять валидный rename либо сохранять row identity и строить disabled-list по финальному согласованному draft. Простого запрета перезаписывать already-used name недостаточно: нужно сохранять оба состояния при временной коллизии, исправлении ошибки, обратном вводе и удалении строк.

Regression должен проверять пошаговый ввод через имя существующего сервера, возвращение исходного текста и прямую замену; состояния off/on и off/off; пакетные имена; финальный Save и payload. Не переносить эту логику в Core и не отключать duplicate-name validation.

## Версии и ограничения

Повторно сверенные upstream main:
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`;
- Core `89997df995df7c39b713e16aba216ecb19c8f497`.

Core binary повторно использован из уже проверенного deployment аудита, SHA256 `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`. Probe построен offline в отдельном target, SHA256 `d2d6b29c51cc95f5b65f75948d056e19daeb4de0640abe05d2dda30a3aceef3f`. `source-hashes.json` фиксирует источники.

Нет native GPUI кликов: доказательство связывает исходник штатного UI callback с выполненными неизменёнными model-layer функциями и настоящим HTTP/runtime. Нет моделей, внешних API, настоящих credentials. Full Desktop/Core gate не запускался, production не менялся. Случай `enabled=false` без disabled-list не объявляется затронутым: проверен именно штатный Desktop off-state.

`repro.py` намеренно утверждает текущую ошибку. Для желаемого поведения есть отдельный `expected_invariant.py`, который на этих данных ожидаемо падает; успешный diagnostic run не означает исправления.

## Повтор

```sh
python3 make_probe.py --desktop /path/Proteus-desktop --core /path/Proteus-core
CARGO_TARGET_DIR="$PWD/target" cargo build --offline --manifest-path probe/Cargo.toml
python3 repro.py --core /path/Proteus-core --binary /path/built/proteus
python3 expected_invariant.py run-.../results.json  # expected exit 1 before fix
```

Для offline build нужны cached dependencies. `--core` также предоставляет штатный Python component-runtime и allow-all policy fixture. Turn не запускается.
