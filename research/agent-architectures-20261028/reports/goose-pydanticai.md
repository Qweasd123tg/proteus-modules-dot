# Goose и PydanticAI: ещё три полезных направления для Proteus

Срез: 28 октября 2026 года, около 22:26 UTC. Исследование исходников только чтением; реализации, сборки, тесты, вызовы моделей, CI и публикация не выполнялись.

## Что действительно добавляет этот проход

1. **`tool-schema-normalizer` — семантически ограниченное уменьшение отдельных JSON Schema**, а не повторный selector/byte budget. Источник — Goose. Разумное место в Proteus: opt-in helper внутри model adapter; существующий hook не вправе менять ToolSpec.
2. **`loop-observer` — ограниченный по памяти детектор повторяющихся действий и результатов**, переживающий сокращение истории внутри execution. Источник — PydanticAI. Начать с диагностического/мягкого режима hook/v6; легитимный polling и неизвестные исходы эффектов нельзя объявлять бесполезным циклом.
3. **`cache-health-audit` — объяснимая диагностика потери provider cache по уже записанным запросам/ответам**, а не прогрев cache и не ещё один token counter. Источник — PydanticAI. Первый вариант — read-only анализ разрешённого journal export, поскольку AfterModel в hook/v6 отсутствует.

Это предложения модулей/библиотек, **не готовые подключения и не измеренное ускорение**. Не повторяются уже описанные schema budget, skill snapshots, speculative compaction, resume manifest, multi-resource admission, mutation leases, capture-at-source и subagent handoff.

## Закреплённые источники и границы актуальности

| Проект | Проверенный HEAD main | Время commit UTC | Последний опубликованный release при чтении |
|---|---|---|---|
| Goose, официальный репозиторий теперь `aaif-goose/goose`; прежний API `block/goose` вернул redirect | [`775b3958c394ae2747cfb01791d3a45ac579139a`](https://github.com/aaif-goose/goose/commit/775b3958c394ae2747cfb01791d3a45ac579139a) | 28.10.2026 20:30:29 | [v1.57.0](https://github.com/aaif-goose/goose/releases/tag/v1.57.0), опубликован 28.10.2026 19:26:10 |
| PydanticAI, включая пакет harness в том же monorepo | [`3817d208c237c2327190b0bb46365eb1ec51672a`](https://github.com/pydantic/pydantic-ai/commit/3817d208c237c2327190b0bb46365eb1ec51672a) | 28.10.2026 21:42:15 | [v2.63.0](https://github.com/pydantic/pydantic-ai/releases/tag/v2.63.0), опубликован 28.10.2026 00:55:47 |

SHA получены через GitHub GET commits/main, затем файлы читались по этим SHA. Описанные механизмы относятся **к закреплённому main**, а не автоматически к названным releases. Goose — [Apache-2.0](https://github.com/aaif-goose/goose/blob/775b3958c394ae2747cfb01791d3a45ac579139a/LICENSE), PydanticAI — [MIT](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/LICENSE); перенос существенного исходного кода требует сохранения применимых notices, зависимости отдельно не разбирались.

База сопоставления: [Core `125a9eb4088991513e9f61d899469be2076e266c`](https://github.com/Proteus-harness/Proteus-core/commit/125a9eb4088991513e9f61d899469be2076e266c), [Modules `5fa8978684a37e8083c64f4d6cf0289e72450c6a`](https://github.com/Proteus-harness/Proteus-modules/commit/5fa8978684a37e8083c64f4d6cf0289e72450c6a). Ключевые утверждения о контрактах перепроверены GitHub GET по этим pins, не по старой локальной рабочей копии.

## 1. Goose: уменьшать представление схемы, не сокращая возможности tool

### Подтверждённый механизм

`normalize_input_schema` обходит позиции subschema и сворачивает `oneOf/anyOf` из простых строковых `const` в строковый `enum`. Описания вариантов переносятся в описание узла. Обход намеренно не редактирует instance data внутри `default/examples/const/enum`. Это не произвольное удаление длинных descriptions или ограничений. [Реализация, начало](https://github.com/aaif-goose/goose/blob/775b3958c394ae2747cfb01791d3a45ac579139a/crates/goose/src/agents/tool_schema_normalize.rs#L1-L199).

Сложные случаи явно ограничены:

- повтор одинакового const запрещает свёртку `oneOf`: там два совпадения означают отказ, в отличие от enum;
- старые объявленные dialects до поддержки const не преобразуются;
- конфликтующие sibling constraints не перезаписываются;
- inlining `$defs` учитывает отличие `$ref` siblings в draft-06/07, nested `$id/$schema`, identity keywords и сложные JSON Pointer forms;
- после inlining собираются живые ссылки, включая транзитивные, прежде чем удалять определения.

Это существенно надёжнее регулярного выражения над JSON, но не заменяет проверку переносимого subset. [Refs и dialects](https://github.com/aaif-goose/goose/blob/775b3958c394ae2747cfb01791d3a45ac579139a/crates/goose/src/agents/tool_schema_normalize.rs#L201-L450).

Нормализация встроена в `Extension::fetch_public_tools`, после проверки available-tools и формирования имени. Полученный каталог кешируется по scope и версии tool list; изменение версии во время fetch не позволяет сохранить результат как актуальный cache entry. [Место вызова](https://github.com/aaif-goose/goose/blob/775b3958c394ae2747cfb01791d3a45ac579139a/crates/goose/src/agents/extension_manager/mod.rs#L310-L385).

### Уже есть в Proteus; чего не хватает

Имеющийся `tool-schema-budget` выбирает целые, неизменённые ToolSpec. Новый helper уменьшал бы **внутреннее представление оставшейся схемы**, не выбирая другой инструмент и не меняя его authority.

Но `ToolSelectionOutput::validate_against` прямо разрешает лишь переупорядочить/убрать зарегистрированные tools и требует полного равенства ToolSpec. `BeforeModel -> ModelContext` меняет messages/instructions, а не tools. Поэтому обещать реализацию этого преобразования обычным hook/v6 было бы нарушением действующего контракта. [Selection](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/tool_selection.rs#L93-L109), [hook responses](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/hook.rs#L166-L225).

В проверенном OpenAI encoder `parameters` берутся из `tool.input_schema`. Это конкретный узкий seam для opt-in преобразования **provider payload**, сохраняя канонический registered ToolSpec и host-side validation исходной схемой. [Encoder](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/model/model-pack/src/adapters/openai/request.rs#L200-L230).

### Предложение для Proteus

Чистая Rust-библиотека внутри существующего model module:

```text
normalize(schema, declared_dialect, provider_profile, limits)
  -> Unchanged(reason)
   | Candidate { encoded_schema, source_digest, transform_version,
                 before_bytes, after_bytes, applied_rules }
```

Первый subset — только inline string-const union, без `$ref` inlining. Разрешённые dialects перечислены явно; неизвестный/custom dialect — unchanged. Включение по конфигурации, без смены defaults. Более сложный `$defs` проход стоит добавлять только при подтверждённой потребности.

Обязательные свойства:

- исходная схема остаётся authoritative для проверки аргументов и audit;
- unknown keywords/annotations не удаляются «ради компактности»;
- сохранились имя, surface, constraints, ordering enum и текст существенных пояснений;
- после подсчёта provider JSON применяется только кандидат с реальной экономией bytes; inlining многократно используемого enum способен **увеличить** payload;
- bounded cache по schema digest + dialect + provider profile + transform version; никакого cache ключа только по имени tool;
- глубина/число узлов/bytes ограничены; oversized или неподдерживаемый вход возвращает unchanged, не отключает tool;
- преобразование не чинит аргументы, не исполняет tool и не выдаёт permission.

### Как проверять, когда будет разрешён следующий этап

Нужны эквивалентность принятия/отклонения JSON instances на поддерживаемом dialect, повторная нормализация без изменений, стабильный provider payload и отрицательные cases: дубликаты oneOf, mixed types, nested resources, schema-looking defaults, конфликтующие siblings, неизвестный dialect. Для provider compatibility — отдельный explicit opt-in прогон, не догадка по размеру JSON. У Goose такие edge cases представлены в исходных tests, но здесь они **не запускались**. [Существующие cases](https://github.com/aaif-goose/goose/blob/775b3958c394ae2747cfb01791d3a45ac579139a/crates/goose/src/agents/tool_schema_normalize.rs#L458-L1075).

**Чего пока нельзя утверждать:** меньшие JSON bytes не доказывают меньше provider tokens, лучшую точность выбора tool или меньшую задержку модели. Число из upstream-комментария о сокращении одной формы схемы не переносится на каталог Proteus.

## 2. PydanticAI: наблюдать реальные повторения, не только считать rounds

### Подтверждённый механизм

`DetectLoops` из harness фиксирует tool calls после model response; перед следующим request сопоставляет результаты и проверяет четыре паттерна: повтор одинакового вызова, одинаковый результат того же вызова, чередование A–B и одинаковый текст без tools. Fingerprint вызова включает имя и canonical JSON args; результат — outcome, структурированный response и идентификаторы файлов. [Patterns/state](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/src/pydantic_ai_harness/pydantic_ai_harness/detect_loops/_capability.py#L25-L250), [сопоставление и fingerprints](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/src/pydantic_ai_harness/pydantic_ai_harness/detect_loops/_capability.py#L372-L434).

Capability запрашивает outermost ordering, чтобы прочитать результаты до history rewriting; `for_run` создаёт свежий экземпляр. После срабатывания использованные steps не учитываются повторно. Действие — nudge, ошибка либо callback. Сокращение истории не очищает уже записанные признаки текущего run. Это полезнее пересчёта повторов по последнему summary. [Lifecycle и detection](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/src/pydantic_ai_harness/pydantic_ai_harness/detect_loops/_capability.py#L174-L250), [actions](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/src/pydantic_ai_harness/pydantic_ai_harness/detect_loops/_capability.py#L340-L370).

**Важная деталь:** window ограничивает рассматриваемые calls, но `_steps` в прочитанной реализации — растущий список всех steps текущего run; `_detect` строит recent slice из него. Поэтому переносить название «window» как доказательство bounded-memory реализации нельзя. Для Proteus разумнее собственный bounded ring.

### Уже есть в Proteus

`single_loop` ограничивает число rounds, но это не отличает полезную длинную работу от повторения одного неудачного read. В прочитанном `codex_loop` продолжение определяется tool calls и `end_turn=false`; специализированного анализа repeated call/result в этом участке не обнаружено. Это ограниченное наблюдение конкретных workflow-файлов, не доказательство отсутствия любых лимитов во всём Core. [single_loop](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/workflow/coding-workflow/src/single_loop.rs#L39-L55), [codex_loop](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/workflow/coding-workflow/src/codex_loop.rs#L105-L168).

Есть `BeforeTool`, `AfterTool`, `BeforeModel`, `TurnSettled` и attribution. Но `AfterTool` уже получает результат **после host truncation**, а не полные исходные bytes. Поэтому одинаковые видимые результаты не доказывают идентичности полных файлов/вывода. Ошибка output hook не отменяет уже случившийся эффект. [Tool hook boundary](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/bound_tools/hooks.rs#L93-L131).

### Предложение для Proteus

`loop-observer` — независимая policy-библиотека с возможным hook/v6 adapter:

- bounded ring последних calls, bounded pending map и счётчик text streak, без хранения полной истории;
- ключ состояния: execution + при наличии session/thread/turn; не только имя tool и не только один ExecutionId для всех дочерних agent bindings; detached execution не придумывает conversation IDs. [Attribution](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/execution_attribution.rs);
- dedupe по host call identity; canonical args для семантической сигнатуры, но не для выдачи повторного grant;
- отдельно учитывать `requested`, `blocked`, `returned` и unknown outcome; signal о повторной попытке не равен доказательству повторного effect;
- `AfterTool` capture перед следующей compaction; для полного raw-result сравнения потребуется ранее предложенный trusted capture digest, его нельзя выдумывать из truncated output;
- на `BeforeModel` — один краткий diagnostic/nudge с evidence call IDs, без изменения tool names/permissions; `BeforeTool` block только в явно включённом режиме;
- после `TurnSettled` cleanup; bounded TTL/cap на потерянные lifecycle events; restart обнуляет наблюдения явно, а не изображает durable state;
- никакого фонового host callback после завершённого hook invocation.

Первая версия должна ограничиться tool patterns. `AfterModel` отсутствует: поиск repeated text по request messages требует dedupe неизменяемых message/part IDs и пропускает часть ответов, удалённых раньше. Полная эквивалентность PydanticAI через один существующий hook не обещается.

### Где нельзя автоматически прекращать

Повтор status/read может быть **правильным** ожиданием CI, очереди, внешнего ответа или изменения файла. Одинаковый результат сейчас не доказывает, что следующий не изменится. Внешние side effects с unknown settlement требуют reconciliation, а не автоматического retry или вывода «уже выполнено».

Поэтому default — observation; polling-tools/явное пользовательское ожидание имеют отдельную политику с interval/deadline/progress state. Детектор не заменяет stopping condition пользователя и не может сам завершить порученное наблюдение только из-за одинаковых ответов. Для active blocking нужен перечень запрещённых паттернов и раздельные основания: validation failure, неизменный read, запрет permissions, неизвестный исход.

Другие пределы: canonicalization не делает разные JSON values равными; volatile timestamps могут скрывать петлю; короткие fingerprints допускают коллизии и не являются idempotency keys. Hash маленького домена аргументов не обеспечивает секретность — upstream отдельно предупреждает об этом. Экспортировать лучше call IDs и счётчики, не arguments/result fingerprints. [Предупреждение и политика trace](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/src/pydantic_ai_harness/pydantic_ai_harness/detect_loops/_capability.py#L62-L72).

Проверка будущего варианта: legitimate polling, repeated malformed calls, A–B, параллельные ответы в другом порядке, разные scopes, повтор delivery одного event, compaction, cancellation, truncated-equal/full-different results, cleanup и replay. Это перечень необходимых проверок, не заявление об их прохождении.

## 3. PydanticAI: диагностировать cache collapse с причиной и неопределённостью

### Подтверждённый механизм

`CacheHealthDetector` поддерживает marks конкретной conversation, разделённые по фактическим provider name/URL/model из ответа. Сравнивает cache read с ранее установленным prefix; классифицирует collapse как unexpected, ttl_expired, compacted, unknown или unreported. Учитывает смену compaction по count и digest последней compaction, чтобы замена summary не терялась при прежнем количестве элементов. [Основные types/store](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/pydantic_ai_slim/pydantic_ai/_cache_health.py#L1-L155), [классификация](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/pydantic_ai_slim/pydantic_ai/_cache_health.py#L277-L426).

Marks переживают несколько runs одной conversation. Store имеет cap conversations и idle horizon; warning adapter использует отдельное run-state, не общий mutable step counter. Sustained collapse не предупреждается на каждом request. Это схема наблюдения, не отправка дополнительных запросов ради cache warming. [Warning lifecycle](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/src/pydantic_ai_harness/pydantic_ai_harness/warn_on_cache_busts/_capability.py#L134-L192).

Особенно полезная защита: usage от provider-native tools/continuation chain может суммировать несколько внутренних model passes. Такое высокое число cache reads нельзя принять за длину единого prefix. Детектор распознаёт этот случай и не поднимает по нему baseline; для объединённой chain предусмотрен final_segment. [Summed usage](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/pydantic_ai_slim/pydantic_ai/_cache_health.py#L208-L224), [update logic](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/pydantic_ai_slim/pydantic_ai/_cache_health.py#L287-L377).

### Уже есть в Proteus

`TokenUsage` содержит optional cached input/cache creation, workflow accounting уже выдаёт provider cache categories. Нельзя предлагать ещё раз «добавить учёт cache tokens». Важно, что список categories опускает нулевые значения; для диагностического различия «0» и «не сообщено» надо брать исходные optional usage поля. [Canonical usage](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/model_standard/canonical_response.rs#L201-L251), [accounting](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/workflow/coding-workflow/src/token_accounting.rs#L136-L155).

Journal schema 21 уже различает request/response по exchange_id, compaction в HistoryMutated, timestamp и session/execution/thread/turn attribution. Это достаточно хорошая основа для read-only доказательной диагностики. Но обязательного типизированного factual provider endpoint/cache partition в CanonicalModelResponse нет: есть provider_metadata. Нельзя молча считать request alias фактическим backend после fallback. [Journal](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/session_journal/types.rs), [Response](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/model_standard/canonical_response.rs#L1-L64).

### Предложение для Proteus

Первая версия — pure analyzer `cache-health-audit`, читающий только явно предоставленный export journal; затем при необходимости tool/v6 wrapper с обычными read grants. Не дать модулю скрытый неограниченный доступ к session storage.

Вход: versioned request/response records, timestamps, resolved backend identity при наличии, provider-reported usage, compaction evidence, профиль документированных cache settings. Выход:

```text
exchange_id, previous_exchange_id, observed_cache_read,
previous_baseline, classification, evidence_quality,
changed_sections?, missing_evidence[]
```

- Сопоставление строго по exchange_id, отдельно workflow/model-helper origins.
- Unknown backend identity, TTL или aggregate usage -> ограниченная диагностика, не выдуманная точность.
- Compaction, model switch, настройка caching и intentional cache-key changes выводятся отдельно.
- Ограничены conversations, backend keys внутри conversation, pending exchanges и размер evidence; одних LRU conversations недостаточно.
- Сравнение canonical section digests может показать изменение instructions/tools/history, но не доказывает одинаковый provider wire prefix после adapter transforms.
- Ни warmup, ни reorder prompt, ни смена model/cache config автоматически не выполняются.
- Состояние можно воспроизводимо получить из уже записанных событий; live callback/новый AfterModel contract для первого варианта не нужен.

**Поправка к формулировкам донора:** cache miss внутри ожидаемого retention window не доказывает, что виноват локальный prompt. Provider routing, eviction и неполная telemetry также возможны. Для Proteus лучше имя `unexplained_collapse` с evidence, а не категорическое «prefix изменён». Это наше консервативное проектное решение, не установленный дефект PydanticAI.

Проверять в будущем: known zero/absent usage, compaction с тем же числом summaries, fallback и возврат к старому backend, TTL boundary, out-of-order responses, native-tool summed reads, cold restart, повтор events, bounded cardinality. Эффект измеряется снижением ложных предупреждений и обнаружением конкретного источника payload churn; само наличие observer не ускоряет запросы.

## 4. Что ещё проверено, но не стоит выдавать за новый модуль

### Goose extension leases — полезное подтверждение, не ещё один cache-проект

`ExtensionLease` держит выбранные slots и лениво построенный ToolCatalog через Arc/OnceCell; удерживаемый lease не меняется от последующих selection/tool-list updates. Dispatch разрешает alias через тот же каталог. Это хороший пример связывания объявленного инструмента с выбранным endpoint snapshot. Но immutable catalogs/process generations уже покрыты прежним исследованием Proteus; новый «extension framework» отсюда не нужен. Snapshot неизменности также не разрешает игнорировать последующее host authority revocation. [Lease](https://github.com/aaif-goose/goose/blob/775b3958c394ae2747cfb01791d3a45ac579139a/crates/goose/src/agents/extension_manager/lease.rs#L1-L270).

### Goose inspectors — не переносить ошибку проверки как разрешение

Inspector manager запускает проверки по порядку; ошибка отдельной проверки логируется, затем обработка продолжается. При сведении результатов Allow не отменяет Deny/RequireApproval. Это две разные гарантии: монотонность найденных запретов **не означает fail-closed при недоступной проверке**. Для advisory analysis продолжение может быть осознанной политикой; для обязательного policy gate — нельзя переносить её без отдельного error contract. Proteus уже имеет ordered typed hooks и host-owned authority; ещё одна разрешающая цепочка из этого кода не требуется. [Inspection manager и reduction](https://github.com/aaif-goose/goose/blob/775b3958c394ae2747cfb01791d3a45ac579139a/crates/goose/src/tool_inspection.rs#L67-L127), [решения](https://github.com/aaif-goose/goose/blob/775b3958c394ae2747cfb01791d3a45ac579139a/crates/goose/src/tool_inspection.rs#L188-L290).

### PydanticAI concurrency — важный negative case, не замена scheduler

Current `ConcurrencyLimitedModel` отвергает повторное использование того же limiter во вложенных wrappers и на agent/model уровнях, поскольку это способно вызвать self-deadlock. Streaming wrapper удерживает concurrency context на lifecycle stream и явно учитывает teardown на другой task. [Проверка повторного limiter](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/pydantic_ai_slim/pydantic_ai/models/concurrency.py#L95-L165).

Полезно перенести этот **инвариант при будущем multi-resource admission adapter**, а не ещё один semaphore: один и тот же permit не должен незаметно приобретаться повторно по reentrant route. Числовой простой limit у донора допускает unlimited queue по умолчанию; это не улучшение уже bounded Proteus process lanes. Ни full deadlock freedom, ни settlement внешних side effects этот limiter не доказывает. [Limiter contract](https://github.com/pydantic/pydantic-ai/blob/3817d208c237c2327190b0bb46365eb1ec51672a/pydantic_ai_slim/pydantic_ai/concurrency.py#L81-L140).

## Приоритет и безопасный следующий шаг

| Направление | Первый самостоятельный результат | Что блокирует production-подключение |
|---|---|---|
| Schema normalizer | Pure helper, минимальный inline subset и rule report | Эквивалентность схем; provider encoder integration, opt-in config |
| Loop observer | Bounded policy state machine; диагностический hook adapter для tool patterns | False positives polling; lifecycle/replay; truncated vs raw results |
| Cache health audit | Read-only analyzer разрешённого journal export | Достоверная backend identity/retention/multipass metadata; не новый token counter |

Самый узкий следующий эксперимент — **schema normalizer без refs**; наиболее безопасный диагностический — **cache-health-audit без runtime mutations**. Loop blocking не следует включать default до проверки легитимного ожидания внешних процессов.

## Проверка и ограничения этого отчёта

- Прочитаны текущие pinned source files и официальные releases; архитектурные предложения отделены от реализации доноров.
- Ключевые contracts Proteus fetched по точному Core pin; для сравнения workflow/encoder — точный Modules pin.
- Не запускался никакой исходный код доноров или Proteus; нет результатов tests/builds/evals и нет performance measurements.
- Repositories, main, PR, CI и настройки runtime не изменялись.
- Snapshot исходников и blob identities: [source-manifest.json](../research-sources/goose-pydanticai/source-manifest.json). В репозиторий включён реестр ссылок и blob identities; копии чужих исходников сюда не добавлены.

