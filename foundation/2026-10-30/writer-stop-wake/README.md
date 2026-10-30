# Остановка idle writer без потери пробуждения

Узкое исправление Proteus-core на базе
[`befd30516aefa6f0a0ad5db9924ad4957160b8dc`](https://github.com/Proteus-harness/Proteus-core/commit/befd30516aefa6f0a0ad5db9924ad4957160b8dc).
Это отдельная ошибка process-host writer, не повтор исправления final-owner
ComponentBroker.

## Подтверждённый исходниками порядок

1. В `spawn_writer` прежний цикл проверяет `stopping == false` и может быть
   вытеснен **до** чтения `wake.revision()`.
2. `ProcessTransport::terminate` устанавливает stopping и уведомляет wake.
   Lifecycle завершает/reaps child и уведомляет wake; stdout reader завершает
   работу и также уведомляет wake. `join_workers` сначала дожидается reader.
3. Writer возобновляется после этих уведомлений, читает уже новую revision,
   обнаруживает пустые очереди и вызывает `wait(observed, None)`.
4. Нового уведомления может не быть. Transport всё ещё владеет writer senders
   во время join, поэтому очередь не disconnected. Join writer зависает.

Это доказательство достижимого interleaving по исходникам, **не** результат
воспроизведения runtime-зависания.

## Изменение

В начале каждой итерации сначала запоминается revision, затем проверяется
stop-флаг. Если stop уже виден, writer выходит; если stop происходит позднее,
изменение revision не позволяет уснуть на старом наблюдении.

Порядок control/data queues, проверка stop перед записью, бюджеты, завершение
dispatch, draining и join не изменяются. Новых каналов, потоков, polling,
таймеров, test hooks или публичных API в production-коде нет. Исправление не обещает общего
effect quiescence либо мгновенного запрета новых эффектов.

## Regression source и пределы проверки

В существующий session harness добавлен **один** сценарий с настоящим
ProcessTransport и сохранённым writer clone. Реальный mock child заранее
завершается/reaps через lifecycle; затем terminate/join проверяется в helper
thread с watchdog. Поэтому сбой этой join-проверки не оставляет живой mock
process, ожидающий stdin. При успешном завершении проверяется отказ записи.

Сценарий не форсирует точный промежуток между atomic load и revision и не
обещает надёжного падения на старом коде. Нет зеркальной копии writer loop,
sleep-based ordering или большого stress-прогона. Watchdog ограничивает
ожидание join-проверки, но не освобождает зависшие потоки и не ограничивает
предшествующее lifecycle termination: обычный внешний timeout runner остаётся
необходимым.

**Пройдено статически:** исходные Git blob identities, forward/reverse apply,
whitespace, побайтовое совпадение дерева после применения, rustfmt двух файлов.
**Не запускались:** compilation/type checking, tests, Cargo, project scripts,
CI, product runtime или mock child. Fixture только подготовлен как исходник.
Перед merge нужен разрешённый gate process-host/session.

Соседние проверенные границы не требуют похожих механических правок:
LifecycleInner отправляет Terminate через unbounded sender и не делает join;
transport workers не владеют самим ProcessTransport; SDK callback completion
удаляет уникального sender перед единственной отправкой в пустой channel
ёмкости 1. SDK RuntimeShutdown не делает join. В просмотренных шести исходниках
Modules module-runtime второго такого механизма нет. Это ограниченный аудит,
не гарантия отсутствия любых других ошибок блокировки.

Идентичности: `SOURCES.json`, `MODULES-SCAN.json`.
Независимое review: `REVIEW.md`.
Узкая композиция с broker patch из [PR71](https://github.com/Qweasd123tg/proteus-modules-dot/pull/71):
`COMPOSITION.json`. Оба порядка строгого применения дали одинаковые файлы;
обратное применение обоих порядков восстановило baseline побайтово.
Это разные crates и только два patch, не проверка runtime всего стека.
Контрольные суммы: `SHA256SUMS`.
