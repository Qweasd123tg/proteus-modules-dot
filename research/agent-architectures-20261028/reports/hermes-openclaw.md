# Механизмы Hermes Agent и OpenClaw для развития Proteus

Дата исследования: 28 октября 2026 года. Срез upstream зафиксирован около 16:20 UTC.

## Вывод

Наиболее полезные заимствования для Proteus — ограниченный по объёму каталог инструментов, неизменяемые снимки skills с ленивым поиском и отдельные механизмы восстановления. Переносить целиком runtime другого агента не требуется: Proteus уже имеет процессные границы, ограниченный multiplexed broker, поколения запросов, cancellation и lazy restart.

Первый небольшой Rust-модуль можно реализовать через `hook/v6 / BeforeToolSelection`: он ограничивает суммарный размер выбранных `ToolSpec`, не меняя их содержание. Следующий самостоятельный результат — развитие имеющегося эксперимента `portable-skill-catalog`, а не второй importer. Ограничение частоты рестартов и доверенный учёт побочных эффектов относятся к владельцу исполнения в Core; обычный hook не может достоверно обеспечить эти свойства.

Ниже **наблюдение** означает чтение закреплённого исходного кода или явно указанной документации. **Предложение** означает проект для Proteus, ещё не реализованный и не измеренный в рамках этого исследования. Сборки, выполнение агентов, обращения к моделям и CI не запускались; численных обещаний ускорения нет.

## Закреплённые версии и происхождение

| Проект | Исследованный commit main | Последний опубликованный release при проверке | Корневая лицензия |
|---|---|---|---|
| NousResearch/hermes-agent | `820967473d4d5b6777d3a9419def4be422711d16`, 28.10.2026 15:56:59 UTC | `v0.22.5`, commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e`, опубликован 23.10.2026 | MIT, Copyright 2025 Nous Research |
| openclaw/openclaw | `c3aa6e15e093c6dc8ab55533a936e4cbe995942e`, 28.10.2026 16:18:00 UTC | `v2026.10.8`, commit `dc2523e5a5c7a309517fd7fa834add938231d526`, опубликован 27.10.2026 | MIT |

Официальные идентичности подтверждены через [документацию Hermes](https://hermes-agent.nousresearch.com/docs), [репозиторий Hermes](https://github.com/NousResearch/hermes-agent), [документацию OpenClaw](https://docs.openclaw.ai/tools/skills) и [репозиторий OpenClaw](https://github.com/openclaw/openclaw). Текущий SHA получен отдельным GitHub GET для ветки, а release — отдельным GET release/tag; закэшированные страницы истории commits не использованы как доказательство текущего HEAD.

Источники releases: [Hermes v0.22.5](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.5), [OpenClaw v2026.10.8](https://github.com/openclaw/openclaw/releases/tag/v2026.10.8). Тексты лицензий: [Hermes LICENSE](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/LICENSE), [OpenClaw LICENSE](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/LICENSE). При переносе существенных частей кода необходимо сохранить применимые notices; лицензии сторонних зависимостей здесь отдельно не исследованы.

База совместимости Proteus: [Core `125a9eb4088991513e9f61d899469be2076e266c`](https://github.com/Proteus-harness/Proteus-core/commit/125a9eb4088991513e9f61d899469be2076e266c) и [Modules `5fa8978684a37e8083c64f4d6cf0289e72450c6a`](https://github.com/Proteus-harness/Proteus-modules/commit/5fa8978684a37e8083c64f4d6cf0289e72450c6a), с разделением backend implementations на 18 независимых выбираемых конфигурацией процессов. Исследованные механизмы upstream относятся к закреплённым commits main, а не автоматически ко всем указанным стабильным releases.

## Неизменяемый каталог skills и ограниченный поиск

### Наблюдение в OpenClaw

Каталог обновляет один discovery worker. Он разделяет между потребителями неизменяемые факты о прочитанных skills, но не их eligibility, selection или полномочия чтения. Старый снимок может оставаться у выполняющегося запроса, пока новый результат готовится отдельно. В `refresh.ts` заданы 30-минутный safety rescan, максимум 128 источников и ограничение retained catalog до 4096 записей. События файловой системы объединяются с задержкой 50 мс. Один pending scan обслуживает конкурирующие запросы; сначала устанавливается завершённый batch, затем публикуются revisions. Результат уже повторно изменившегося source не принимается. [Исходник refresh.ts L58–162](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/skills/runtime/refresh.ts#L58-L162), [L176–279](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/skills/runtime/refresh.ts#L176-L279).

Поиск не требует embeddings или model call. Ленивый lexical index ограничен 1024 bodies, 16 KiB на body и 4 MiB суммарно; одновременно читаются четыре файла. Metadata остаётся доступной для всего eligible catalog. В выдаче есть `coverage`: сколько bodies проиндексировано, сколько записей осталось только с metadata и сколько bodies сокращено. Имя и description имеют двойной вес относительно body, точное совпадение имени стоит первым. [installed-skill-catalog.ts L19–108](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/agents/installed-skill-catalog.ts#L19-L108), [L187–258](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/agents/installed-skill-catalog.ts#L187-L258).

Важно различать индексирование и загрузку инструкции. Индекс читает ограниченный префикс; полный `skills_read` не должен выдавать обрезанную инструкцию как успешную. Для не включённых в prompt skills размер полного чтения ограничен 256 KiB с явной ошибкой при превышении. Authority проверяется до и после чтения. Отзыв permission во время индексирования не превращается в обычное неполное покрытие. [installed-skill-catalog.ts L39–108](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/agents/installed-skill-catalog.ts#L39-L108), [L290–316](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/agents/installed-skill-catalog.ts#L290-L316).

### Предложение для Proteus

Развить существующий эксперимент `portable-skill-catalog` на `context_provider/v4` и `tool/v6`: immutable snapshot, revision, bounded lexical index и отдельный поиск. Этот эксперимент уже предоставляет explicit roots, namespaced IDs, лимиты чтения, refresh/load и проверку `id + sha256 + catalog_path`; повторять их в новом модуле не нужно. Его текущий каталог читает весь ограниченный `SKILL.md` для SHA256, а затем отбрасывает body. Поэтому progressive disclosure уже уменьшает контекст модели, но ещё не доказывает уменьшение файлового I/O. Проверенный исходник эксперимента: [catalog.rs L98–309](https://github.com/Qweasd123tg/proteus-modules-dot/blob/ea7409b30edec9a84a842a36d6ec56d0fbdd3059/examples/portable-skill-catalog/src/catalog.rs#L98-L309), [load_skill L311–364](https://github.com/Qweasd123tg/proteus-modules-dot/blob/ea7409b30edec9a84a842a36d6ec56d0fbdd3059/examples/portable-skill-catalog/src/catalog.rs#L311-L364).

У этого эксперимента отдельный SDK pin `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`. Совпадение названий contracts — основание для разработки адаптации, но не доказательство проверенного запуска на Core `125a9eb`; перед внедрением нужен отдельный compatibility pass. [README эксперимента L1–5](https://github.com/Qweasd123tg/proteus-modules-dot/blob/ea7409b30edec9a84a842a36d6ec56d0fbdd3059/examples/portable-skill-catalog/README.md#L1-L5).

Минимальный первый этап — `Arc<CatalogSnapshot>` внутри каждого процесса, reuse неизменившихся parsed facts и single-flight построение индекса. Background watcher можно добавить позже: для первых потребителей достаточно явного refresh. Два отдельных provider/tool процесса не разделяют `Arc`; нельзя обещать общий межпроцессный cache без отдельного решения по ownership и failure domain.

Обязательные условия:

- Ключ cache включает source identity, revision и invocation settings. Сам cache не выдаёт permission.
- Каждый load заново проверяет disabled settings из текущего invocation snapshot, ожидаемый digest и вычисленный путь. Он не подменяет этот snapshot mutable UI state. `search` не разрешает instruction read или выполнение scripts.
- Запрет, полученный в текущей invocation, нельзя отменить старым снимком; вывод остаётся source-annotated недоверенными данными.
- При metadata-only coverage пустая выдача не доказывает отсутствия подходящего skill.
- Изменения references/assets не покрываются SHA256 только `SKILL.md`; при расширении формата нужна отдельная семантика их revision.
- Бюджеты OpenClaw — пример, а не обязательные defaults Proteus. Существующие более строгие лимиты importer не нужно автоматически расширять.

Proteus уже передаёт `SkillRuntimeSettings` и `ExecutionAttribution` в `tool/v6` и `context_provider/v4` из той же immutable сборки. Это подходящее место для корректного scope, без нового memory/search slot. [Process architecture L758–774](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/docs/architecture/process-module-architecture.md#L758-L774).

## Стабильность prompt и бюджет инструментов

### Наблюдение в Hermes

Deferred-tool catalog сортирует источники и инструменты детерминированно, чтобы не менять bytes cached prefix без причины. Сначала пробует полный список, затем только имена; при переполнении сворачивает крупнейшие группы в summary, сохраняя небольшим источникам видимость. Бюджет оценивается как `ceil(chars / 4)`: это приближение tokens, не точный размер JSON или provider-specific wire request. [tool_search_catalog.py L265–335](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/tools/tool_search_catalog.py#L265-L335).

Изменившийся skills index не заставляет Hermes пересобирать system prompt на каждом turn. Реализация сравнивает текущий набор с baseline prompt, передаёт полную delta после cached prefix и не повторяет ту же delta без изменений. Режимы MoA и Codex app-server здесь исключены, поскольку используемый transcript sidecar у них отсутствует. Это ограниченный конкретный механизм, а не универсальный протокол всех runtimes. [skills_index_delta.py L102–142](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/skills_index_delta.py#L102-L142).

Память Hermes также использует frozen snapshot в system prompt, а live state виден через tool responses; документация предупреждает, что изменения становятся baseline следующей сессии. Этот компромисс сохраняет prefix, но увеличивает риск устаревшего контекста в длинной сессии. [Документация Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory).

### Предложение для Proteus

`tool-schema-budget` — небольшой Rust hook, который получает уже допущенные `ToolSpec`, считает суммарные canonical serialized bytes, сохраняет детерминированный порядок и возвращает подмножество, укладывающееся в лимит. Metadata результата может объяснить число исключённых tools и использованный бюджет. Это ограничение canonical descriptors, а не обещание точного token budget конкретного провайдера.

Точная граница — `BeforeToolSelection`, а не `BeforeModel`. `ToolSelectionOutput::validate_against` разрешает переупорядочить или исключить кандидатов, но запрещает изменить или придумать descriptor. Hook chain повторно проверяет результат и относительно первоначальных кандидатов, и относительно уже выбранных предыдущим hook tools. Следовательно, сокращать descriptions, менять JSON Schema или возвращать отложенный инструмент под новым именем в этом hook нельзя. [tool_selection.rs L93–109](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/tool_selection.rs#L93-L109), [hook.rs L159–187](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/hook.rs#L159-L187).

Если обязательный целый descriptor не помещается, нужен явный отказ или согласованная стратегия отбора, а не обрезанный JSON. Deferred discovery имеет смысл только при реально доступном пути describe/invoke; простое скрытие большинства tools без восстановления доступности ухудшит выполнение задач. Ожидаемое уменьшение prompt bytes — гипотеза до измерения на Proteus.

## Ограниченное восстановление процессов и памяти

### Наблюдение в Hermes и OpenClaw

Hermes plugin host помечает proxy handles поколением процесса: старый handle не должен случайно обратиться к новому объекту с тем же числовым ID. После смерти host используется monotonic clock и лимит трёх рестартов за 600 секунд; плагин, убивший host во время loading, исключается из списка восстановления. Текущий вызов получает ошибку; восстановление процесса само по себе не повторяет его действие. [plugin_host.py L72–90](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/hermes_cli/plugin_host.py#L72-L90), [L175–205](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/hermes_cli/plugin_host.py#L175-L205).

MemoryManager отдельно ограничивает зависшие внешние вызовы. Timeout prefetch — восемь секунд; admission gate учитывает до четырёх stalled calls и максимум 16 in-flight, включая orphan calls, на пару profile home/provider. Background writes сериализуются. Session-end extraction и переключение session binding выполняются одной FIFO-операцией, чтобы поздняя запись не попала в другую сессию. При обязательном checkpoint API v2 pre-compression failure не считается успехом. [memory_manager.py L39–57](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/memory_manager.py#L39-L57), [L203–226](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/memory_manager.py#L203-L226), [L633–650](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/memory_manager.py#L633-L650), [L693–731](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/memory_manager.py#L693-L731).

У OpenClaw есть revoke-able capability lease и timeout wrapper для hooks. Однако revoke lease — проверка действительности доступа, а timeout wrapper лишь прекращает ожидание Promise; ни то, ни другое не является OS sandbox или гарантированным завершением произвольного кода. [capability-lease.ts](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/plugins/capability-lease.ts), [hook-timeout.ts L4–20](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/plugins/hook-timeout.ts#L4-L20).

### Что Proteus уже имеет

Pinned Core уже владеет bounded invocation broker, лимитами очередей по числу кадров и bytes, поколениями, отдельным наблюдением child exit и priority control lane. Idle ожидание основано на notification/revision, а не обязательном busy polling. Cooperative cancellation адресна; истечение grace period сбрасывает весь component. Следующая invocation lazily запускает новый child с handshake. Текущий вызов не повторяется автоматически. [Process architecture L610–645](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/docs/architecture/process-module-architecture.md#L610-L645), [L697–739](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/docs/architecture/process-module-architecture.md#L697-L739).

Поэтому новый governor не должен дублировать transport, подменять wire-v3 или вводить общий failure domain для 18 независимых процессов. Полезный дополнительный предмет проектирования — restart-window budget, circuit-breaker с явным degraded state и согласованное admission для длительных внешних операций. Это работа на существующей lifecycle boundary Core/process-host, не способность произвольного `tool/v6` управлять соседними процессами. Необходимость изменения следует подтверждать конкретным сценарием повторных падений; само наличие механизма в Hermes недостаточно.

RAM/CPU quotas — отдельный возможный проект, не следствие bounded RPC и не часть обещаний этого модуля. Proteus `restricted` ограничивает OS-grants процесса и поддерживает один configured export; trusted остаётся default. Смена языка на Rust не создаёт filesystem/network sandbox. [OS Launch Policy L143–182](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/docs/architecture/process-module-architecture.md#L143-L182).

### Что не следует переносить

- Hermes по умолчанию импортирует plugins in-process; неизвестное значение isolation тоже возвращается к in-process. Для fail-closed конфигурации Proteus такое поведение не подходит. [plugin_isolation.py L95–104](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/hermes_cli/plugin_isolation.py#L95-L104).
- Hermes plugin-host wire обслуживает входящие запросы thread-per-request и читает строку без показанного здесь per-frame cap. Нельзя переносить это вместо существующего bounded broker Proteus. [plugin_host_wire.py L340–353](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/hermes_cli/plugin_host_wire.py#L340-L353). Отдельный Hermes managed-worker transport, напротив, явно ограничивает JSON frame до 4 MiB. [managed_worker.py L90–106](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/managed_worker.py#L90-L106).
- Timeout external memory prefetch не убивает Python thread: он продолжает работу, а admission gate только сдерживает накопление новых зависших вызовов. Это нельзя описывать как hard cancellation. [memory_manager.py L357–393](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/memory_manager.py#L357-L393).

## Делегирование как выбор маршрута

### Наблюдение в Hermes

Delegation provider отвечает на вопрос о маршруте одной задачи и возвращает plain JSON. Core сохраняет spawn, isolation, depth, concurrency, fan-out остановки, progress и result lifecycle. Reserved task fields нельзя переопределить; backend-specific schema должна быть детерминирована для config. Недоступный выбранный backend отказывает, а не молча запускает ребёнка по другому маршруту. [delegation_provider.py L1–47](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/delegation_provider.py#L1-L47), [L84–110](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/delegation_provider.py#L84-L110), [delegation_registry.py](https://github.com/NousResearch/hermes-agent/blob/820967473d4d5b6777d3a9419def4be422711d16/agent/delegation_registry.py).

### Предложение для Proteus

`delegation-policy-router` на Rust может вычислять рекомендацию из задачи, доступных capabilities и budget: разрешённый profile/route либо объяснимый отказ. Он не должен принимать model-generated credentials или расширять authority выбранного slot. Первое безопасное исполнение — data-only tool, результат которого обрабатывает уже выбранный workflow; такой tool сам по себе ещё не включает автоматическое делегирование.

Автоматическая смена workflow/model или новый routing contract требуют отдельной интеграции с Core. В текущей модульной архитектуре наличие tool/workflow exports в одном component не даёт прямого cross-export исполнения; вызовы проходят host policy/admission. Нельзя выдавать JSON-рекомендацию за authority token. [Process architecture L744–774](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/docs/architecture/process-module-architecture.md#L744-L774).

## Доверенное происхождение результата и повтор действий

OpenClaw хранит effect provenance у host, а не в произвольном JSON ответа инструмента. Состояния различают `not_started`, `read_completed`, `failed_no_effect`, `mutation_committed` и `uncertain`. Начало первого возможного эффекта отмечает владелец операции; вложенный no-start не может стереть эффект, уже начавшийся выше. При недостатке доказательств результат остаётся uncertain. Ownership инструмента привязан к реальной регистрации и паре plugin/tool, не только к совпадению имени. [tool-effect-receipt.ts L6–47](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/agents/tool-effect-receipt.ts#L6-L47), [L62–105](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/agents/tool-effect-receipt.ts#L62-L105), [tool-metadata.ts L31–102](https://github.com/openclaw/openclaw/blob/c3aa6e15e093c6dc8ab55533a936e4cbe995942e/src/plugins/tool-metadata.ts#L31-L102).

Для Proteus это полезная идея будущего execution recorder, но не готовый отдельный AfterTool-модуль. Pinned `hook/v6` разрешает `AfterTool → ToolOutput { output: String }` и изменяет только `result.output`; доверенного settlement sidecar этот ответ не создаёт. [hook.rs L78–101](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/hook.rs#L78-L101), [L207–210](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/hook.rs#L207-L210).

Если такая возможность понадобится, минимальное корректное место — Core-owned invocation record с generation/request identity и закрытым обновлением provenance. Отдельный read-only tool может показывать статус, но не выпускать доказательство отсутствия эффектов. Для мутирующего действия timeout после начала записи запроса не доказывает ни отсутствие выполнения, ни rollback; существующий запрет автоматического retry нужно сохранить. [Process architecture L720–739](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/docs/architecture/process-module-architecture.md#L720-L739).

## Очерёдность полезных изменений

| Возможность | Минимальная интеграция | Что действительно новое | Основное ограничение |
|---|---|---|---|
| Бюджет canonical ToolSpec | `hook/v6 / BeforeToolSelection` | Суммарный byte budget и объяснение отбора | Только целые существующие descriptors; не provider-token accounting |
| Снимки и поиск skills | Развитие `portable-skill-catalog`, `context_provider/v4` и `tool/v6` | Reuse parsed facts, bounded index, coverage | Cache не заменяет актуальные settings и digest check |
| Data-only delegation router | Tool плюс явное использование выбранным workflow | Отделение route policy от execution lifecycle | Рекомендация не переключает Core и не выдаёт authority |
| Restart-window governor | Существующий Core/process-host lifecycle | Circuit-breaker поверх уже имеющегося lazy restart | Не самостоятельный tool и не новый transport или sandbox |

Effect receipt recorder следует рассматривать отдельно, когда появится конкретная потребность в доказуемой retry/reconciliation семантике. Его нельзя обещать как пятый маленький plugin на текущем hook contract.

Ожидаемые результаты первых двух изменений — меньше повторного чтения/разбора и меньший model-visible descriptor payload. До измерения холодного и повторного запроса, объёма прочитанных bytes, размера canonical request и памяти процесса это остаётся проверяемой гипотезой, а не установленным ускорением.
