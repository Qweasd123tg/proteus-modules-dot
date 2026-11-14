# Core: ACP/CLI → runtime/profile/workflow boundaries

Дата: 2026-11-13. Источник: `Proteus-harness/Proteus-core`, main `89997df995df7c39b713e16aba216ecb19c8f497`. Remote main повторно проверен после прогонов, SHA не изменился.

Изолированная копия: `/workspace/shared/core-acp-cli-chain`. Production-код не менялся: `reproduction.patch` содержит только четыре новых regression-теста внутри test-модулей. Никаких commit, push, PR или публикаций. Дополнительные Python probes находятся только в evidence-каталоге. Использованы официальные fixture-компоненты этого проекта, временные каталоги, локальные процессы и PTY; реальные API моделей, аккаунты и платные запросы не использовались.

## 1. P2: watcher принимает session overlays за изменение профиля и стирает их

Это **одна группа root cause с двумя воспроизведёнными проявлениями**, не два независимых бага.

ACP `session/new` добавляет editor-provided MCP servers в копию AppConfig и передаёт её `AgentAppServer::launch` вместе с исходным config_path. Watcher берёт fingerprint из этой effective config, но затем читает исходный профиль с диска, где editor servers отсутствуют. Первые два poll принимают несовпадение за смену профиля, публикуют чистый disk config и удаляют MCP из следующего epoch. Файл при этом не менялся, reload_error отсутствует.

Тест использует настоящий `State::new_session`, настоящий MCP discovery и штатный Python MCP fixture:

```
immediately after session/new: editor enabled=true,
  tools=[editor__echo, editor__fail, editor__delay_write, editor__oversize], error=None
after 900 ms idle: mcp_servers=[]; epoch 0 -> 1; reload_error=None
```

Тот же стык затрагивает CLI `--plan`, `--auto` и `--permission-mode`: `run_cli` записывает флаг в AppConfig до launch. При disk default Normal watcher считает Plan→Normal или Auto→Normal реальным изменением default и снимает выбранный пользователем режим.

Это проверено не только unit-тестом, но и собранным с указанного SHA CLI через реальный stdio protocol:

```
--plan: Plan -> Normal, epoch 0 -> 1, profile_unchanged=true
--auto: Auto -> Normal, epoch 0 -> 1, profile_unchanged=true
no flag: Normal -> Normal, epoch 0 -> 0, profile_unchanged=true
```

Никакие инструменты в этом mode probe не выполнялись. Утрата режима подтверждена; отдельный сценарий выполнения запрещённых пользователем действий не проверялся и не заявляется.

Источники:
- [ACP merges request MCP](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/acp/input.rs#L26-L57)
- [ACP passes merged config plus original path](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/acp/mod.rs#L215-L229)
- [Watcher baseline and reload](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile_watch.rs#L60-L155)
- [CLI writes launch mode into config](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/main.rs#L148-L157)
- [Changed config mode becomes runtime mode](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile.rs#L41-L62)

Исправление: различать published disk baseline и session overlay. CLI mode следует накладывать через session override, не менять baseline. ACP MCP overlay должен сохраняться отдельно и объединяться с новым baseline при каждом reload. Простого пропуска первого reload недостаточно: последующая реальная правка файла снова потеряет overlay.

Артефакты: `repros.log`, `repeat-{1,2,3}.log`, `cli_mode_probe.py`, `cli-mode-wire.log`. Оба Rust repro повторены ещё три раза, одинаковый результат. ACP проверен на уровне настоящего session handler и runtime, не через конкретный GUI-редактор.

## 2. P2: hot reload публикует профиль, который холодный старт отвергает, и ломает все slash-команды

`launch` вызывает `command_catalog()`, проверяя объединение host/tool/profile команд. `prepare_assembly` проверяет отдельные имена и prompt, но не дубли с host. `publish_profile` публикует replacement без общей проверки catalog.

В обычный валидный профиль добавляется `[commands.help]`. Тот же AppConfig при холодном launch возвращает `duplicate command: /help`. Hot watcher же публикует его успешно:

```
cold launch: Err(duplicate command: /help)
hot reload: epoch 0 -> 1; reload_error=None
unrelated /history: Err(duplicate command: /help)
```

Каждый `execute_command` начинает с общей `command_catalog()`, поэтому перестают работать даже `/history`, `/status`, `/mode`, не использующие конфликтующий prompt. Обычные agent turns здесь не проверялись и не объявляются сломанными. Возврат валидного файла является возможным обходом; этот recovery отдельно не прогонялся.

Источники:
- [Startup check](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server.rs#L598-L601)
- [Catalog conflicts and every command's dependency](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/commands.rs#L62-L87)
- [Partial config-only validation](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/commands.rs#L11-L20)
- [Publication path](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile.rs#L21-L68)
- [Documented last-good-assembly behavior](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/configuration.md#L1477-L1492)

Исправление: вынести shared merged-catalog validation и проверять **следующий** config + подготовленный tool registry до commit/publication. Ошибка должна сохранить прежний epoch и показать reload_error.

Артефакты: `reload-commands.log`, `reload-commands-repeat-{1,2,3}.log`, третий Rust repro в patch.

## 3. P2: поздний ответ на approval ломает корреляцию следующих запросов CLI

Настоящий interactive CLI запущен в отдельном PTY с официальным `process_commands.py`, approval timeout 200 ms. Пользователь вводит `/probe`, ждёт 800 ms, затем отвечает `n`. Tool **не выполняется** ни разу. Контрольный сценарий с немедленным `n` сохраняет рабочие следующие `/history`.

При позднем `n`:

```
/probe -> approval request timed out after 200ms
/history -> unknown approval id: <expired>
/history -> app-server returned unexpected response id: cli-command-4
```

В зависимости от порядка конкурентных response третий `/history` либо сразу получает чужой id, либо успевает показать `messages: 0`, после чего автоматический `config_summary` выбрасывает `unexpected response id` и REPL завершается. Оба варианта реально наблюдались. Это не повторное выполнение tool и не одобрение просроченного запроса: functional bug относится к сохранению работоспособности клиента после корректного серверного отказа.

Причина: `CliAppClient::request` распознаёт ответ из `pending_control_responses`, но `decode_response(...)?` завершает **текущий несвязанный request** при ошибке control reply. Его собственный ответ остаётся в stream и становится неизвестным id для следующего request. У prompt_approval синхронный stdin read; клиент не обработал истечение до отправки ответа.

Источники:
- [Control error propagates through current request](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/cli_app.rs#L163-L190)
- [Approval response sent after terminal input](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/cli_app.rs#L193-L217)
- [Server removes resolved/expired entry](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/approvals.rs#L108-L132)
- [REPL config refresh after successful display](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/main.rs#L558-L565)

Исправление: ancillary control replies должны разрешаться отдельно от ожидаемого target id. Сообщить о stale approval, но дочитать текущий response и сохранить синхронизацию. Не маскировать transport/protocol failures как успех. Более полный асинхронный reader сможет также закрывать устаревший terminal prompt при resolved event.

Артефакты: `cli_late_answer_probe.py`, `cli-late-answer.log`, `cli-late-repeat-{1,2,3}.log`, `cli-late-exit-variant.log`, `cli-immediate-answer.log`. После адаптации диагностического хелпера к двум реальным порядкам ответа три повтора проходят assertions. Первоначальный helper принимал только продолжающийся REPL; один сохранённый лог показывает, почему он был уточнён. Четвёртый Rust repro в patch изолирует transport correlation после уже завершившегося control request.

## Охват, проверки, ограничения

`coverage.tsv`: 28 файлов целиком, 5349 исходных строк; ещё 9 частичных диапазонов. Это фактическое чтение текущего прохода, включая повторное чтение частей предыдущего ACP-аудита, не утверждение о 5349 совершенно новых строках. Полным аудитом репозитория не является.

Штатные targeted tests: **15 passed, 0 failed** (ACP 5, profile watcher 3, slash integration 1, CLI 6). Все **четыре** новых regression ожидаемо падают с воспроизведёнными product-level симптомами: три lib и один bin test. `cli-tests.log`: 6 штатных passed и 1 новый ожидаемый failed; transport regression отдельно подтверждает, что оба валидных config requests получают ошибки чужих request IDs. Все regression проверены на указанном SHA. CLI binary собран из него без production patches (`build-cli.log`). `git diff --check` чистый.

Не запускались полный workspace gate, live provider/harness profiles, реальные IDE, Windows/macOS. Не заявлены находками: background-child approvals при полностью idle REPL (code-reading hypothesis, не воспроизведена); ACP fallback-output при нестандартном workflow (не было доказанного нарушающего producer). Предыдущие transient watcher recovery и worktree path findings не дублируются.

Воспроизведение Rust: применить `reproduction.patch`, задать официальную fixture в `PROTEUS_TEST_REFERENCE_MODULE`, затем:

```
cargo test --locked -p proteus-core --lib repro_chain_ -- --nocapture
cargo test --locked -p proteus-core --bin proteus repro_chain_ -- --nocapture
```

Python probes имеют в начале явные локальные пути к binary/fixture, которые следует заменить на свои после сборки.
