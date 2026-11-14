# Независимый source review: legacy runtime instructions

## Итог

**В exact candidate не найден source-level blocker.** Минимальная production-правка в legacy request_from_state соответствует ранее опубликованному workflow-continuation P2. Это не новая finding. Source-review принятие не означает compile/test/runtime PASS; исторические результаты prior report не являются проверкой текущего патча.

## Production diff

В host.rs прежний literal `[System100]` сначала записывается в локальный Vec, затем `instructions.extend(input.runtime.instructions.iter().cloned())`, после чего передаётся в прежний helper. Других production-изменений нет. Сохраняются kind/text/priority и относительный порядок каждого runtime block, включая одинаковый текст у разных kinds. Нет сортировки, нормализации, дедупа, второго synthetic continuation reason или мутации input.

Пять legacy call sites охвачены: single_loop/main, single_loop/final, plan, execute и review. Последующий общий helper не изменён: intent Developer95, phase Developer90 и dynamic Developer80 добавляются после переданного списка при прежних условиях. Tool selection, preparation/ACK lifecycle, response persistence и output paths не меняются. Runtime blocks присутствуют в request уже до context preparation. Не заявляется, что один этот patch исправляет или измеряет все token-estimate правила.

Core reviewed_workflow напрямую прочитан на dependency pin `41bdfffa6e70228278b4abc758b7f81a12672f35` и main `bcbda4435534a296c707a1daa250813d692f68e1`: reason уже добавлен единственным Developer128 block перед workflow.run. Invocation runtime-info клонирует список. Следовательно Modules должен переносить blocks, а не заново читать reason и синтезировать второй block.

Codex pre-turn, first sampling и последующие explicit-block requests уже передают runtime instructions и не проходят изменённый legacy wrapper. Повторное добавление в shared helper было бы неверной границей; текущий candidate этого не делает. Adapter-specific приоритетное упорядочивание остаётся в adapters.

## Проверка test source

Добавлен один test module и три предложенных теста. Они не запускались.

1. **Builder exact list:** сравнивает полный список `[workflow System100] + runtime + phase Developer90` для пустого и непустого runtime; проверяет неизменность input list. Runtime содержит System, Developer, Project, UserPreference и reason128, включая одинаковый текст у Developer/Project. Это препятствует незаметной сортировке, text-only dedup и изменению kind/priority.
2. **Пять legacy paths:** fake default response — Assistant done/Stop без tools; по исходнику он завершает обычный single loop одним request, max_tool_rounds=0 выбирает final одним request, plan/execute/review дают три requests. В обоих вариантах continued=false/true runtime slice проверяется целиком и длина исключает лишний synthetic reason. Recorded preparation reasons подтверждают нужные пять phase paths.
3. **Codex nonduplication:** первая scripted response имеет end_turn(false), поэтому codex_loop проходит follow-up request; следующая default Stop response заканчивает loop. Оба request списка сравниваются с runtime instructions целиком. Pre-turn preparation не считается отдельной sampling response.

Continuation fixture соответствует scaffold: anchor указывает на исходный User; previous Assistant candidate добавлен в full input.history и continuation.history.new_messages; attempt=1; reason уже присутствует как Developer128. Fake checkpoint по умолчанию выдаёт detached revision=None, поэтому не заменяет полную историю неполным ACK messages. Fake tools пусты, intent=None, compactor по умолчанию возвращает unchanged; дополнительных phase blocks эти условия не создают. По чтению fixture не найден причины ошибочного ожидаемого числа requests или некорректного user anchor.

### Честные пределы тестов

- Это тесты Modules boundary, не end-to-end запуск Core BeforeStop и не реальная provider wire-проверка.
- Они не проверяют reviewer attempt budget, fresh/warm/cold restart, compaction-changing ACK или successful review correction.
- Intent95/dynamic80 branches не активируются. Production diff их не меняет; не следует объявлять их новым тестовым покрытием.
- Captured preparation reasons и exact instructions в preparation.request теперь проверяются: requests и preparations zip-ятся после отдельных проверок ожидаемого количества/phase списка. Сравнение ограничено instructions, поэтому позднее подавление tools в final/review не создаёт ложное несовпадение. Pinned ContextPreparationInput.request имеет тип Option<CanonicalModelRequest>; production helper передаёт Some(request.clone()), так что unwrap соответствует этому пути. Это предложенное test coverage, не выполненный PASS.
- Полные тексты legacy System/phase constants не сравниваются во всех workflow fixtures; exact runtime blocks сравниваются, helper fixture проверяет свой System/phase text. Это достаточный узкий regression intent для данной правки, не полная проверка prompt contents.

## Composition и evidence

PR106 sampling lifecycle вызывает тот же request_from_state и сам не решает потерю runtime blocks. Coordinator отдельно проверяет текстовую composition; этот reviewer не заявляет совместный build или применение обоих patches.

Modules baseline: `c035142558f0fca43e9772fc0e50ca293abf1531`. Read: exact before/after host.rs/tests.rs, новый instruction_propagation.rs, helper/callers/scaffold, FakeHost, prior report и указанные Core boundaries. Полный source catalog проверяет coordinator.

Reviewed after SHA256:

- host.rs: `79935d3beeea4d6576bf69f8eabb6fff28621b2d7d2a764df5c3bcd1a156b43c`
- tests.rs: `1cd258b990ecb30b2dfbbfc4d7d7a2ea3e2894548b2672b3f68253a258f364e4`
- tests/instruction_propagation.rs: `55715a9d51c2d8dab16b32c932225c8a217671db6658b811148bd63865149add`

Rust/compiler/toolchain, tests/fixtures, project scripts/runtime/providers не запускались. Production, refs и публикации не изменялись.

## Последний точный candidate

Повторно прочитаны добавленный zip/assert и actual-pin ContextPreparationInput contract. Source blocker не найден. Ручной перенос строк не считается rustfmt/test run. Test SHA256 выше независимо пересчитан; актуальный patch SHA256 независимо подтверждён: `aeec6b18e9e394bf48c231cda979c2d102a07d7181eb6852062fa3ace7d8c35c`. Production diff остался прежним.
