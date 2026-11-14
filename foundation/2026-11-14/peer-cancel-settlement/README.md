# Core: общий bounded cancel-and-settle для process peer

Source patch для [Proteus-core](https://github.com/Proteus-harness/Proteus-core) на точной базе **`89997df995df7c39b713e16aba216ecb19c8f497`**. Проверенный локальный commit: `1e96d9bf0e649ed9c1983436532b256df74a559d`. Его SHA является идентичностью локальной проверки, а не опубликованным upstream commit.

**Upstream не изменён.** Этот каталог передаёт текстовый патч, а не устанавливает его или выпускает новую сборку. Нет raw logs, приватных configs, бинарников и архивов. Исходники сохраняют [MIT-лицензию Core](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/LICENSE).

## Исправление и упрощение

Role timeout ранее обрывал внешний `timeout_at` и сразу убивал прямой peer, обходя адресную отмену активного turn. Новая boundary-регрессия на исходной базе падала: cooperative Cancel не доходил, peer становился non-resumable.

Теперь `run_leased_turn` владеет cleanup активного peer. Driver сообщает interruption; timeout и user cancel используют общий `finish_interrupted`: адресный `Cancel`, затем ожидание response исходного `Send`. ACK самого Cancel не заменяет terminal response. Весь settlement, включая запись, чтение и пересылку событий, ограничен `cancel_grace_ms`.

Cancel target публикуется лишь после полной initial Send-записи, временно снимается перед continuation. Outstanding message receipts и persistent `write_in_flight` bit переживают drop driver future: ambiguous delivery и возможная partial JSONL запись не разрешают небезопасное переиспользование peer. Setup/protocol/write errors инвалидируют соединение. Причины `TimedOut`/`Cancelled`, partial text и независимость соседних peers сохранены.

Production diff в трёх файлах: **+101/−136, net −35 строк**. Удалены `cancel_sent`, нечитавшийся published-id Mutex, промежуточный `finish_cancelled`, повторные cleanup-вызовы четырёх веток и отдельный timeout только чтения. Нет нового framework, dependency, DTO, config field или изменения wire protocol. Это локальное уменьшение числа независимых правил, не доказательство ускорения.

## Подтверждённые проверки

- Штатный scoped runner на final production: **35 уникальных tests passed**, process_agent_control 12 + process_agent_pool 23. Последняя test-only доработка marker зависшего EventSink проверена отдельным повтором затронутого теста, production после scoped suite не менялся.
- Проверены approval/user-input deadline, точный target, partial text, same-PID resume после cooperative timeout, ACK без terminal, игнорирование Cancel, stalled settlement EventSink и blocked delivery write. Существующие startup/initial write, targeting siblings, mailbox, rotation, depth и history tests сохранены.
- На финальном native binary проверены **4 реальных случая**: custom role timeout, component timeout control, штатный shell `exec_command` role timeout и user-cancel control. Ожидаемые статусы сохранены; через 4.5 секунды после ответа helper отсутствует и поздний marker не создан. Это наблюдение именно этих сценариев, не гарантия для любого module.
- Child journal фиксирует `TurnSettled=canceled`, parent сохраняет `timed_out`/`cancelled`. Три cold `/history` успешны, hashes journals до/после не изменились. Подробный transcript rendering и workflow replay этим не проверены.
- `cargo fmt --all --check`, `git diff --check` прошли. Патч применён в отдельном Git index к точной базе; результирующее дерево совпало с проверенным локальным commit.
- Независимое read-only review проверило final sources, hashes и логи, блокеров не нашло; повторно tests не запускало.

Native binary SHA-256: `42b2178cc27224151c3c71b8136ab454e5e2173735330f96890899888960bcaa`. Использованы ранее проверенные reference/shell module binaries, не новая Modules сборка. CI delivery-репозитория не подменяет эти локальные проверки.

## Обязательные ограничения

1. **Fallback не гарантирует принудительную остановку всех OS-потомков.** При partial write, pending delivery, игнорировании Cancel или grace expiry по-прежнему убивается прямой peer. Components/terminal commands могут иметь свои process groups; проблема полного OS ownership здесь не решена.
2. **Timeout + grace:** role deadline допускает дополнительный cleanup budget `cancel_grace_ms`. Строгое завершение всей системы в момент role deadline не обещается.
3. Синтетический stop-reading test доказывает non-resumable outcome, но **сам по себе не отличает запрет дописывания Cancel к partial frame от последующего kill**. Guard дополнительно проверен исходниками; более сильная black-box гарантия не заявляется.
4. Full workspace, portable/release, Windows, GUI и live LLM не проверялись. Latency/RSS/throughput не измерялись.
5. Финальный event sink вне settlement, например `SubagentFinished`, сохраняет прежнее поведение. Глобальной latency-гарантии для произвольно зависшего sink нет.

## Как применить

Используйте отдельную чистую копию **Core**, не этот delivery-репозиторий. Проверьте `sha256sum -c SHA256SUMS` в каталоге пакета. `PATCH_FILE` ниже должен указывать абсолютный путь к `0001-peer-cancel-settlement.patch`.

```bash
test "$(git rev-parse HEAD)" = 89997df995df7c39b713e16aba216ecb19c8f497
git status --short  # убедитесь, что рабочая копия чистая
git switch -c review/peer-cancel-settlement
git apply --check "$PATCH_FILE"
git am "$PATCH_FILE"
python3 scripts/test.py -p proteus-core --offline --test process_agent_control --test process_agent_pool -- --nocapture
cargo fmt --all --check
```

Offline-прогон требует подготовленных зависимостей и fixtures по инструкциям upstream. При другой базе, конфликте или уже перенесённом исправлении остановитесь и пересмотрите применимость, не применяйте силой. Scoped tests не заменяют обязательные upstream review/CI. Сочетание с другими патчами требует отдельной проверки; здесь проверено применение к указанной чистой базе.
