# PR86–89: применимость после обновления upstream

Дата проверки: 2026-11-14. **Docs-only, source-only; не подтверждение runtime-совместимости.**

## Зафиксированные версии

- Core: `89997df995df7c39b713e16aba216ecb19c8f497` → `bcbda4435534a296c707a1daa250813d692f68e1`. [Сравнение](https://github.com/Proteus-harness/Proteus-core/compare/89997df995df7c39b713e16aba216ecb19c8f497...bcbda4435534a296c707a1daa250813d692f68e1).
- Modules: `3270dc0f894eaf4d0360306052b806099b8f5351` → `c035142558f0fca43e9772fc0e50ca293abf1531`. [Сравнение](https://github.com/Proteus-harness/Proteus-modules/compare/3270dc0f894eaf4d0360306052b806099b8f5351...c035142558f0fca43e9772fc0e50ca293abf1531).
- Проверены опубликованные patch-файлы delivery-репозитория на `2730fcf49b69a7d86151e4e84e88beabc16a83dc`.

**Итог:** изменения PR86–89 не перенесены в проверенный upstream. Все 78 текстовых hunks имеют точное совпадение исходного контекста в соответствующей последовательности. Это позволяет продолжать интеграцию, но не объявлять патчи проверенными на новых версиях. Merge PR в этом репозитории означает доставку материалов, не интеграцию в Proteus-core/Proteus-modules.

## Матрица

| Материал | Файлы / hunks | Результат статической проверки |
| --- | --- | --- |
| [PR86](https://github.com/Qweasd123tg/proteus-modules-dot/pull/86), [Core config](../reviewed-simplification/core-config-validation.patch) | 7 / 10 | Все hunks совпали. Общая семантическая валидация и её подключение к Save по-прежнему требуют переноса. |
| PR86, [Modules history/compaction](../reviewed-simplification/modules-history-compaction.patch) | 9 / 11 | Все hunks совпали. Общая нормализация восстановленной истории и удаление request-scoped tool results при compaction не внесены. |
| [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87), [cancel settlement](../peer-cancel-settlement/0001-peer-cancel-settlement.patch) | 7 / 29 | Все hunks совпали; единое bounded settlement и учёт незавершённой записи отсутствуют upstream. |
| [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88), [question identity](../user-input-queue-identity/0001-user-input-queue-identity.patch) | 4 / 8 | Все hunks совпали после PR87. App-server всё ещё принимает caller request ID. Изменившаяся runtime-and-events.md не конфликтует с двумя hunks патча. |
| [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89), [descendant origin](../descendant-origin/0001-descendant-origin.patch) | 6 / 20 | Все hunks совпали **после PR87 → PR88**. Самостоятельная применимость к чистому upstream не заявляется. |

Счётчики файлов относятся к каждому patch отдельно и не складываются в число уникальных файлов.

## Что именно проверено

Два независимых чтения exact-SHA файлов и текстовых patch-файлов дали одинаковые счётчики: 10 + 11 + 29 + 8 + 20 = 78. Для каждого hunk проверены объявленные количества строк и ровно одно точное совпадение всех context/deleted строк; замена выполнена только в памяти. Последующие hunks и patches проверялись на полученном тексте. Новые пути проверены как отсутствующие upstream.

Это **не `git apply --check`**, не `git am`, не компиляция и не выполнение тестов. Проверка не устанавливает семантическую корректность и не заменяет Git-проверку index/modes. Код проекта, Python fixtures и runtime не запускались.

Единственное upstream-изменение пути из пакета по сравнению с прежними базами: `docs/guides/runtime-and-events.md` (текущий blob `9bebaa1dec95d0d2c758a7ad502eaaadedb882e0`). Добавления о reasoning находятся вне контекста hunks PR88. Существующие production-файлы пакета сохраняют прежние blobs.

## Обязательные поправки к инструкции переноса

1. **Не откатывать dependency pin.** В [Modules Cargo.toml](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/Cargo.toml) Core, contracts, SDK, protocol и process-host закреплены на `41bdfffa6e70228278b4abc758b7f81a12672f35`. Сохранить этот новый штатный pin вместо старого `b5fac84245b075896c24763b3aebac79b4375c2e` из прежних материалов. Core HEAD и Modules dependency pin различаются; совместимость всей комбинации надо проверять явно.
2. **Новые reasoning events не покрыты обещанием PR89.** [should_forward_child_event](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/agent_control/process/turn.rs) пропускает tool, approval, subagent и error events, но не новые [AssistantReasoningTextDelta / AssistantReasoningMessageCompleted](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/domain/events.rs). PR89 сохраняет этот whitelist: это существующее ограничение фильтра, не новая регрессия патча. Сохранение origin не равно доставке всех variants через дерево peers.
3. **Старый GREEN не переносится на новые SHA.** Результаты прежних scoped tests остаются историческими. Новые transcript/projection изменения особенно требуют свежей проверки; старые projection tests её не заменяют.
4. Background routing, потребители с ключом только call ID и teardown descendants остаются отдельными незакрытыми областями. Этот документ не расширяет scope PR86–89 и не объявляет их исправленными.

## Следующие gates перед runtime-интеграцией

- Git-проверка и применение на exact-SHA исходниках с цепочкой Core PR87 → PR88 → PR89; PR86 проверять отдельно и затем в общей комбинации.
- Сборка и scoped tests с новым штатным Modules pin; отдельно обозначить, если проверяется patched Core вместо pinned dependency.
- Config: Save/watch/HTTP, неизвестные module_config slots, согласованность загрузки и сохранения.
- Cancellation: частично записанный frame, неоднозначная доставка сообщения, timeout, повторный cancel и settlement.
- Identity: коллизии request IDs, несколько peers и повторные вопросы.
- Origin: вложенные peers, cancel, cold-history/transcript/projection.
- Recovery/compaction/resume: readable reasoning и opaque pi/thinking, согласованность tool call/result.
- Затем требуемые CI и целевые интеграционные сценарии; не суммировать перекрывающиеся старые тесты как новое покрытие.

**Выигрыш этой ревалидации:** не требуется заранее переписывать 78 hunks из-за текстового drift; сохранена возможность продолжить перенос. Экономия времени не измерена, гарантия runtime-корректности и ускорение агента не заявляются.
