# Убирать работу там, где вход не изменился

Шесть source-only патчей к четырём upstream-репозиториям. Продолжение [схем/ownership](../repeated-work/) и [истории/UI](../history-and-ui/); прежние патчи здесь не дублируются.

## Патчи

1. **Core: `core/01-inserted-part-validation.patch`.** После capture результата заново проверяется стабильность только вставленного message, а не хешируются все старые payloads. Полная проверка уникальности active IDs остаётся первой; новый part сверяется со всем known_parts, включая trace-only identity. `record_at` возвращает точный индекс, прежний `record -> bool` сохранён. COW isolation, порядок bindings, settlement/effect recovery и errors не меняются. Это не устранение полного journal replay; O(history IDs) проверка и возможная COW-копия остаются.
2. **Core: `core/02-token-cancellation-waits.patch`.** Workflow/tool/context/context-provider ждут существующий CancellationToken вместо пробуждения каждые 10 ms. HookHost без wake-источника сохраняет polling. Bool fallback возвращает управление outer select после каждого tick, в том числе при медленном predicate. Pre-encode check, admission receiver drop, cancel ACK и тот же typed terminal сохранены. Нет новой задачи, wire-протокола, authority или таймера в token path.
3. **Core: `core/03-async-cancel-ack.patch`.** После патча 02 ожидание broker ACK выполняется через oneshot/await с прежним двухсекундным пределом, вместо блокирования executor thread. Sync API и ACK point после broker cancel остаются прежними. Успешный ACK не означает terminal/rollback; потеря waiter или timeout не отзывает уже принятую команду. Потом adapter ждёт тот же terminal. Новый async API требует Tokio с включённым time driver (штатный Core уже его включает); у protocol crate явно включается production time feature.
4. **Modules: `modules/01-lazy-terminal-reconstruction.patch`.** Streamed items строятся только когда terminal output и completed fallback не содержат emittable текста/refusal/tool call. FnOnce расположен за прежним guard; replacement/append order, metadata, IDs, raw arguments, errors и состояние потока остаются прежними. Восстановление неполного ответа по-прежнему выполняется.
5. **Desktop: `desktop/01-targeted-view-notifications.patch`.** Ответ одному view не вызывает лишний runtime-wide notify. Targeted show/fail, ACK/latest queue, stale gates и resize сохраняются. Очистка общей runtime error по-прежнему уведомляет всех. Ready/error/restart/lifecycle notifications не удалены.
6. **Extensions: `extensions/01-markdown-prose-noop.patch`.** Для точного повторения единственного prose-сегмента и того же упорядоченного languages пропускается MDast/definitions parse. Используется уже сохранённый source, без нового кеша/копии всего текста. HTML node переиспользовался и раньше. host.show и текущие revision/session/sequence по-прежнему отправляются. Это не ускорение изменившегося streaming suffix и не объединение двух Markdown compilers.

## Проверка и применение

Точные upstream commits, исходные Git blob SHA и хеши патчей — в `SOURCES.json`; контрольные суммы доставки — в `SHA256SUMS`. Каждая папка относится к отдельному upstream checkout. Сначала `git apply --check --whitespace=error-all <patch>`, затем `git apply <patch>`; не применять вслепую к другой базе. Внутри папки порядок числовой. Пакет применим совместно с предыдущими пакетами PR #58/#59. Патч core/03 требует core/02 и проверен после него; обратный текстовый порядок не поддерживается. Остальные патчи независимы. SOURCES.json для core/03 отдельно фиксирует upstream и производную patch-base identity.

Выполнены source review автором и независимым reviewer, проверка исходных blobs, strict whitespace и patch application, сравнение candidate bytes и композиция патчей. Регрессионные Rust-исходники добавлены для history capture/COW, cancellation/admission/terminal, terminal reconstruction и Markdown refresh. Для notification-only изменения проверены callsites; native сценарии target/other view, stale response, error recovery, ACK/latest, resize/scroll и restart **не запускались**.

**Не запускались Rust/продуктовый код, cargo, тесты, сборки, UI, CI или benchmarks.** Source/application review не означает compile/runtime pass. Новых измерений latency, CPU, RSS/PSS нет. Upstream-репозитории не изменены; доставка содержит патчи, не автоматически применённый продукт.

Точные инварианты добавлены рядом с реализацией и в существующие Core runtime/process guides. Общие efficiency rules уже находятся в предыдущих пакетах; новый параллельный свод правил не создаётся.

## Глубокий остаток: почему пока не сделан shortcut

**Полный completed-transcript replay.** Он остаётся на пути завершения хода до снятия admission barrier. Важное уточнение: SQLite cache уже не переписывает неизменившиеся rows и не выделяет для них полную JSON-строку; оставшаяся работа — `hash_serialized`, сверка rows и полный validated journal replay.

Поздние final results заменяют ранние effects, checkpoint меняет видимость раннего model response, settlement завершает существующие tool rows; равные history_revision/message ID не доказывают одинаковый отображаемый ряд. Это видно в [transcript projector](https://github.com/Proteus-harness/Proteus-core/blob/60f667d53dd2b1e6f2e271f2e1af1e94cc63f316/crates/proteus-core/src/app_server/transcript/journal.rs). Warm writer содержит validation/usage/context, а не полный renderer state; ещё одна копия журнала увеличила бы удержание payloads.

Следующая реализация должна расширять существующий projector: committed post-sync cursor/generation/sequence, индекс зависимостей поздних фактов и самая ранняя изменённая позиция. Для недоказанных случаев — нынешний strict rebuild. Cursor и rows публикуются атомарно; display cache не становится execution authority. Эквивалентность требуется на каждом committed prefix, включая Replace/compaction, effects/final results, cancellation, restart и повреждённый cache, до заявлений об ускорении.

**Cancel ACK:** дополнительный патч 03 устраняет блокирующее ожидание в async adapter. Синхронным вызывающим сохранён recv_timeout, broker grace/terminal state machine и неизвестные побочные эффекты не переопределяются. Source tests покрывают yield на current-thread runtime, full/disconnected очередь, broker rejection, закрытие ACK sender, timeout, drop до/после enqueue и готовый ACK при истёкшем timer; они не запускались.

**Markdown MDast→HTML:** публичного прямого compiler bridge у используемого markdown 1.0.0 нет; новый parser/compiler ради этого не добавлен. **IPC encode-once** и **native Mermaid effective key** остаются отложенными по ранее описанным admission/memory и quota/error-order причинам.
