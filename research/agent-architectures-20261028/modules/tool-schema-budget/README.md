# Бюджет схем tools — opt-in Rust hook

`tool_selection.schema_budget` — самостоятельный процесс **hook/v6, wire v3**.
Он дополняет существующий селектор: оставляет инструменты в прежнем порядке,
но не тратит весь прямой tool-контекст на несколько очень больших схем.
Ни Core, ни reference-модули, ни права инструментов не меняются.

**Статус:** исходники написаны и сверены с закреплёнными контрактами чтением.
Сборка, исполнение, тесты и измерение ускорения не выполнялись; проверку делает
пользователь. Это не готовая подтверждённая поставка. `Cargo.lock` не создавался.

## Что именно добавлено

В [существующем dynamic selector](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/tool-selection-hook/src/lib.rs#L82-L152)
ограничивается число tools. Размер схем только оценивается как `bytes / 4`
для metadata, а [config](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/tool-selection-hook/src/config.rs)
содержит `max_hot_tools` и `always_include`, без суммарного byte budget.
Этот пример добавляет именно суммарный бюджет, а не ещё один поиск tools.

Идея экономить контекст размером каталога, а не одним числом инструментов,
согласуется с [Claude SDK tool search](https://code.claude.com/docs/en/agent-sdk/tool-search):
режим `auto:N` включает отложенную загрузку по доле окна контекста. Здесь нет
заявления о совместимости с Claude, копирования его алгоритма или равенстве
байтов токенам. Поиск уже есть в Proteus; дополнительный model round-trip сам
hook не делает.

## Контракт и алгоритм

1. Только `BeforeToolSelection` и явно указанные `enabled_phases`; остальные
   события, отсутствующая либо другая фаза получают `Continue`.
2. Вход — **output предыдущего hook**, не первоначальный список candidates.
   Удалённый ранее инструмент не восстанавливается.
3. Считается точный размер компактного JSON-массива `Vec<ToolSpec>`:
   все поля canonical spec, скобки и запятые. Counting writer не создаёт вторую
   строку со всеми сериализованными схемами.
4. Сначала резервируется вся обязательная группа. Затем optional tools
   допускаются в прежнем порядке, если помещаются. Слишком большой optional
   tool не мешает следующему меньшему. Схемы не обрезаются и не переписываются.
5. Если всё помещается, ответ `Continue` не переписывает tools и metadata.
   При сокращении metadata содержит `upstream` с исходным значением и
   `schema_budget` с точными размерами, количеством и признаком overflow.

Всегда сохраняются **в пределах предыдущего selection**:

- все имена из `always_include`, если они там присутствуют;
- вся группа с `metadata.category = "proteus_agent_control"`;
- **все non-Function surfaces**: provider-hosted, freeform, workflow-owned и
  неизвестный будущий вариант;
- Function tools без явного корневого `input_schema.type = "object"`, а также
  с корневыми `$ref`, `$dynamicRef` или `$recursiveRef`: scalar/array, union,
  ссылочная и неизвестная форма остаются прямыми. В [JSON Schema drafts 4–7](https://json-schema.org/understanding-json-schema/structuring)
  `$ref` заставляет validator игнорировать соседнее `type = "object"`.
  Deferred `proteus_tool_call.args` допускает только object, тогда как
  [Core не ограничивает корень schema объектом](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/domain/tool_validation.rs#L7-L43).

Таким образом, сокращаются только обычные object-argument Function tools без
корневой ссылки, для которых существующий deferred bridge передаёт аргументы.

Отсутствующее обязательное имя не создаёт новый tool. Metadata не даёт прав;
`ToolSafety`, schema, timeout, parallel flag и остальные поля spec остаются
неизменными. Сохраняются canonical значения и их сериализация, а не исходные
пробелы/форматирование входного JSON на проводе.

## Бюджет не равен лимиту всего запроса

По умолчанию `on_mandatory_overflow = "preserve"`: это **best-effort target**.
Если обязательная группа больше бюджета, она целиком сохраняется;
`mandatory_overflow=true` явно показывает превышение. Нельзя одновременно
гарантировать её сохранность и жёсткий лимит меньшего размера.

Только явное `on_mandatory_overflow = "error"` включает отказ hook при таком
превышении. Core прервёт текущую операцию выбора/ход до принятия selection;
это не решение policy `deny`, не остановка уже исполненного tool и не retry.

При обычном успешном сокращении `selected_bytes <= max_schema_bytes`.
Это граница **только выбранного canonical JSON-массива**, не токены модели,
не provider-specific serialization и не полный model request. Reference
workflow добавляет discovery meta-tools **после** selection; они и инструкции
в этот бюджет не входят.

## Подключение без потери существующих hooks

`profile.fragment.toml` — шаблон, **не самостоятельный профиль**. Подставьте
пути к executable и вручную добавьте component/config tables в выбранный профиль.
Если dynamic selector уже подключён, не создавайте второй export с тем же id.

Массив `modules.hooks` не является операцией append. **Не импортируйте пример
вслепую поверх рабочего массива**: сохраните все его элементы и вставьте
`"tool_selection.schema_budget"` непосредственно после
`"tool_selection.dynamic"`. Например:

```toml
# Было:
# hooks = ["codex_compact", "tool_selection.dynamic", "your_other_hook"]
# Стало:
hooks = ["codex_compact", "tool_selection.dynamic", "tool_selection.schema_budget", "your_other_hook"]
```

Если dynamic selector раньше не использовался, сначала осознанно выберите его
и его count-budget либо размещение этого hook после другого селектора.
Пример не меняет workflow и не добавляет новые policy grants.

Подтверждённая чтением цепочка:

- [Core исполняет handlers последовательно](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/execution_hooks.rs#L79-L143),
  передавая следующему принятый event;
- [hook/v6 проверяет selection против исходного и предыдущего списков](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/hook.rs#L157-L170):
  можно только убрать/переставить неизменённые specs; этот модуль не переставляет;
- [reference workflow](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/workflow/coding-workflow/src/host.rs#L172-L216)
  сравнивает selection с policy-visible каталогом и затем добавляет
  `proteus_tool_search`, `proteus_tool_describe`, `proteus_tool_call`;
- [deferred invocation](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/workflow/coding-workflow/src/dynamic_tools.rs#L316-L398)
  заново получает policy-visible tools и идёт через обычное host execution.
  Provider-hosted нельзя вызвать этим путём; в plan разрешены только read-only.

Шаблон включает только `codex_loop`, `single_loop`, `execute`. **Plan и review
не сокращаются**: в review reference workflow отключает discovery, а в plan
даёт только поиск/описание без `proteus_tool_call`. Это не полноценный путь
вызова скрытого read-only tool. Не добавляйте другие фазы без проверки их
workflow и доступности нужных действий.

## Стоимость и ограничения

- Сканирование линейно по сериализованным байтам, проверка дубликатов имён —
  `O(n log n)`. Нет LLM, сети, файлового I/O, новых потоков или кэша.
- По умолчанию до 1024 входных tools и 8 MiB сканирования. Их превышение,
  malformed config и cancellation всегда дают ошибку; это отдельные resource
  limits, не режим mandatory overflow. Результат не возвращается частично.
- Проверка отмены идёт между tools и во время записи в counting sink.
  Уже принятый/декодированный SDK JSON этим лимитом не ограничивается;
  абсолютный RSS bound не заявляется.
- Для маленького каталога отдельный hook-процесс и сериализация могут быть
  дороже выгоды. Снижение токенов/задержки не измерялось. Omitted tools остаются
  доступны только если конкретный workflow действительно реализует discovery.
- SDK закреплён на Core `125a9eb4`; canonical типы импортируются через SDK.
  Прямые crates.io версии взяты из Cargo.lock того же Core. Полный dependency
  lock и фактическая совместимость ещё не проверены.

Immutable skill snapshots/search и speculative compaction остаются отдельными
архитектурными кандидатами. Этот небольшой hook их не реализует и не заменяет.
