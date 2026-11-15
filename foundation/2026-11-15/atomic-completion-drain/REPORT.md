# Collaboration wait: проверка наличия через owned atomic drain

## Результат

Подготовлен **непроверенный source candidate для небольшого invariant simplification**. Existing drain_completions уже атомарно извлекает batch под mutex; candidate использует полученный owned Vec как единственный ответ на вопрос, есть ли у данного waiter update.

Удалён отдельный has_completions и два check-then-act места. Нового lock, helper, framework, публичного DTO или dependency нет. Независимый exact review не нашёл source-level blockers.

**Не заявляется новый consequential production incident, обычный serial workflow failure или выполненный regression reproduction. PR118 delivery HOLD не исправляется.**

## Версии

Fresh refs в начале и конце, 2026-11-15:
- Core `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Modules Core pin `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Delivery `0c850261aac4edd2da955ef6e8c66179310695c1`, включая PR119.

Десять прочитанных Core blobs совпадают main/actual pin и проверены по Git SHA. Patch адресован текущему Core baseline, а не автоматически собранному стеку всех delivery candidates. Modules pin не изменяется.

## Source witness и точная reachability

В старом WaitAgentTool initial path и notified loop вызывают has_completions, затем drain_completions. Эти методы берут один mutex **в разных critical sections**:

1. Waiter A получает true от has_completions.
2. Конкурент B извлекает доступный batch.
3. A получает пустой Vec от drain и возвращает timed_out=true, хотя его ненулевой timeout ещё не истёк.

Это source interleaving, не исполненная трасса. Между вызовами нет await: один serial executor thread сам по себе не воспроизводит такое переключение. Нужен действительно конкурентный thread consumer. Частота и штатный пользовательский путь такого concurrency здесь не доказаны.

Исходный loop уже явно описывает competing waiters и обещает ждать собственный deadline, когда чужой consumer забрал broadcast update. Candidate делает этот invariant локальным к единственной atomic операции, вместо надежды на неизменность queue после отдельной проверки.

## Изменения и сохранённые свойства

- Initial path делает один drain. Непустой Vec возвращается сразу; empty при timeout=0 остаётся обычным polling timeout; empty при ненулевом timeout начинает ожидание.
- Loop возвращает только непустой Vec, который извлёк именно этот waiter. Empty drain не завершается ложным ранним timed_out.
- notified создаётся, pin-ится и enable-ится **до** loop drain. Arrived-before-registration completion находится в queue, arrived-after-enable либо находится drain, либо будит waiter.
- После чужого consumption wake не считается доказательством владения результатом.
- Same mutex, batch limit 8, snapshot/history handling, ordering и queue consumption сохраняются.
- Lock/lookup errors продолжают проходить через существующий Result; timeout cancellation и deadline implementation не переписаны.
- Не вводятся fairness guarantee или новая трактовка настоящей гонки completion на самой границе timeout.

Production строки двух файлов: 1075→1067. В непустом queue path отдельная query-lock операция исчезает: query+drain заменены одним drain. Это source fact, не измеренные contention/latency/CPU/RAM improvement.

## Что остаётся открытым

Consumption всё ещё происходит до JSON serialization, Core caps и AfterTool transformations. Нет delivery acknowledgement, accepted-record set, persistent reread или возврата records в queue. Следовательно:
- cross-record splice/consumed-report gap PR118 остаётся;
- не обещается, что completion дошёл до модели целиком;
- схема старых generations и retention не меняется;
- PR119 file-read invariant, PR117 usage/accounting и остальные family не закрываются этим patch.

## Proposed test, NOT RUN

Один новый contract scenario в отдельном tests/wait.rs использует существующие in-memory TestHost и private CollaborationControl:
- вручную poll двух WaitAgentTool futures до Pending;
- одна completion будит обоих, первый waiter забирает её;
- второй остаётся Pending и получает следующую completion;
- заключительный zero poll показывает отсутствие повторной выдачи.

Он проверяет поведение competing waiters при broadcast и subsequent delivery без настоящих peers. **Он не заставляет старый CPU-interleaving между двумя locks и может пройти на baseline.** Это дополнительное contract coverage, не failed-before/passed-after regression evidence. Existing timeout/poll/followup scenarios не изменены.

При разрешённом toolchain нужны compile и focused collaboration tests, затем подходящий Core gate. Детерминированного воспроизведения исходной межпоточной гонки или real workflow incidence этот пакет не содержит.

## Verification

- 10 source blobs: SOURCES.json; все 10 локальных blobs повторно проверены publisher по Git SHA.
- Patch прошёл только git apply --check --whitespace=error и текстовое применение; after bytes совпали.
- Independent exact source review: ATOMIC-WAIT-INDEPENDENT-REVIEW.md.
- Новых references has_completions в сохранённом полном collaboration module source нет.
- Общий build/композиция со всеми прежними Core candidates не выполнялись.

Patch SHA256: `512d41de07d99ed11d6579f5fefcb751a7b5f61a013c5273f60745d6b257df86`.

Публикуются только patch, report, independent review и sanitized source identities; raw source snapshots и промежуточные журналы исключены.

Rust/cargo/compiler/formatter/tests/project scripts/fixtures/runtime/provider calls не запускались. Ничего не устанавливалось. Upstream production и refs не менялись; публикация этого пакета в delivery repository не применяет patch в Core. Публиковать только как conditional source-level invariant candidate, не подтверждённый production bugfix.
