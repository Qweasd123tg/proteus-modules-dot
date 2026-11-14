# OTM-1: успешный image-tool result останавливает OpenCode workflow до следующего sampling

## Статус

**P2 source-only interoperability candidate.** Собственный `opencode_tools/read` возвращает допустимый PNG result, который обязательная projection собственного `opencode_loop` затем отвергает. Это достижимая по исходникам функциональная цепочка, а не runtime-воспроизведение. Проверены обычные successful tool/checkpoint и native continuation branches; сбой не требует compaction threshold.

Никакие project scripts, npm/Node/Rust tests, provider, HTTP, GUI, model fixtures или production runtime не запускались. Нет source patch. Публикуются только документы; production source не изменён.

## Актуальные базы

- Modules main при проверке: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core main при проверке: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules Cargo dependency pin: Core `41bdfffa6e70228278b4abc758b7f81a12672f35`. Это не Core main и не автоматически проверенная runtime-композиция.
- Native npm package: `@opencode/core@2.0.22`, source pin `527f0b931d1f9b3ebd34e106c51b31ce5db5b075`.
- После обновления main заново прочитаны три production файла, README, NOTICE, package.json и три relevant test files на указанном Modules SHA: их текст и Git blob SHA совпали с исходным проходом.

## Причинная цепочка

1. Native upstream reader распознаёт PNG/JPEG/GIF/WebP и читает media как base64: [read-filesystem.ts:136–148](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/core/src/tool/read-filesystem.ts#L136-L148). [read.ts:175–186](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/core/src/tool/plugin/read.ts#L175-L186) выдаёт текст и `data:<mime>;base64,...` file block. Это штатный producer, не злонамеренный custom module.
2. Proteus [files.mjs:104–113](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/opencode-runtime/files.mjs#L104-L113) сохраняет такой block как `ToolResult {ok:true, content:[{type:"image", mime_type, data}], ...}`.
3. [workflow.mjs:215–229](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/opencode-runtime/workflow.mjs#L215-L229) сохраняет полный result в `results`, хотя native Step получает его текстовую оболочку. [269–280](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/opencode-runtime/workflow.mjs#L269-L280) добавляет **полный** result в canonical messages и выполняет checkpoint.
4. Normal tool follow-up достижим без дополнительной гипотезы. Native event создан с `providerExecuted:false`; [upstream publisher:458–466](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/core/src/session/runner/publish-llm-event.ts#L458-L466) отмечает tool как called, [622–625](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/core/src/session/runner/publish-llm-event.ts#L622-L625) требует continuation для called non-provider tool. [Step:271–273](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/core/src/session/runner/step.ts#L271-L273) сохраняет true при toolChoice auto. Workflow выбирает auto при nonempty selection и продолжает цикл на строке 283.
5. Следующая итерация [workflow.mjs:154–166](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/opencode-runtime/workflow.mjs#L154-L166) **безусловно** вызывает `nativeContext(input,messages)` для estimate, ещё до `host.context.prepare` и нового model request.
6. [compaction.mjs:67–98](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/opencode-runtime/compaction.mjs#L67-L98) связывает result с assistant ToolCall, но каждый non-text `result.content` отвергает на строке 92: `OpenCode tool-result media needs an explicit canonical media bridge`.
7. [workflow.mjs:288–297](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/opencode-runtime/workflow.mjs#L288-L297) преобразует исключение в error workflow. Следующий sampling не происходит.

## Checkpoint и product boundary

Текущее [Core checkpoint](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/runtime/checkpoint.rs) возвращает `messages: history.clone()`. [HistoryCapture](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/session_journal/history_capture.rs) сохраняет proposed messages и exact committed tool payload, а не стирает media. [ToolContent contract](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/domain/tool.rs) поддерживает Image.

[Именованный opencode profile](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/configs/opencode.config.toml) соединяет opencode_loop, opencode_tools и read. Это source reachability поставляемой конфигурации, **не заявление, что профиль установлен/активен у пользователя или default всего продукта**. Runtime совместимость выбранных Core/Modules сборок здесь не проверялась.

## Что относится и не относится к выводу

- Основной witness: маленький валидный PNG, successful read, корректная matched ToolCall/ToolResult pair, successful checkpoint, обычное continuation. Нет cancellation, failed read/checkpoint, malformed content или переполненного контекста.
- Text-only result (`content:[]` либо text blocks) проходит выделенную projection branch. Это source negative control, не выполненный тест.
- Отключение compactor либо `auto:false` не устраняет вызов nativeContext в самом workflow; этот вызов стоит до hook.
- Прямой standalone read без последующего workflow не доказывает failure.
- Не утверждается утрата canonical image, повреждение journal, повтор tool effect, cold-resume poisoning, ошибка GUI, provider rejection или измеренная частота инцидента.
- Другие non-text content также отвергаются guard, но основной finding ограничен PNG: PDF/provider binary semantics отдельно не проверены.
- User-image attachment path не исследован этим finding; не объединять его с tool-result media.

## Направление исправления и упрощения

Один общий canonical-to-native media bridge должен сохранять supported media одновременно для workflow estimate и compaction; сейчас общий helper уже есть, но его domain уже, чем output собственного tools export. Не создавать второй text-only estimator и не удалять media молча, иначе остановка превратится в потерю данных для модели. Нужны exact upstream durable media shapes и проверка обратной compaction projection.

Это не просьба менять permissions/sandbox/tool admission. Нет обещания LOC, RSS или latency выигрыша.

Минимальный будущий executable gate: расширить существующий `tests/workflow.test.mjs` случаем tool-call → successful PNG result → второй sampling, сохранить exact image payload и call identity. Контроли: text-only result; compactor absent/auto:false; unmatched/failed read отдельно. Затем focused native files producer → workflow bridge check. Tests здесь **не написаны и не запускались**.

## Дедупликация и review

- Прочитан published главный индекс PR85; metadata/body PR85–101 и последние PR проверены, новых PR после101 не было на момент проверки.
- Targeted текстовый scan 94 top-level published `REPORT.md/README.md/report.txt/findings.md` файлов в continuous-audit evidence по `opencode`, `nativeContext`, `tool-result media`, `canonical media bridge`; совпали только benchmark mentions. Дополнительно просмотрены media/image/compaction hits и полностью прочитан `round3-models/REPORT.md`.
- Старый A1 в round3-models — silent loss в OpenAI/Anthropic provider serializer. Здесь workflow error **до** provider request, другой owner и исправляемая граница. Исправление serializer A1 само по себе OTM-1 не устраняет.
- PR86 model-history/compaction patch относится к другому Rust workflow/hook; PR91–101 описывают другие source chains.
- По GitHub path history compaction.mjs введён commit `f3c70133e84f11dc632c7b9ec8e489456bfa3ff9` от 11 ноября, после даты полного аудита7 ноября. Полный DOCX PR84 повторно не читался; абсолютная новизна во всех приватных/WIP материалах не заявляется.
- Независимый source review подтвердил цепочку; отдельно перечитаны Modules production/test/doc files, pinned upstream reader/Step/publisher и Core checkpoint contract. Повторно прочитаны три ключевых файла на **свежем** Modules SHA. Source-chain blocker не найден, P2 source-only candidate принят.

