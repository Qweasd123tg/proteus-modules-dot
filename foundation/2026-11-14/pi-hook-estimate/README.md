# PCE-1: Pi compaction использует оценку предыдущего состояния истории

## Статус и значение

**P3 source-only composition candidate.** После изменяющего `BeforeContext` hook следующий `pi_compact` берёт актуальные сообщения из `event.output.messages`, но порог compaction проверяет по старому `event.input.token_estimate`. Из-за смешения двух состояний можно пропустить compaction либо вызвать лишнюю модельную суммаризацию.

Основной доказанный исходниками witness: предыдущий custom hook уже уменьшил историю ниже порога, однако оставил достаточно материала для следующего summary. Pi вызывает summary по прежней высокой оценке. Это не установленный инцидент в штатном/default профиле. Фактический overflow, потеря canonical history, задержка, стоимость API и runtime reproduction не заявлены.

**Project code, validator, fixtures, tests, providers и runtime не запускались. Зависимости не устанавливались; production patch отсутствует.**

## Закреплённые источники

- Modules `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules Core dependency pin `41bdfffa6e70228278b4abc758b7f81a12672f35`. Independent review повторно прочитал `context_preparation.rs`, `compaction_validation.rs` и `execution_hooks.rs` на обеих ревизиях; текст совпал.
- Pi npm dependency `@earendil-works/pi-coding-agent@1.5.2`; для чтения upstream использован официальный release commit `b4afdddf44e059c67ccf5097e5317d913521b470`. Установленные npm bytes и runtime composition не проверялись.
- Точные Git blob identities перечислены в [SOURCES.json](SOURCES.json).

## Причинная цепочка

1. Pi hook экспортирован с [`ordered_many`](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/pi-runtime/exports.mjs#L22-L31).
2. Core [создаёт original input и отдельный output](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/context_preparation.rs#L49-L75), а [после каждого hook передаёт следующий accepted event](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/execution_hooks.rs#L76-L82). [Применение ответа](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/contracts/hook.rs#L171-L176) вызывает `compose_outputs`: меняется output, не input.
3. Pi [строки 17–23](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/pi-runtime/compaction.mjs#L17-L23) проецирует `event.output.messages`, но выбирает `event.input.token_estimate ?? estimateContextTokens(pi).tokens`. При ненулевой исходной оценке новый output estimate и пересчёт не используются.
4. Upstream [`shouldCompact`](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/core/compaction/compaction.ts#L264-L270) сравнивает переданное число с `contextWindow - reserveTokens`; default reserve равен 16 384, retained budget равен 20 000.
5. [`prepareCompaction`](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/core/compaction/compaction.ts#L859-L919) затем ищет границу и материал для summary. Он не повторяет проверку window threshold. Поэтому небольшая по сравнению с окном, но всё ещё длиннее retained budget история может породить настоящее summary request из [Pi adapter](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/pi-runtime/compaction.mjs#L40-L81).
6. Сравнение со штатными соседями: [Codex hook](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/hook/codex-context-preparation/src/lib.rs#L29-L37) и [OpenCode hook](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/opencode-runtime/compaction.mjs#L207-L209) уже заменяют исходную оценку на output estimate после `output.changed`.

## Валидный source-derived witness

Выбирается существующая Pi catalog модель `gpt-6.1-sol`. [Release catalog source](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/ai/catalog/providers/openai-codex.ts#L15-L18) задаёт окно 500 000, следовательно проверяемый порог Pi равен 483 616.

1. Original preparation содержит старый длинный prefix и три неизменённых user messages по 40 000 ASCII-символов. Исходная оценка равна 510 000.
2. Первый custom hook удаляет только старый prefix, сохраняет эти три сообщения с их идентичностями, возвращает `changed=true`, `token_estimate=30000`. Current user остаётся последним. Нет in-place изменения payload, дублирования IDs или tool calls.
3. [Core validation](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/contracts/compaction_validation.rs#L29-L105) допускает такое сокращение. В event следующего hook original input estimate остаётся 510 000, а output имеет три сохранённых user messages и оценку 30 000.
4. Pi принимает неправильное решение `510000 > 483616`. Native cut по 20 000 сохраняет последние два сообщения и получает первое для summary. Значит guard `if (!plan) return unchanged` этот witness не устраняет.
5. При правильной оценке `30000 > 483616` ложно: Pi должен вернуть Continue без summary callback.

Это анализ ветвей исходников, не выполненный тест и не измерение токенизации провайдера. Предыдущий hook custom; штатный расширяющий/сжимающий chain с данным естественным исходом не установлен.

Обратный разрешённый контрактом случай: original low estimate, предыдущий hook добавляет fresh compactor-owned text, возвращает high output estimate и сохраняет current user. Pi преждевременно возвращает Continue по старой низкой оценке. Этот случай доказывает неверный threshold gate, **не фактический отказ провайдера или overflow**.

## Контроли и важные ограничения

- При отсутствии предыдущего `changed` output исходная оценка относится к актуальному кандидату.
- Если original estimate null, текущая ветка уже пересчитывает текущие Pi messages; конкретная stale-non-null причина отсутствует.
- Если changed output estimate null, исправление должно пересчитать новый кандидат, а не использовать старое input значение.
- Если после сокращения нет суммируемого prefix, `prepareCompaction` возвращает undefined. Нельзя утверждать, что любой stale high estimate создаёт модельный запрос.
- Witness исключает отсутствующий request, неизвестную модель, malformed identity и terminal compaction entry.
- Core не теряет предыдущий output при Continue; проблема в решении Pi о необходимости собственной обработки.
- Вне области: tool-output budgets, BeforeModel instruction telemetry, OTM-1 media bridge, persisted compaction-report cardinality, permissions и security.

## Исправление и упрощение

Достаточно локального выбора источника оценки, как в соседних adapters:

```js
const estimate = event.output.changed
    ? event.output.token_estimate
    : event.input.token_estimate;
const tokens = estimate ?? estimateContextTokens(pi).tokens;
```

Это направление, **не внесённый и не проверенный source patch**. Конструкция `output.token_estimate ?? input.token_estimate` неправильна после changed/null, поскольку возвращает устаревшую оценку. Новый framework, registry или cross-language abstraction здесь не нужны. Измеренный LOC/RSS/latency выигрыш не заявлен.

Будущие focused regression cases: high→low с непустым summary prefix; low→high; changed/null; unchanged; короткий no-plan control. Проверять число summary callbacks и принятую историю, не timing и не расположение строк исходников.

## Дедупликация и независимый review

- Прочитаны metadata/body PR85–104 и главный индекс PR85. Targeted scan 94 top-level published reports на delivery commit `19b263ef10f8d83c394b5e98ee4b7462d8b4023d` по Pi compaction path/name и stale/preceding estimate не дал совпадающей причины.
- Отдельно сопоставлены причины в `context-budget`, `hook-usage`, `hooks-replay`, `workflow-steering`, `workflow-continuation`, `round3-models`. PR95 DS-7 относится к cardinality persisted reports; PR102 OTM-1 относится к media bridge перед sampling. Это другие границы.
- Полный старый PR84 DOCX и все вложенные raw/test artifacts повторно не читались. Абсолютная новизна во всех приватных/WIP материалах не заявляется.
- Независимый source review подтвердил source chain, валидность custom-hook witness и no-plan caveat; финальный review повторно проверил числовой пример и scope. Reviewer ничего не исполнял.

## Остальной проход workflow

Прочитаны fresh Pi loop/projection/compaction, OpenCode workflow/compaction и Rust single/codex/plan-execute-review loop builders. Известные cancellation recovery, runtime instructions, private-draft steering и PNG continuation не пересчитаны как новые findings. Нового существенного дефекта default workflow или оправданного крупного общего рефакторинга этим проходом не установлено.
