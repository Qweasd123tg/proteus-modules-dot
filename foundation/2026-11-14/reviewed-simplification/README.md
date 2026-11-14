# Проверенные локальные рефакторы: config validation и model history

Два независимых текстовых патча для **разных upstream-репозиториев**, подготовленные 14 ноября 2026. Публикация здесь передаёт исходники и инструкции: **патчи не применены к upstream, не установлены в runtime и не являются новой готовой сборкой Proteus**.

## Состав и базы

| Патч | Репозиторий и точная база | Проверенный локальный результат |
|---|---|---|
| [core-config-validation.patch](core-config-validation.patch) | [Proteus-core](https://github.com/Proteus-harness/Proteus-core), `89997df995df7c39b713e16aba216ecb19c8f497` | `5768c47f949a306e69a5796162bfbe9947c3b20e` + test-only `902bf64464e651ff117b3fa79c78170120a72c30` |
| [modules-history-compaction.patch](modules-history-compaction.patch) | [Proteus-modules](https://github.com/Proteus-harness/Proteus-modules), `3270dc0f894eaf4d0360306052b806099b8f5351` | `e56c1cad10d18d4e037968bf7ccef611a05cd605` + `43a23e666a69488fefaecab3c80272ebaf8d903b` |

Локальные SHA служат идентичностью проверенной работы, а не ссылками на опубликованные upstream commits. Modules сохраняет свой штатный contracts pin `b5fac84245b075896c24763b3aebac79b4375c2e`; обновлять его ради этого патча не требуется. В combined Modules patch включены **обе** правки: один перенос normalizer без исправления compactor использовать не следует.

В поставке нет raw logs, приватных конфигураций, бинарников или архивов. Исходные файлы и фрагменты остаются под лицензиями upstream; [Core MIT](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/LICENSE), [Modules MIT](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/LICENSE).

## Что меняется

### Core: одна семантическая проверка профиля

`AppConfig::validate_semantics()` объединяет правила provider, `module_config` slots, hooks и prompt commands. Loader и итоговый Save вызывают общий pass; watcher использует loader. Раздельные неполные проверки Builder удалены. Исходная форма instructions, разрешение файлов, TOML-представимость, runtime assembly и защитные перечитывания watcher остаются отдельными обязанностями.

Закрыт подтверждённый сценарий: Save принимал неизвестный slot, но последующие cold load/watch отвергали сохранённый профиль. Теперь отказ происходит до записи, изменения runtime epoch и history. Пустые профили, отсутствие provider и absolute/relative file-backed instructions сохраняют прежнюю семантику.

### Modules: общий request-only recovery и корректная compaction

Normalizer незакрытых tool calls перенесён из Codex-specific recovery в общий history helper. Его используют `single_loop`, `plan_execute_review` и `codex_loop`; особый порядок Codex interruption marker сохранён. Synthetic `aborted` закрывает вызов **только в model request**, не становится фактом durable history и не запускает инструмент повторно.

Codex compactor оставляет tool-пары во входе суммаризатора, но не переносит request-scoped ToolCall/ToolResult как независимый context в replacement, где исходные calls уже удалены. Обычный Request context и `turn_aborted` сохраняются; ниже порога compaction история не меняется.

## Проверки и их границы

- **Core: 48 уникальных scoped tests passed**: config 23, Builder 18, watcher 3, HTTP-router 4. Новая регрессия на исходной базе падала на ошибочно успешном Save; после исправления проходит. Проверены TOML/JSON/directory, первый Save отсутствующего файла, пустые профили, неизменность disk/live/epoch/history после отказа, следующий корректный Save и watcher recovery. Статическое независимое review не нашло блокеров.
- **Modules: 121 scoped tests passed**: workflow 98 + compactor 23. Независимое review повторило эти тесты и отдельное compactor-воспроизведение. Первоначальные workflow-регрессии показали RED 3 failed / 3 passed на старом коде.
- **Modules process RED/GREEN**: настоящий Core, workflow/hook процессы, canonical replacement/ACK, native Anthropic adapter и локальный scripted HTTP endpoint. С compactor: 6 сценариев, 30 turns, 98 requests; без compactor: 6 сценариев, 30 turns, 51 request. Проверены cancel/control трёх workflows, warm follow-ups и cold resume. Старый compactor оставлял orphan result на первом warm resume после отмены; исправленный не оставляет missing/orphan outputs, не повторяет tool execution и не пишет synthetic results в durable history.
- Форматирование, diff checks и применение к чистым базам проверены. Release ZIP Modules собраны и их executable bytes сверены, но здесь ZIP не публикуются.

**Не заявляется полный gate:** Core использовал scoped Cargo и ранее подготовленный reference fixture без пересборки, не полный `scripts/test.py`; не проверены module_swap/doctor/portable, GPUI и сетевой HTTP socket (HTTP tests используют in-process router). Modules process gates использовали debug binaries и localhost fixture, не release runtime, внешний LLM или GUI. Полный workspace не прогонялся. Это результаты локальной проверки, не CI этого delivery PR.

Не исправлены external-edit→Save race, автоматическое восстановление уже испорченного профиля, произвольный сторонний faulty compactor и недоказанные late-ACK сценарии. Измерений latency/RSS/throughput нет.

## Выигрыш без завышения

Production diff двух патчей: **+85/−77 строк, net +8**. Это не сокращение сотен строк и не доказанное ускорение. Добавлены 583 строки тестов и 6 строк документации, всего 11 новых тестов. Выигрыш: общие правила имеют одно место реализации, а три конкретные несогласованности Save/Load и cancel/resume/compaction устранены без новых зависимостей, DTO или настроек.

## Как применить

Не применять эти патчи к `proteus-modules-dot`. Используйте отдельные чистые рабочие копии соответствующих upstream на указанных базах. Сохраните свою работу; при другой базе сначала проверьте, не перенесены ли изменения, и повторите тесты. Не применяйте силой при конфликте.

В каталоге этой поставки проверьте `sha256sum -c SHA256SUMS`. Затем задайте `PATCH_DIR` абсолютным путём к этому каталогу и перейдите в **нужный upstream checkout**.

Для Core:

```bash
test "$(git rev-parse HEAD)" = 89997df995df7c39b713e16aba216ecb19c8f497
git status --short  # рабочая копия должна быть чистой
git switch -c review/shared-config-validation
git apply --check "$PATCH_DIR/core-config-validation.patch"
git apply "$PATCH_DIR/core-config-validation.patch"
git diff --check
```

Для Modules:

```bash
test "$(git rev-parse HEAD)" = 3270dc0f894eaf4d0360306052b806099b8f5351
git status --short  # рабочая копия должна быть чистой
git switch -c review/shared-history-compaction
git apply --check "$PATCH_DIR/modules-history-compaction.patch"
git apply "$PATCH_DIR/modules-history-compaction.patch"
git diff --check
python3 scripts/test.py -p coding-workflow -p codex-context-preparation --offline
```

Core scoped команды после подготовки штатных fixtures и dependencies:

```bash
cargo test --offline --locked -p proteus-core --lib core::config:: -- --nocapture
cargo test --offline --locked -p proteus-core --lib app_server::config_builder:: -- --nocapture
cargo test --offline --locked -p proteus-core --lib app_server::profile_watch:: -- --nocapture
cargo test --offline --locked -p proteus-core --lib app_server::http::tests::config:: -- --nocapture
```

В новой среде offline может не хватить dependencies/fixture. Следуйте build/test инструкциям upstream; не считайте отсутствие подготовки падением патча и не выдавайте scoped targets за полный gate. После локальных проверок нужны обычное review и необходимые CI исходного репозитория. Публикация здесь их не заменяет.
