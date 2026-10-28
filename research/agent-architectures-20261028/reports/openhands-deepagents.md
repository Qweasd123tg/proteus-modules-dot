# OpenHands и Deep Agents для развития модулей Proteus

Проверено **28 октября 2026 года, UTC**. Предмет — алгоритмы управления контекстом, исполнением и делегированием, а не инфраструктура тестирования.

**Главный вывод:** полезнее перенести три узких механизма, чем подключать ещё один Python harness: сохранение больших результатов у источника до RPC, структурно безопасные границы сокращения истории и привязку видимости инструментов к реально загруженным skills. Отдельное направление — явный контракт того, что именно наследует субагент. Все предложения ниже — проектные; в Proteus они этой работой не внедрены.

## Актуальные проекты и закреплённые версии

| Проект | Текущий официальный источник | Закреплённый HEAD | Последний GitHub release при проверке |
|---|---|---|---|
| OpenHands Software Agent SDK | [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk), не архивирован | [7486c1d16ef67e00a57d6eec8baf48c8efdd7be2](https://github.com/OpenHands/software-agent-sdk/commit/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2), 28 октября, 16:20:53 UTC | [v1.59.0](https://github.com/OpenHands/software-agent-sdk/releases/tag/v1.59.0), 28 октября |
| LangChain Deep Agents | [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents), не архивирован | [cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca](https://github.com/langchain-ai/deepagents/commit/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca), 28 октября, 14:54:51 UTC | [deepagents==0.7.32](https://github.com/langchain-ai/deepagents/releases/tag/deepagents%3D%3D0.7.32), 23 октября |

Оба изученных SDK распространяются по MIT: [OpenHands LICENSE](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/LICENSE), [Deep Agents SDK LICENSE](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/LICENSE). При переносе существенных фрагментов надо сохранить соответствующие уведомления. Это не проверка лицензий всех транзитивных зависимостей или hosted-сервисов.

HEAD и release — разные точки. Исходники анализировались именно на HEAD выше; не следует автоматически приписывать все обнаруженные детали опубликованному release. Версии в изученных manifests — OpenHands SDK 1.59.0 и deepagents 0.7.32; последний также сохраняет классификатор Beta. [OpenHands manifest](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/pyproject.toml#L1-L7), [Deep Agents manifest](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/pyproject.toml#L1-L16).

Актуальная архитектурная основа OpenHands — **Software Agent SDK**. В одном репозитории четыре пакета: SDK, tools, workspace и agent-server; приложения Agent Canvas и CLI потребляют их интерфейсы. Tools исполняются рядом с агентом в выбранном окружении, а не обязательно «через API workspace». Простая смена класса workspace поэтому не равнозначна добавлению проверки полномочий на каждый tool call. [Официальная архитектура](https://docs.openhands.dev/sdk/arch/overview).

Deep Agents — конкретный harness поверх LangChain/LangGraph. Здесь исследован Python SDK, а не Managed Deep Agents и не терминальное приложение dcode. Перенос всего графового runtime не нужен для использования перечисленных алгоритмов. [Точка сборки harness](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/graph.py).

## Что уже есть в Proteus

Сравнение опирается на Core `125a9eb4088991513e9f61d899469be2076e266c` и Modules `5fa8978684a37e8083c64f4d6cf0289e72450c6a`, а также предыдущие отчёты этой серии. Повторно предлагать journal, replay, bounded RPC, role permits, snapshots и общий hook framework не требуется.

Прямое чтение подтвердило более конкретные пересечения:

- Shell уже ограничивает выдачу, сохраняет начало и конец, сообщает `dropped_bytes`, `truncated`, `exit_code`. Успешный вызов инструмента не равен нулевому exit code процесса. Это **не новая дельта Deep Agents**. [Текущий shell output](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/tool/shell-tool/src/unified_exec/output.rs#L12-L151).
- Есть исследовательская библиотека `research/tool-output-artifacts`, но она не включена в runtime exports и принимает уже готовый `ToolResult`. Это не захват потока у источника. [Статус прототипа](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/research/tool-output-artifacts/README.md), [process_result](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/research/tool-output-artifacts/src/lib.rs#L42-L157).
- Compactor уже делает модельную summary, сохраняет пользовательские anchors и разделяет request-scoped context. Host проверяет неизменность существующих message/part identities и связи replacements. [Compactor](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/codex-context-preparation/src/compaction.rs#L15-L79), [identity validation](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/compaction_validation.rs#L17-L128).
- `skill-pack` уже публикует каталог и загружает тело skill по имени. Новый каталог или ещё один поиск skills сами по себе не нужны. [Текущий skill-pack](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/tool/skill-pack/src/lib.rs#L1-L137).

## Захват больших результатов до RPC

### Подтверждённый механизм Deep Agents

`BaseSandbox.execute_with_offload` использует capture-at-source: команда выполняется в sandbox, output сохраняется там же, а наружу передаётся небольшой preview. В текущем wrapper установлен дисковый cap 10 MiB; после достижения cap остаток потока дренируется. Exit code исходной команды извлекается отдельно от exit code pipeline. Отдельные признаки различают перенос вывода в файл и безвозвратную потерю части вывода. [Capture wrapper](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/backends/sandbox.py#L1367-L1461), [тип результата](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/backends/protocol.py#L810-L890).

Это важнее обычного post-processing: большой текст не нужно сначала материализовать в ответе и отправлять через RPC, чтобы только затем обрезать. Документация чтения также предусматривает пагинацию на стороне sandbox, а не загрузку всего текстового файла клиентом. [Постраничное чтение](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/backends/sandbox.py#L1715-L1772).

### Предлагаемый Rust seam

Развить **существующий shell tool**, добавив заменяемый сборщик `OutputCapturePolicy` и ограниченный `ArtifactSink` непосредственно в его output-reader path:

```text
process stdout/stderr
  → bounded capture sink + bounded head/tail preview
  → CaptureReceipt
  → существующий ToolResult и bounded RPC
```

Receipt должен различать:

- идентичность capture и владельца session/invocation;
- сохранённые bytes и факт достижения cap;
- `complete / truncated / interrupted / unknown`;
- отдельно исход процесса и исход записи artifact;
- доступный диапазон чтения и подтверждённую ссылку на artifact.

Для первой версии достаточно локального shell. Не нужен новый общий process slot; нельзя выдавать `AfterTool` hook за source capture, поскольку к этому моменту результат уже собран. Существующий исследовательский artifact processor можно использовать как источник формата preview, но не считать решением memory/transport pressure.

Сохранение artifact создаёт новую обязанность по квотам и сроку хранения. Нужны per-artifact и per-session caps, ограниченное число файлов, обработка disk-full и закрытие writer при отмене. Artifact должен принадлежать runtime/tool и проверяться на чтении; произвольная строка пути из ответа модели не становится разрешением на доступ. Проектные файлы и внутренние captures желательно хранить раздельно.

**Ожидаемая польза:** сохранить доступ к большим диагностическим данным, не увеличивая RPC frames и model-visible контекст. Уменьшение peak RSS возможно относительно post-hoc materialization, но не доказано относительно уже bounded collector Proteus; существующий collector уже защищает RAM ценой потери middle output.

**Ограничения донора:** drain после cap не ограничивает CPU и не завершает бесконечно пишущий процесс. В исходнике рядом с wrapper есть противоречащий ему старый комментарий про SIGPIPE; описанный здесь вывод основан на фактическом pipeline `head -c ...; cat > /dev/null`. Не стоит переносить shell wrapper буквально: Rust reader позволяет сохранить существующие cancellation и process lifecycle. Равенство размера cap само по себе не доказывает, что были отброшены дополнительные bytes; для точного `truncated` нужен отдельный учёт.

## Структурно безопасное сокращение истории

### Подтверждённый механизм OpenHands

OpenHands отделяет неизменяемые события от представления для модели. `Condensation` записывает IDs исключаемых событий, summary и позицию вставки; исходные события не переписываются этой операцией. `View` вычисляет допустимые места разреза как пересечение ограничений. [Condensation](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/event/condenser.py#L12-L103), [View](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/context/view/view.py#L22-L48).

Ограничения не сводятся к числу сообщений:

1. Tool call и его observation не разделяются разрезом. [Matching](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/context/view/properties/tool_call_matching.py#L16-L95).
2. Несколько actions из одного LLM response остаются целой группой. [Batch atomicity](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/context/view/properties/batch_atomicity.py#L10-L88).
3. Tool loop, начатый подписанным thinking block, сохраняется целиком. Это связано с требованиями конкретных provider representations, а не с универсальным правилом любого текста. [Tool-loop atomicity](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/context/view/properties/tool_loop_atomicity.py#L14-L126).
4. При позднем observation после recovery error представление убирает дубликат `tool_call_id`; в текущей политике выигрывает первый. [Observation uniqueness](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/context/view/properties/observation_uniqueness.py#L20-L74).

### Предлагаемый Rust seam

Pure helper `context_segments` принимает canonical history и host-verified provider constraints; возвращает допустимые границы, protected spans и причины отказа. Он вызывается из существующего context-preparation алгоритма **до** выбранного keep-tail или selective compaction:

```text
CanonicalMessage[]
  → index call/result and atomic groups
  → legal cut boundaries
  → budget-based candidate
  → existing identity validation + structural validation
```

В Proteus уже есть `ContentPart::ToolCall`, `ToolResult` и `Reasoning { signature }`, поэтому базовое matching можно вычислить без копирования Python event hierarchy. [Canonical parts](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/model_standard/content_part.rs#L24-L136). Если граница LLM batch потеряна при разбиении canonical messages, её нельзя восстановить эвристикой: понадобится явная host-owned group identity либо консервативное сохранение целого блока.

Существенное отличие от готовой проверки Proteus: текущая identity validation удостоверяет происхождение и неизменность записей, но не вычисляет closure tool-call групп. Это дополнительный алгоритм, а не замена существующей валидации.

**Не объявлять текущую compaction сломанной.** Прочитанный compactor заменяет всю compactable history summary и user anchors; selective retention tool tail там не реализован. Structural planner особенно полезен при дальнейшем keep-tail, выборочной compaction и принятии подготовленной summary со свежим suffix. Он не должен удалять незавершённый call из canonical journal.

Не копировать policy «первый observation всегда истинный» в исполнение Proteus. Для model view нужно одно согласованное представление, но поздняя запись результата может содержать более точный факт внешнего эффекта; journal и settlement должны его сохранить. При конфликте — явная диагностика/host reconciliation, не молчаливое переписывание результата.

**Стоимость:** hash-index по call IDs и линейный проход по сообщениям, затем выбор допустимой границы. Предлагаемая Rust реализация может быть линейной по числу parts плюс размеру групп; это не оценка сложности всех Python fallback-enforcement loops. Никакого измеренного ускорения не заявляется.

### Дополнительная оптимизация представления

OpenHands кеширует производный `View`: обычное добавление применяет только новый tail, смена ветки перестраивает представление. Cache не является вторым persistent event store. [Incremental view](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/conversation/state.py#L367-L430). Для Proteus это возможная оптимизация конкретной дорогой projection после профилирования, а не основание снова создавать journal или утверждать, что текущий Core каждый раз сканирует всю историю.

## Видимость инструментов вслед за загруженным skill

### Подтверждённый механизм Deep Agents

В `metadata.include_tools` skill перечисляет нужные инструменты. Они раскрываются после чтения или pin этого skill и остаются видимы, пока соответствующая запись присутствует в эффективном контексте. Middleware выполняется после summarization, сохраняет record раскрытых tools и проверяет его при последующем вызове. [Описание механизма](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/middleware/skills.py#L971-L1013), [disclosure и вызов](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/middleware/skills.py#L1302-L1431).

Здесь есть конкретный переносимый алгоритм: **выбор tools обусловлен не только similarity query, но и присутствием инструкции, объясняющей их правильное использование**.

### Предлагаемый Rust seam

Расширить существующие skill catalog/selector чистой политикой `skill_tool_visibility`:

```text
effective context anchors + SkillDigest
  + already authorized candidate ToolSpecs
  → stable ordered subset + disclosure reasons
```

Факт загрузки должен происходить из успешного host-recorded skill tool result и содержать skill identity/digest. Не выводить его из фразы модели «я прочитал skill». После compaction, смены skills settings или ревизии каталога пересчитывать visibility. Tool schemas материализуются только для пересечения связанных tools с текущими допустимыми кандидатами. Видимость не выдаёт новые grants.

Это **не готовый plug-in только на нынешнем `BeforeToolSelection`**: текущий `ToolSelectionInput` содержит request и candidates, но не весь effective context/disclosure snapshot. `BeforeModel` видит request, однако его `ModelContext` response не меняет tools. [Selection contract](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/tool_selection.rs), [Hook events и responses](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/hook.rs#L27-L102). Нужно либо вызывать pure policy из workflow с доступом к истории до selection, либо явно расширить typed input. Нельзя подменять это неучтённым межпроцессным global cache.

**Новое относительно предыдущих отчётов:** не очередной schema byte-budget и не каталог skills, а зависимость между инструкцией и инструментом с ограниченным временем жизни. Byte-budget остаётся отдельным последним фильтром.

**Ограничения донора:** `_find_skill_reads` считает достаточным любое успешное `read_file`, включая частичное чтение и впоследствии clipped content. Поэтому данный механизм не доказывает полного прочтения инструкций. [Точная логика](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/middleware/_skill_tools.py#L265-L301). Для Proteus лучше явный digest/body coverage, если требование действительно состоит в загрузке полного skill. Кеш Deep Agents skills загружается один раз на thread и обновляется через сброс metadata; это не автоматический watcher изменений. [Cache semantics](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/middleware/skills.py#L916-L933).

## Явный контракт контекста субагента

### Что действительно наследуют доноры

Deep Agents по умолчанию создаёт отдельную message history, но передаёт другие разрешённые поля state и принимает часть изменённых полей назад. Удаляются private/excluded fields, неизменённые поля не возвращаются повторно, чтобы не удвоить additive reducer. Это **изоляция контекста, а не изоляция всей памяти**. [State handoff](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/middleware/subagents.py#L404-L453), [input и merge](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/middleware/subagents.py#L747-L836). StateBackend также может разделяться родителем и детьми; записанные ребёнком файлы остаются доступны остальным. [Официальные backends](https://docs.langchain.com/oss/python/deepagents/backends).

OpenHands TaskManager создаёт отдельную conversation, но использует родительский working directory. MCP configuration наследуется точно, а ограничение набора обычных tools включается отдельным `SubAgentScope.tools`, по умолчанию false. [Рабочий каталог](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-tools/openhands/tools/task/manager.py#L307-L342), [scope](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/subagent/scope.py#L39-L101).

### Предлагаемый Rust seam

Отдельная pure policy `handoff_projection` могла бы выбирать небольшой task capsule вместо безусловного копирования всего родительского transcript:

- task + проверяемые anchors/ссылки на evidence;
- явно выбранные history segments и budget;
- read-only artifact references либо отдельный workspace;
- возвращаемую result schema и разрешённые artifact exports.

Контекст, mutable state, workspace и authority должны иметь **четыре независимых режима**. Флаг `isolated` без этих уточнений слишком неоднозначен. Не передавать approval cache, credentials и произвольные private channels вместе с историей. Core AgentControl остаётся владельцем процессов, scopes и permits; policy только строит разрешённую проекцию.

Начальный scope — data-only capsule и компактный отчёт ребёнка, без универсального state merge. Если позднее нужен merge, предпочтительны явные разрешённые fields/операции и revision checks, а не возврат всей сериализованной state. Это дополняет ранее предложенный delegation router: router выбирает исполнителя, projection выбирает передаваемые данные.

**Ожидаемая польза:** меньше повторного контекста у узких субзадач и меньше случайного загрязнения state. Обратная сторона — ребёнку может не хватить фактов; ссылки на artifacts и ограниченное дозапрашивание предпочтительнее молчаливого расширения полномочий. Ускорение и экономия токенов не измерены.

## Границы исполнения которые нельзя переносить как гарантии

1. **Permissions middleware не равно sandbox.** В Deep Agents правила применяются к built-in filesystem tools, но не к прямым вызовам backend; child permissions могут целиком заменить parent rules. Обычный `FilesystemBackend(root_dir=...)` без virtual mode также не является security boundary, а shell может обходить path-only ограничения. [Точный SDK contract](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/graph.py#L494-L518), [официальные предупреждения](https://docs.langchain.com/oss/python/deepagents/backends).

2. **CompositeBackend — маршрутизатор пространства имён, не ACL.** Longest-prefix routing удобно разделяет `/workspace/`, `/memories/` и внутренние artifacts. Но маршруты не предоставляют сами по себе tenant isolation, atomic cross-backend rename или единую транзакцию. В Proteus потенциальный перенос — bounded route resolver внутри конкретных filesystem tools с сохранением host path authority, не общий привилегированный filesystem service. [Routing implementation](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/backends/composite.py#L195-L286).

3. **Наследуемый child budget не равен общему family reservation.** OpenHands `TaskManager._create_task` выбирает лимит из agent definition либо родителя и передаёт его новой conversation. Отдельные лимиты детей сами по себе не устанавливают атомарное резервирование общего остатка при параллельном запуске; расход дочерних conversations агрегируется в родительские metrics отдельно. [Передача limits](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-tools/openhands/tools/task/manager.py#L255-L334), [агрегация metrics](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-tools/openhands/tools/task/manager.py#L500-L509). Имеющееся host-owned admission Proteus не следует заменять только такими настройками. Полный runtime enforcement SDK в этой работе не проверялся исполнением.

4. **Timeout ожидания не всегда останавливает работу.** Deep Agents default `agrep` использует timeout вокруг `asyncio.to_thread` и прямо предупреждает, что thread продолжит работу; некоторые старые backends не принимают `max_count`, и их результат обрезается после полного materialization. [Backend protocol](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/backends/protocol.py). Для Rust seam нужны cancellation-aware execution и реальные ceilings на чтение/выдачу, а не только timeout клиента.

5. **Typed Action/Observation полезны как разделение, но уже не новинка для Proteus.** OpenHands хранит schema-bearing action, tool-call identity и typed observation отдельно от model rendering. Proteus уже имеет canonical calls/results/provenance; перенос Python class hierarchy или собственного event log был бы дублированием. [OpenHands schemas](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/tool/schema.py#L333-L449), [observation identity](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/event/llm_convertible/observation.py#L18-L80).

## Рекомендуемая последовательность

| Очерёдность | Дельта | Реальная точка интеграции | Граница готовности |
|---|---|---|---|
| 1 | Source capture с artifact receipt | Внутри существующего shell tool output reader | Спроектировать caps, чтение и ownership; не выдавать post-hoc prototype за runtime |
| 2 | Safe context segments | Pure Rust helper в существующем context preparation | Нужен для selective keep-tail; нынешняя whole-history compaction не объявляется ошибочной |
| 3 | Skill anchored tool visibility | Skill-pack + selector/workflow | Проверяемый loaded-skill snapshot; нынешнего DTO недостаточно для standalone hook |
| 4 | Handoff projection | Подготовка входа AgentControl | Сначала task capsule без общего state merge |

Второй journal, новый универсальный checkpointer, общий pool вместо 18 subprocess modules и перенос LangGraph runtime для этих задач не нужны.

## Проверка и оставшиеся ограничения

Прочитаны официальные docs, GitHub metadata, release records и закреплённые исходники. Ключевые сравнительные утверждения дополнительно сверены непосредственно с Proteus contracts/modules. Локально сохранены report, evidence manifest и копии прочитанных источников.

- **Чтение источников:** выполнено; permission blockers не возникли.
- **Сборки, тесты, CI и запуск присланного/upstream кода:** не выполнялись.
- **Изменение исходников Proteus или upstream:** не выполнялось.
- **Remote writes и публикация:** не выполнялись.
- **Производительность, runtime enforcement и совместимость предложений:** не установлены исполнением; изложены проверенные механизмы и проектные seams.
- **Открытые интеграционные вопросы:** ownership/retention artifacts; передача batch identity при её отсутствии; typed disclosure snapshot перед tool selection; точные поля handoff capsule.

Отсутствие свойства в прочитанном контракте не является доказательством отсутствия любой реализации во всём репозитории. Для adoption сначала нужен отдельный контрактный review выбранного seam, не безусловное копирование донора.

