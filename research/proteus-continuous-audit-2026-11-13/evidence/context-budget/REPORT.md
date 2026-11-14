# P2: лимиты tool output не ограничивают фактический текст для модели

Проверено 2026-11-13. Remote HEAD: Core `89997df995df7c39b713e16aba216ecb19c8f497`, Modules `3270dc0f894eaf4d0360306052b806099b8f5351`. Рабочие исходники не менялись; commit/push/PR нет.

## Что подтверждено

Одно и то же содержимое проходит разные бюджеты в зависимости от поля `ToolResult`. Core ограничивает `output` и `error`, но не текстовый fallback из `content`. Дополнительный `hook.output_budget` тоже смотрит только на `output`, хотя его настройка описана как максимальный объём результата инструмента.

Реальная цепочка воспроизведения:

`Core server stdio → coding.codex_loop process → tool/v6 process → BoundTools → hook.output_budget process → native Anthropic model process → HTTP capture на 127.0.0.1`.

Core, workflow, hook и адаптер настоящие. Синтетические части: локальный HTTP-сервер вместо провайдера и инструмент, возвращающий безопасные повторяющиеся символы без внешних эффектов. Сервер сначала запрашивает инструмент, затем фиксирует фактическое сериализованное `tool_result.content` следующего запроса.

Для исходных 300000 ASCII-байт:

| Форма результата | Без hook, штатный Core cap 200000 | С hook cap 16000 |
|---|---:|---:|
| `output` | 200000 | 16000 |
| пустой output + `content: Text` | **300000** | **300000** |
| пустой output + `content: Json {body: ...}` | **300011** | **300011** |
| `error` | 200000 | **200000** |
| output = короткие 20 байт, большой скрытый content | 20 | 20 |

Все десять turns завершились успешно, каждый сделал ровно два native HTTP-запроса. При Text/Json `ToolFinished` также содержит полный structured result и не выставляет `output_truncated`/`error_truncated`. Контроль с коротким output доказывает, что structured content не добавляется к любому результату: проблема именно в модели fallback/precedence.

Это не повтор skills whole-chunk loss и не compaction finding. Измерено нарушение per-tool model-visible budget: в проверенном случае Text превышает явно включённые 16000 байт в 18.75 раза. Не проверялись реальные расходы API, качество ответа модели, отказ реального провайдера из-за overflow или исчерпание памяти; таких последствий отчёт не утверждает.

## Причинная цепочка

1. [Core `BoundTools::truncate_result`, строки 524–558](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_tools.rs#L524-L558) ограничивает только два строковых поля. Вектор `content` остаётся без изменений.
2. [Core `finish`, строки 99–119](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_tools/hooks.rs#L99-L119) повторяет этот же truncate до и после AfterTool. Повтор не закрывает пропущенное представление.
3. [Modules `OutputBudget`, строки 69–83](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/hook/hook-pack/src/lib.rs#L69-L83) срабатывает только при `result.output.len() > max_bytes`; `content` и `error` не рассматриваются.
4. [Contracts `text_or_status`, строки 151–178](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/domain/tool.rs#L151-L178) выбирает сначала error, затем output, а при их отсутствии полностью сериализует Text/Json из content.
5. [Native Anthropic `tool_result_block`, строки 319–325](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/request.rs#L319-L325) отправляет этот текст. Именно этот HTTP body сохранён воспроизведением. Native OpenAI использует тот же `text_or_status` на строках 410/415, но его HTTP-путь в этом проходе не запускался.

Важная граница для исправления: [применение `HookResponse::ToolOutput`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/contracts/hook.rs#L207-L209) изменяет только `result.output`. Простая замена `result.output` на `result.text_or_status()` внутри hook может ограничить structured fallback, но **не error**: оставшийся `result.error` имеет более высокий приоритет при сериализации. Нужен согласованный budget фактической model-visible проекции и подходящая семантика contribution, а не только локальная правка условия hook.

Возможное направление: централизовать bounded текстовую проекцию результата с явной диагностикой truncation, сохранить статус ошибки и не резать JSON в невалидную структуру. Если исходный structured payload должен сохраняться для UI/инструментов, его storage budget должен быть отдельным явно определённым контрактом. Это рекомендации, не внесённый патч.

## Проверки и воспроизводимость

- `run.py`, `tool_fixture.py`: десять реальных process-chain сценариев; все данные и HOME создаются во временных директориях, отдельная сессия на каждый сценарий.
- `provider-requests.json`: реальные HTTP bodies, полученные локальным endpoint. `*-events.json`: фактические Core events и ответы. `summary.json`: компактные размеры и результаты.
- `verify.py`: диагностические assertions PASS. `verify.py --expect-budgeted`: **ожидаемый FAIL**, первая ошибка `text-hook-False: 300000 > 200000`. Green диагностики не означает исправленный продукт.
- `baseline-tests.log`: **23 context-pack + 2 hook-pack** baseline tests passed через штатный Modules runner. Это не полный workspace gate.
- `verified-binaries-build.log`: model-pack и hook-pack components дополнительно пересобраны из чистого checkout Modules текущего HEAD; весь repro повторён после сборки. Cargo использует штатный Core contracts/SDK pin `b5fac84245b075896c24763b3aebac79b4375c2e`, без подмены dependencies.
- Core binary и workflow/context components взяты из ранее проверенной сборки текущих HEAD. Их hashes совпадают с предыдущим аудиторским evidence; в этом проходе эти три бинарника заново не собирались. Полный список SHA256 в `provenance.json`, source HEAD/status в `source-provenance.json`.

Команды: `python3 run.py && python3 verify.py`. Файлы используют явные пути к pinned binaries и Core Python helper; при переносе нужно указать соответствующие checkout/build paths.

## Границы

Structured-only content возвращает синтетический, но обычный и валидный process tool/v6. Не утверждается, что каждый штатный инструмент уже возвращает этот формат, либо что текущий MCP-конвертер формирует его таким же образом. Для воспроизведения не нужны повреждённый protocol payload, чужой код или обход policy.

Hook opt-in: дефект Text/Json касается штатного Core cap и с hook, и без него; невыполнение меньшего cap для error относится к включённому `hook.output_budget`. Активный summarizing compactor намеренно не подключён, чтобы отдельно проверить гарантию per-tool budget. Native GUI и live LLM не проверялись. Никакие пользовательские репозитории, сессии и секреты не использовались.

Дополнительно прочитаны context byte admission, root-to-cwd project-doc budgets, UTF-8 bounded reading, provider retrieval и workflow token accounting. Новой независимой второй проблемы из этих чтений не заявляется.
