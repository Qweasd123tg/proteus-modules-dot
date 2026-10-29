# Resource admission policy для Proteus — исходниковый прототип

**Статус:** отдельный pure Rust crate без внешних зависимостей. Исходники написаны
и прочитаны вручную; **сборка, тесты, CI, benchmark и запуск исходников не
выполнялись**. Совместимость компилятора и работоспособность исполнением не
подтверждены. Репозитории Proteus не изменялись. Это не включённое ограничение
runtime и не production-ready модуль.

## Задача и граница

Модуль предлагает совместное распределение ресурсов для уже готовых invocation:

- concurrency конкретного provider;
- существующие process/role slots;
- именованный exclusive resource;
- необязательные консервативные token upper-bound units.

Host передаёт проверенную готовность, полный demand и snapshot доступности.
Модуль возвращает детерминированный план либо конкретную ошибку. Он **не**
проверяет DAG, не удостоверяет `ready`, не выдаёт права, не резервирует ресурсы,
не запускает процессы, не хранит journal, не восстанавливает workflow и не
управляет lease. Имена `HostReadyItem` и `ProposedGrant` не превращают обычные
данные в доказательство или capability.

Это продолжение раздела «Совместное резервирование ресурсов» из
[`durable-workflows.md`](../../reports/durable-workflows.md),
а не перенос чужого scheduler. Исходные границы Core закреплены отчётом на
[`125a9eb4088991513e9f61d899469be2076e266c`](https://github.com/Proteus-harness/Proteus-core/tree/125a9eb4088991513e9f61d899469be2076e266c).
Дополнительное открытие трёх pinned Core-файлов через web в этом задании вернуло
`Cache miss`; новой прямой проверки этих файлов и утверждения об интеграции нет.

## API

Основные типы находятся в [`src/lib.rs`](src/lib.rs):

| Тип / метод | Назначение |
| --- | --- |
| `PendingQueue::new(epoch, limits)` | Ограниченные pending-данные одного host coordination domain. |
| `enqueue(HostReadyItem, tick)` | Добавить host-verified invocation; выделить стабильный `Ticket`. |
| `cancel(ticket)` | Идемпотентно убрать только pending item; поменять queue revision при удалении. |
| `remove_pending(&tickets)` | Удалить весь набор pending items либо ничего; используется также внутри host commit. |
| `ResourceSnapshot` | Host epoch, resource revision, monotonic tick и ceilings/availability. |
| `AdmissionPolicy::plan(&queue, &snapshot)` | Заменяемая data-only граница решения. |
| `AgingFifoPolicy { barrier_after_ticks }` | Реализация FIFO scan с aging barrier. |
| `GrantPlan` | Revision-bound proposal: полные grants, причины defer и aggregate reservations. |

`ResourceKey` содержит `ResourceKind` и строковое имя. Разные kinds — разные
пространства имён. Имена сравниваются точно, с учётом регистра и Unicode bytes;
никакой нормализации пути, case-folding, разрешения symlink или определения
footprint здесь нет. Host обязан назначать общий canonical key одному реальному
ресурсу. `Exclusive` требует `units == 1` и `ceiling == 1`; `available` равно 0
или 1. Для остальных kinds допускается ceiling 0, но положительный demand тогда
получит явный отказ.

`invocation_id` различает попытки выполнения, а не только node ID. Host не должен
допускать двух активных владельцев с одним invocation identity за пределами
этой очереди. `ready_fact_revision` привязывает запрос к версии host facts, но
сам по себе не проверяет их. Demands неизменяемы в очереди; изменение требует
удаления и новой host-проверки/enqueue, теряя прежний возраст и ticket.

## Что именно гарантирует алгоритм по своим входным данным

1. Сначала проверяется весь snapshot и наличие/ceiling каждого demand каждого
   pending item. Даже неверный элемент за aging barrier не скрывается.
2. Очередь обходится в порядке enqueue. Входной порядок ресурсов snapshot и
   demands не влияет на порядок grants; demands и aggregate отсортированы по
   `(kind, name)`.
3. До локального вычитания проверяется **весь** demand item. Если хотя бы одного
   ресурса мало, для item не вычитается ничего.
4. Для complete grant локальная availability уменьшается целиком. Никаких
   реальных holds при этом не возникает. Deferred item не получает даже
   «предварительного» hold.
5. Итог содержит exact aggregate этих demand-данных в canonical порядке и
   stamp `(coordination_epoch, queue_revision, resource_revision, observed_at_tick)`.
   Одинаковые входы и policy дают одинаковый результат; системное время не читается.

«All-or-none» относится к **каждому demand** внутри решения и ко **всему набору
выданных grants** при host commit. Это не требование удовлетворить всю очередь:
план может включать несколько полных grants и несколько deferred items.

Поля `GrantPlan` публичны для замены policy и передачи данных. Их можно подделать
или изменить. Ни default policy, ни stamped proposal не заменяют независимую
проверку ресурсов и разрешений host-ом.

## Fairness: FIFO с явно выбранной ценой

Если старый item помещается, он выбирается раньше новых. Если он временно
заблокирован, но его возраст меньше `barrier_after_ticks`, последующие подходящие
items могут его обогнать. Возраст вычисляется как
`snapshot.observed_at_tick - item.enqueued_at_tick`.

Когда заблокированный item достигает порога, он становится barrier **для всех
более молодых items, в том числе с полностью независимыми ресурсами**. Они
получают `BehindAgedBarrier`. Это осознанный head-of-line blocking: защищаем
старые requests от постоянного обхода ценой throughput. Порог 0 — строгий FIFO
при первом временном блокировании.

Гарантии конечного ожидания нет без предпосылок: host продвигает monotonic tick,
повторяет планирование, не сбрасывает возраст пере-enqueue, а действующие
владельцы действительно освобождают нужные ресурсы. Barrier не отбирает ресурсы
у запущенного владельца и не решает deadlock внутри пользовательского кода.
Число обходов молодого item не ограничено отдельным счётчиком; ограничено окно
по host ticks, если host корректно двигает время. Неподвижные ticks лишают aging
его смысла. Единицу ticks и порог определяет host, не модель.

## Невыполнимые requests и ошибки

- `UnknownResource { ticket, resource }`: host должен исправить ресурсный
  каталог/demand либо убрать item в существующий host rejection/quarantine path.
- `DemandExceedsCeiling { ticket, resource, requested, ceiling }`: request не
  может поместиться даже без других владельцев; это **ошибка**, а не вечное
  ожидание и не aging barrier.
- При таких ошибках **весь вызов `plan` возвращает `Err`**, без частичных grants.
  До устранения неверного item остальные тоже не получают план. Для продолжения
  host явно устраняет причину или удаляет данный ticket и пересчитывает план.
- `QueueFull`, oversized inputs, пустые/контрольные ID, пустой demand, нулевые
  units, дубли invocation/resource, неверный exclusive demand, неверный snapshot,
  регресс ticks, несовпадение epoch и exhausted counters — типизированные ошибки.
- Все арифметические переходы counters и availability checked. Переполнение не
  оборачивается. Исчерпанный epoch/counter требует host reconciliation и нового
  **никогда ранее не использованного** epoch, не сброса counters на месте.

Неизвестный ticket в `cancel` возвращает `Ok(false)` и не меняет revision.
Множественное `remove_pending` сначала проверяет весь набор и только затем
меняет очередь один раз; unknown/duplicate ticket оставляет её нетронутой.

## Ограничения размера и стоимости

| Ограничение | По умолчанию | Hard maximum |
| --- | ---: | ---: |
| Pending items | 256 | 4096 |
| Resources snapshot | 256 | 4096 |
| Demands на item | 16 | 64 |
| UTF-8 bytes ID | 128 | 256 |

Queue не удерживает чрезмерную spare capacity переданных строк/векторов: после
проверок копируются только допустимые данные. Память, уже выделенная самим host
для сырых входов, не контролируется crate. Отказ allocator/OOM не преобразуется
в recoverable `AdmissionError`; это не hard-real-time/memory-proof реализация.

При `Q` pending items, `R` ресурсах и до `D` demands на item планирование использует
`BTreeMap`: примерно `O(R log R + Q D log R)` сравнений bounded keys; результат
занимает `O(R + Q D)` bounded данных. Enqueue проверяет очередь за `O(Q)` и
сортирует demands за `O(D log D)`. Batch removal простое, до `O(Q K + K²)` для
`K` tickets, ограниченных capacity. Это анализ исходников, не измерение скорости.

## Единственная точка интеграции и atomic commit

Размещать adapter **перед dispatch существующего workflow/AgentControl**, а не
внутри advisory `planning.ready_steps`. Host-owned execution facts устанавливают
готовность; model/caller `ready/completed` не принимаются как authority. Уже
существующие `ExecutionAdmission`, immutable runtime snapshot, cancellation,
policy/approval/safety и process/role permits остаются обязательными.

Порядок host adapter:

1. Проверить execution facts, identity, актуальные разрешения и cancellation.
   Составить полный canonical demand по окончательному действию; не доверять
   свободно заявленному моделью расходу или footprint.
2. Под контролем **одного** resource/mutation coordinator получить snapshot
   доступности и monotonically versioned epoch/revision; добавить проверенные
   requests в принадлежащую host очередь. Любое изменение readiness,
   cancellation или demand должно инвалидировать соответствующий pending item
   и/или проверяться заново перед commit.
3. Вызвать pure `plan`, не удерживая реальные части demand во время ожидания.
4. В едином serialized/transactional commit проверить stamp против текущих
   epoch/queue/resource revisions; повторно проверить readiness revisions,
   cancellation, invocation binding, действующий runtime/policy snapshot и
   полномочия. Проверить уникальность tickets, exact demands, aggregate и текущие
   ceilings/availability независимо от заменяемой policy. Устаревший/поддельный
   план отвергнуть, ничего не резервируя.
5. Атомарно зарезервировать **все** aggregate resources и удалить соответствующие
   pending tickets, проверив заранее возможные ошибки queue removal; повысить
   resource revision. При любой невозможности не менять ни queue, ни resource
   accounting. Сам `remove_pending` не делает межкомпонентную транзакцию.
6. Выдать invocation-bound reservation владельцу существующего dispatch. Если
   dispatch не состоялся, host обрабатывает возврат в этой же системе владения,
   не повторяя side effect по догадке.

Если существующие semaphore/permits нельзя включить в такую all-or-none
транзакцию или надёжный согласованный acquisition protocol, **enforcement ещё
не реализован**. Последовательное ожидание semaphore при уже удерживаемом
exclusive resource — запрещённый для этого дизайна hold-and-wait. Этот crate не
делает независимые semaphores атомарными автоматически.

Связанный [mutation-coordinator prototype](../mutation-lease-state-machine-prototype/README.md)
— **не второй scheduler и не второй
независимый источник ownership**: admission только предлагает ranking и полный
набор demand. Named exclusive должен резервироваться тем же host coordinator,
который управляет mutation leases, footprint, quiescence и settlement. Нельзя
считать успешный `plan` полученным mutation lease или независимо учитывать один
worktree в двух несогласованных таблицах. Resource snapshot обязан отражать
активные leases этого единственного владельца, включая uncertain owners/barriers.

`cancel` здесь удаляет pending item. Отмена/timeout уже запущенного invocation
не доказывают окончания процесса и не освобождают его lease. Возврат ресурсов
требует host-confirmed окончания владельца/effect tree; одного TTL недостаточно,
а использование expiry для takeover потребовало бы fencing. Эти механизмы
намеренно отсутствуют в policy.

## Token upper bounds и права

`TokenUpperBound` — необязательные целые единицы заранее ограниченного расхода.
Bucket/horizon, meaningful upper bound, provider retries/fallbacks, учёт actual
usage и возврат неиспользованного остатка определяет host. Если верхней границы
нет, этот dimension не добавляется; тогда token budget **не обеспечивается**
этим plan. Приблизительную оценку нельзя выдавать за гарантированную границу.
Даже корректный token upper bound не является обещанием точной денежной цены.

Resource grant не предоставляет filesystem/network capability, не объединяет
права разных exports одного component и не сохраняет approval для повторного
вызова. Все права и разрешения остаются у host. JSON/FFI, криптографическая
аутентификация inputs, durable queue, leases, fencing и Core adapter не входят
в этот исходниковый прототип.
