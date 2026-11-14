# P2: output budget склеивает отчёты разных субагентов внутри успешного wait_agent

Проверено 2026-11-13 на remote HEAD Core `89997df995df7c39b713e16aba216ecb19c8f497` и Modules `3270dc0f894eaf4d0360306052b806099b8f5351`. Remote HEAD повторно проверены `git ls-remote origin HEAD`; оба production checkout чистые. Commit/push/PR нет.

## Подтверждённый результат

При включённом **opt-in `hook.output_budget`** с `max_bytes=16000`, `head_bytes=12000` шесть завершённых агентов возвращают по 8000 байт. `wait_agent` забирает все шесть результатов, но native Anthropic получает **синтаксически валидный JSON только с двумя агентами**. У второго агента начало summary принадлежит worker_1, а конец принадлежит worker_5:

```text
path = /root/worker_1
summary = UNIQUE_WORKER_1_REPORT\nBBBB...FFFF\nUNIQUE_WORKER_5_REPORT
```

Отчёты worker_2, worker_3, worker_4 исчезают из model-visible результата целиком. Модель не получает сообщения об усечении: `is_error=false`, `timed_out=false`, metadata не имеет `output_truncated`, текст не содержит truncation marker. Это не просто слишком короткий ответ или невалидный JSON: данные от одного ребёнка оказываются подписаны именем другого.

Повторный `wait_agent(timeout_ms=0)` возвращает `{"timed_out":true,"agents":[]}`. `list_agents` показывает шесть completed-статусов, но не возвращает summary. Поэтому повтор обычного чтения через collaboration API не восстанавливает отчёты. **Утрату данных с диска навсегда не утверждаем:** при активном hook исходный полный batch из шести результатов сохранён в canonical `ToolEffectRecorded`; существуют и истории детей. Повреждённая версия сохранена в `ToolResultRecorded` и фактически отправлена модели. Ручное чтение raw journal может восстановить данные, но не исправляет штатный результат `wait_agent`.

## Настоящая цепочка

`Core server stdio → coding.codex_loop process → native Anthropic HTTP adapter → spawn_agent ×6 → настоящие child Proteus processes → wait_agent → AfterTool output_budget → native Anthropic HTTP capture`.

Синтетические части: локальный HTTP endpoint вместо живой модели и side-effect-free workflow ребёнка, возвращающий различимые буквы и маркеры. Все tool invocations, collaboration queue, child process runner, hook, serialisation и journal настоящие. HTTP endpoint ждёт все шесть `SubagentFinished`, чтобы проверить накопившийся completion batch, а не зависеть от случайного порядка завершения.

| Сценарий | Child summaries | Первый wait в HTTP | Результат |
|---|---:|---:|---|
| Без hook | 6 × 8000 bytes | 48819 bytes | Все 6 отчётов целые |
| output_budget 16000/12000 | 6 × 8000 | 16000 | Валидный JSON с 2 агентами; worker_1 содержит хвост worker_5 |
| Точный повтор | 6 × 8000 | 16000 | То же смешение |
| Короткий контроль с hook | 6 × 1000 | 6819 | Все 6 отчётов целые |
| Дополнительный Core-cap edge, без hook | 8 × 16000, quote-heavy payload | 200000 | Невалидный JSON с явным Core truncation marker; очередь уже пуста |

Все пять root turns завершились `Success`. В первых четырёх по десять native HTTP запросов, в последнем двенадцать. Child role timeout ни разу не сработал: это новая граница, не повтор ранее подтверждённого сокрытия `timed_out` в TaskTool.

Последняя строка не означает, что любой штатный batch ломает Core cap: для неё намеренно используются восемь сильно JSON-экранируемых summary по 16000 байт, роль без меньшего `max_summary_bytes`; это дополнительная проверка aggregate byte-budget и не основной realistic сценарий. Core хотя бы сообщает truncation, в отличие от проверенного hook splice.

## Причинная связь

1. [Core `control.rs:295–308`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L295-L308): `drain_completions` удаляет до восьми элементов по количеству, без byte budget. [Константы](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L19-L23) допускают 16000 bytes на summary, то есть большой aggregate даже без JSON escaping.
2. [Core `collaboration/mod.rs:276–308`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/collaboration/mod.rs#L276-L308): `wait_agent` сериализует весь уже потреблённый batch в обычную строку `ToolResult.output`.
3. [Modules `hook-pack/src/lib.rs:69–83`](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/hook/hook-pack/src/lib.rs#L69-L83): `OutputBudget` конкатенирует head и tail без separator, indicator и знания JSON-структуры. В обоих воспроизведениях границы находятся внутри двух разных summary-строк. Получается один синтаксически правильный record, но с чужим хвостом.
4. [Core `bound_tools/hooks.rs:99–119`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_tools/hooks.rs#L99-L119) сохраняет raw effect, затем принимает transformation и записывает его как итог. Выход ≤ budget, поэтому общая дополнительная truncation metadata не возникает.
5. [Core `control.rs:265–278`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L265-L278) использует `view(..., false)` для `list_agents`; terminal payload доступен только в consumed completion. [Документация](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/runtime-and-events.md#L580-L585) также прямо отделяет retained status от payload.

Это связано с ранее найденной несогласованностью output budgeting, но не повтор structured-content bypass: здесь обычный output корректно попадает под лимит, и именно реализация лимита нарушает происхождение результатов плюс completion consumption semantics.

## Условия и ограничения

- Основной дефект требует включённого `hook.output_budget` и достаточно большого batch. В текущем штатном `codex-behavior.toml` включён `codex_compact`, не output_budget; поэтому не объявляется default Codex-поломкой.
- Summaries по 8000 bytes не превышают даже role cap8192, используемый штатным explore-профилем. Достаточна комбинация нескольких обычных отчётов, не нужен oversized single-agent payload.
- Completion order в этих прогонах worker_0…worker_5. При другом порядке тот же алгоритм может смешать другие records либо сделать JSON невалидным.
- Child workflow специально не пользуется инструментами или внешними данными. Живая модель, Desktop, OpenAI HTTP-path и изменения качества решений не тестировались.
- Source review и настоящие runtime прогонки, но не полный workspace suite и не workflow replay. Все binary SHA256 сохранены; использованы уже проверенные сборки текущих HEAD из предыдущего аудита, свежая сборка в этом проходе не выполнялась.

## Направление исправления, без патча

Нужна budgeted model-visible projection, сохраняющая целостность record и identity. Минимальный общий запрет: не сшивать head/tail так, будто удалённых байтов никогда не существовало. Но один separator лишь делает повреждение заметнее и не восстанавливает consumed отчёты.

Для collaboration результат должен быть структурно ограничен до consumption: bounded summaries с явным truncation, возврат целых records, оставление невыданных completions в очереди либо адресный повторно читаемый payload. Общий hook не должен превращать JSON record одного агента в смесь нескольких. Регрессионный тест обязан проверять не только общий размер и валидность JSON, но и идентичность каждого summary его agent path, количество выданных/оставшихся результатов и повторный wait.

## Артефакты и проверка

- `run.py`, `child_workflow.py`: 5 изолированных process/HTTP сценариев, только временные HOME/workspace.
- `verify.py`: diagnostic assertions **PASS** на текущем дефекте.
- `verify.py --expect-complete`: **ожидаемый FAIL**: `wait consumed 6, model received 2; worker_1 contains worker_5 tail`.
- `provider-requests.json`: реальные HTTP requests; `*-events.json`: реальные app-server events и responses.
- `journal-summary.json`: raw batch6 → model-visible2 и границы смешанного record; `*-sessions`: canonical journals, blobs, session identity/config.
- `source-provenance.json`, `provenance.json`: HEAD/clean-status и hashes бинарников.

Запуск: `python3 -B run.py && python3 -B verify.py`. Пути к уже собранным бинарникам и к Core Python SDK helper указаны в скриптах явно; при переносе нужны соответствующие сборки данных revisions.
