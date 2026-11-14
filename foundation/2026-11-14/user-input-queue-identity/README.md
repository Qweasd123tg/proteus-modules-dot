# Собственная identity очереди user-input

Source patch для [Proteus Core](https://github.com/Proteus-harness/Proteus-core), а не изменение runtime этого delivery-репозитория. **Upstream не изменён.** Лицензия исходного проекта: MIT. Публикуются только patch и описание, без сырых логов, конфигураций и бинарников.

## Что исправлено

App-server назначает каждой pending user-input записи собственный непрозрачный UUID вместо caller-local tool ID. Два независимых peer с `call_0` больше не заменяют responder друг друга; запоздалый ответ/timeout старой записи не разрешает новую запись с тем же локальным ID. Ответ связан с конкретным invocation через существующий oneshot и process bridge. Новый registry, mapping table, DTO, dependency или framework не добавлены.

Questions, title, origin, seq, policy, timeout и cancellation сохраняются. Клиент обязан возвращать ID, полученный в `UserInputRequested`, а не вычислять его из tool call ID. Bridge сохраняет исходный child ID и возвращает ответ по нему. IDs tool calls и canonical journals не переписываются. Проверены исходники opaque-ID consumers CLI/ACP/HTTP/Desktop, но Desktop UI не запускался.

## Точная база и порядок применения

- Исходный upstream Core: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Обязательный предшествующий пакет: [cancel-and-settle](../peer-cancel-settlement/README.md), опубликованный в [PR #87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87), **не применённый upstream**.
- Непосредственная проверенная база identity patch: локальный cancel commit `1e96d9bf0e649ed9c1983436532b256df74a559d`.
- Итоговый локальный commit: `7bd840ad7f85c86e9b4fc1158593b5f4af6ece33`.
- Проверенное итоговое дерево: `efb3108e7c93cc8a510ae9805a56d469fa5c463a`.

В чистой отдельной рабочей копии Core, где DELIVERY указывает на checkout этого репозитория:

```bash
git switch -c review/user-input-queue-identity 89997df995df7c39b713e16aba216ecb19c8f497
git am "$DELIVERY/foundation/2026-11-14/peer-cancel-settlement/0001-peer-cancel-settlement.patch"
git apply --check "$DELIVERY/foundation/2026-11-14/user-input-queue-identity/0001-user-input-queue-identity.patch"
git am "$DELIVERY/foundation/2026-11-14/user-input-queue-identity/0001-user-input-queue-identity.patch"
git rev-parse HEAD^{tree}
```

Git am может создать другие SHA commits из-за metadata committer; сравнивайте tree. При уже применённом cancel patch не применяйте его второй раз. Композиция с другими пакетами и более свежим upstream здесь не проверялась. SHA256SUMS проверяет неизменность доставленного patch. Mail-format whitespace сохранён побайтно.

## Проверки и наблюдаемый результат

- **16 user-input tests passed**: три новые регрессии, существующие cancellation/shutdown/resolve, parsing и HTTP response/loop. Дополнительно собранный pool target с нулём выбранных tests не засчитывался.
- **35 process tests passed**: control 12 + pool 23. После этого менялись только комментарий и assertion теста; 16 affected tests повторены на финальном исходнике. Эти 35 перекрываются с проверками cancel пакета, их нельзя считать 35 новыми тестами.
- Baseline: три новые queue-регрессии падают; реальный root stdio + два peer публикуют одинаковый `call_0`. Baseline останавливается на collision, это не заявление о фактически отправленном чужому человеку ответе.
- Финальный процессный сценарий: peers A/B используют `call_0`, затем `call_1` в прежних durable sessions/PIDs; четыре pending IDs различны. Ответы в обратном порядке доходят каждый своему child; запоздалый generation-one ответ отклоняется при pending generation two. Локальные call IDs сохранены, summaries успешны.
- Три canonical journals содержат пять successful TurnSettled и правильные ответы. Три cold stdio `ExecuteCommand /history` успешны, hashes журналов неизменны; это не workflow replay и не подробный HTTP transcript.
- `cargo fmt --all --check` и source `git diff --check` прошли. Независимый read-only reviewer не нашёл блокирующего дефекта; сам tests не перезапускал.
- При публикации patch повторно применён к точной базе в отдельном Git index; resulting tree совпал с локальным commit. Runtime tests при упаковке повторно не запускались.

Команды scoped tests из Core checkout с настроенным toolchain и `PROTEUS_TEST_REFERENCE_MODULE`, указывающим на совместимый собранный reference module:

```bash
python3 scripts/test.py -p proteus-core --offline --lib --test process_agent_pool user_input -- --nocapture
python3 scripts/test.py -p proteus-core --offline --test process_agent_control --test process_agent_pool -- --nocapture
```

Процессные fixture/scripts и raw evidence остаются локальными и не включены в этот source-only пакет; их сценарии здесь описаны, но готовый standalone runner не доставляется.

## Что НЕ закрыто

- Origin вложенных descendants всё ещё flatten-ится; background/idle dispatch gap остаётся.
- Core/Desktop reducer/live tool projection всё ещё местами сопоставляет только call ID. Корректная доставка ответа не доказывает корректную tool-card attribution.
- Worktree naming на основе role + local call ID может столкнуться между sessions; worktree ownership здесь не менялся.
- Completion eviction, background ownership, queue caps и старые sleeping timeout tasks не исправлены.
- Tool IDs в canonical journal session-local, не turn-local: reuse в другой turn одной session остаётся ошибкой. Финальный fixture использует session-wide counters, а не ошибочный same-session reuse.
- UUID collision resistance не является математическим доказательством уникальности или новой security guarantee.
- Full workspace, module_swap, Desktop native UI/build, live providers, release/portable, Windows, workflow replay и performance не проверялись. Ускорение/RAM-выигрыш не заявлены.
- Ограничения предшествующего cancel пакета сохраняются: timeout + grace и отсутствие гарантии остановки всех OS-потомков при fallback.
