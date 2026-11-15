# Независимый exact review: root tool-result projection

## Verdict

Source-level blocker не найден. Известная потеря tail при active reconnect устраняется в owner нужной projection: полный root result и bounded nested child preview различаются по структуре transcript, не по background compact flag. Это осознанное увеличение retained root text, не memory optimization и не гарантия bounded aggregate memory. Source acceptance не означает tests/runtime PASS.

## Production invariant

Прочитан exact diff и свежие status/snapshot/canonical transcript paths. Единственная поведенческая перемена: direct message.tool теперь сохраняет переданный result целиком; nested subagent.tools передаёт в update_tool UTF-8 prefix до прежних 10_000 bytes. Common updater копирует выбранный slice без дополнительного cap. None result/status-only updates не очищают прежний text; status, metadata и terminal extraction не меняются.

Branch-local slicing правильно сохраняет foreground child limit при compact=false и background child limit при compact=true. compact по-прежнему выбирает только JSON retention. Child slice копируется через to_owned, не удерживая allocation полного result внутри карточки. Общий временный text_or_status allocation до выбора ветки существовал прежде и не устранён.

Cold canonical append_transcript_tool_result уже сохраняет полный text_or_status с прежними error/output/content/status priorities. Новый root live projection следует тому же text contract. Это выравнивание выбранного текстового result, не утверждение полного равенства всех transcript fields при любых histories или missing-call events.

## Cost contract

Root result String теперь может существенно превышать 10 KiB. TurnProgress владеет им до reset/settlement; snapshot clone создаёт отдельную копию. Количество root rows и размер structured fallback не получают нового общего byte budget. Core output/error cap не доказывает универсальный 200 KiB предел text_or_status: Text/Json content fallback может быть больше. Дополнительный retained объём и transient snapshot copies следует считать реальной ценой correctness, а не «данные и так уже были в памяти».

Прочитанная memory guidance допускает явно названные исключения вроде неделимой видимой строки и требует ownership/lifetime ясности. Здесь исключение и отсутствие aggregate budget открыто документированы. С учётом выбранного full-root transcript outcome это не требует нового framework как условия узкой правки; bounded storage/retrieval view policy была бы отдельным контрактным решением. Runtime/RSS/latency не измерялись.

## Proposed tests и compile-shape

Два новых test functions прочитаны полностью. Child fixture различает foreground без spawn root card и background с running spawn_agent/task_name=scan; проверяет non-ASCII cutoff, retained allocation меньше полного текста, status и прежние JSON compaction differences. Root fixture использует RuntimeEventSink и in-process session subscriptions, шесть ToolResult representations: short/long output, error с lower-priority output, Text fallback, Json fallback, empty success. Сравнивает delivered Runtime DTO, active reconnect result/status/metadata, canonical transcript projection и settled snapshot.

Nested test module paths согласованы с existing layout: events/tests/tool_results.rs и explicit path turn_progress/tests/tool_previews.rs. super::* даёт existing harness/private types; EventSink trait импортирован parent events tests. Async fixture удерживает call/result values на нужных scopes. serde сериализация Option::Some(tool) даёт тот же tool object, поэтому comparison с expected_tool осмысленна. New helper/public DTO/dependency не добавлены. Compiler не запускался.

Эти tests **не выполнялись**. Root fixture не использует live HTTP/WebSocket, persistence reload или реальную cold storage; canonical helper плюс finish_progress — source-level proposed projection coverage. Child capacity assertion проверяет предлагаемое allocation свойство в test source, не memory benchmark. Нового end-to-end event ordering/reconnect stress proof нет.

## Evidence

Coordinator сообщил 18 exact Core blobs и text apply checks. Baseline Core bcbda4435534a296c707a1daa250813d692f68e1. Reviewer прочитал exact patch, relevant fresh source/cost docs и пересчитал:

- patch: 1d505f8937285f5990aa65baf13ee5486003696fa7ca8e2ef568e6a84187d05a
- turn_progress.rs: c1cb7f540321b150301fbc5a023b6ecba8337acbe3420875c084579426345593
- tool_previews.rs: 5e03d3141cc907023154d06dedb513ea0c28e238305e6206916ad9bb5ecbdb17
- tool_results.rs: 92ed00a9aa9be9d6a31b49295f7443a5551f8b576007671e9c2202161d7a7693

Rust/compiler/formatter/tests/runtime/SQL/Python model execution/project scripts/install не запускались. Production, refs и публикации не менялись. Соседние authority/approval механизмы не аудировались. Retention tradeoff принят только как явно обозначенный scope этого candidate, не как общий hard bound.
