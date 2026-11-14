# Сохранение origin вложенных агентов

Source patch для [Proteus Core](https://github.com/Proteus-harness/Proteus-core), лицензия исходного проекта MIT. **Upstream не изменён.** Этот delivery-пакет содержит patch, описание и checksum, без сырых логов, конфигураций и бинарников.

## Изменение

ChildProcess хранит physical root ThreadId вместе с durable AppSubagentSession. Пара сохраняется при resume и заменяется целиком при NewSession. Forwarder переводит только physical root в logical child alias; thread потомка, исходный turn и execution интерактивного запроса сохраняются. Label прямого ребёнка становится его role, label потомка не затирается. Execution-only origin остаётся без chat identity; отсутствующий origin получает прежний direct-child fallback.

Одна и та же проекция применяется при обычном forwarding и cancel settlement. Существующие event filters и typed response bridge не изменены. Нет нового bus, registry, descendant map, dependency, DTO/wire/config field или запрета nesting. Два production файла: +67/−38, net +29 строк. Дополнительное состояние: один ThreadId на peer, не на каждого потомка/событие.

Это logical provenance, а не аутентификация identity недоверенного peer. Принимающая session по-прежнему владеет envelope/session_id/event_id/seq/timestamp; raw source envelope полностью не сохраняется.

## Зависимости и применение

Проверенная цепочка:

1. Upstream Core `89997df995df7c39b713e16aba216ecb19c8f497`.
2. [Cancel-and-settle / PR87](../peer-cancel-settlement/README.md): локальный commit `1e96d9bf0e649ed9c1983436532b256df74a559d`.
3. [User-input queue identity / PR88](../user-input-queue-identity/README.md): **непосредственная база** `7bd840ad7f85c86e9b4fc1158593b5f4af6ece33`.
4. Этот patch: локальный commit `03c91e807370a47233ea7e9783c39429a82013cf`, tree `00a3c04a70d7927d1688ea155142025f596a2874`.

Все три пакета доставлены отдельно, не внесены в upstream. В чистом отдельном Core checkout, DELIVERY указывает на checkout этого репозитория:

```bash
git switch -c review/descendant-origin 89997df995df7c39b713e16aba216ecb19c8f497
git am "$DELIVERY/foundation/2026-11-14/peer-cancel-settlement/0001-peer-cancel-settlement.patch"
git am "$DELIVERY/foundation/2026-11-14/user-input-queue-identity/0001-user-input-queue-identity.patch"
git apply --check "$DELIVERY/foundation/2026-11-14/descendant-origin/0001-descendant-origin.patch"
git am "$DELIVERY/foundation/2026-11-14/descendant-origin/0001-descendant-origin.patch"
git rev-parse HEAD^{tree}
```

Не применяйте предшественников повторно, если они уже присутствуют. SHA commits после git am может отличаться из-за metadata committer; сравнивайте tree. Композиция с другими пакетами или свежим upstream здесь не проверена. SHA256SUMS фиксирует побайтный оригинал mail patch, включая его форматный whitespace.

## Проверки

**63 unique scoped Rust tests passed** по локальному evidence:

- Process control 14 + process pool 23 = 37, включая две новые boundary-регрессии, timeout/cancel, pending interactions, session rotation/resume, sibling/config isolation.
- Existing app_server::turn_progress: 13.
- Existing core::approval::cache: 13, включая per-thread и detached-execution separation.

После полного process suite только test fixture расширен проверками четырёх origin forms (root, descendant, execution-only, None) для user-input и approval на initial/resumed/rotated sessions. Два affected tests повторены успешно; production после suite не менялся. Повторные и zero-selected tests не прибавлены к 63; многие scopes перекрывают предыдущие пакеты.

На неизменённой базе две новые boundary-регрессии падают. Реальный model-free root → parent → leaf baseline ошибочно атрибутирует leaf tool родителю. На исправленной версии три настоящих Core процесса с shipped collaboration/request_user_input tools передают leaf thread по logical leaf ID из SubagentStarted; source turn/execution совпадают с leaf canonical TurnOpened. Typed answer доходит leaf, все три journals успешно settled. Три cold stdio ExecuteCommand `/history` показывают по два сообщения, hashes журналов неизменны. Это не detailed HTTP transcript или workflow replay.

Самостоятельный read-only review не обнаружил блокирующего production дефекта, проверил boundaries/consumers/evidence; reviewer не перезапускал tests. Его замечание об optional-origin coverage учтено расширением fixture.

`cargo fmt --all --check` и source `git diff --check` прошли. При упаковке повторно применён patch к точной базе в отдельном Git index: tree совпал с локальным commit. Runtime tests при публикации повторно не запускались.

Из Core checkout с настроенным toolchain и PROTEUS_TEST_REFERENCE_MODULE на совместимый собранный reference module:

```bash
python3 scripts/test.py -p proteus-core --offline --test process_agent_control --test process_agent_pool -- --nocapture
python3 scripts/test.py -p proteus-core --offline --lib --test process_agent_pool app_server::turn_progress -- --nocapture
python3 scripts/test.py -p proteus-core --offline --lib --test process_agent_pool core::approval::cache -- --nocapture
```

Rust boundary tests и synthetic peer fixture включены в patch. Отдельный end-to-end nested runner и raw evidence в пакет не входят.

## Оставшиеся gaps

- **Background routing НЕ исправлен.** Background leaf question после завершения foreground parent не доставляется и после resume: это воспроизведено и на baseline, и на patched версии. У idle peer нет постоянного forwarding owner; origin translation этого не решает. Успешное воспроизведение gap не означает успешную доставку.
- **Call-ID-only projection Core/Desktop НЕ исправлена.** ToolCallResolved/Finished, approval/terminal cards могут неверно сопоставляться при одинаковых IDs разных sessions. Правильный origin не чинит consumers автоматически.
- Не добавлены pending snapshots, idle output draining, descendant teardown, worktree lifetime/naming, unread completion retention или durable tree recovery.
- Existing event filter сохранён, в том числе terminal-binding limitation; не обещается forwarding всех event variants.
- Full workspace/module_swap, Desktop build/native UI, live providers, release/portable, Windows и workflow replay не запускались.
- Нет latency/RSS/throughput benchmarks или обещания ускорения. Ограничения предыдущих пакетов, включая timeout + grace и отсутствие гарантии остановки всех OS-потомков при fallback, сохраняются.
