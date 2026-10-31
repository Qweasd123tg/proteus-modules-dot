# Дополнение: совместимость PR71 с текущими source-пакетами

30 октября 2026. **Конфликтов исходников не найдено; это не сборка и не
проверка поведения.** Дополнение к [предыдущей композиции Core/Modules](https://github.com/Qweasd123tg/proteus-modules-dot/blob/312d87297af27635556b15abd63b00865316e368/docs/source-composition-2026-10-30/COMPOSITION.json),
без повторения её матрицы и большого манифеста. Modules здесь не перепроверялись.

## Точные входы и порядок

Патчи предназначены для upstream исходников, не delivery-репозитория.

- **Core `befd30516aefa6f0a0ad5db9924ad4957160b8dc`:**
  terminal (PR63) → worktree (PR65, окончательный `38eb7954…`) → journal
  (PR66) → cli (PR68) → optional runtime → optional typed_core (PR67) →
  broker (PR71).
- **Desktop `a28cc7f507424a570e86dc44230ee323156fdf6c`:**
  bounded-live-pump (PR69) → **общий** desktop-resync (PR70) → hidden-chain
  (PR71). Отдельные два resync-патча поверх общего не применять.

PR63/65/66/67/68 имеют те же полные identities, что в предыдущем манифесте.
Новые для этой композиции delivery heads:

| PR | Точный head | Patch SHA-256 |
|---|---|---|
| [69](https://github.com/Qweasd123tg/proteus-modules-dot/pull/69) | `06b3b2bc231b15ae81296071ecb215f64257a6f0` | `ada1f395c3ecaaf16723a16d2cd8d60a6fa6cb65cca9537e637ae90558ba3f9b` |
| [70](https://github.com/Qweasd123tg/proteus-modules-dot/pull/70) | `0b835868058dd58a608a707fc1f3d6ba7c5bd9c8` | `2945c429305bc986d7a91d1062e8c985c4ce5ccd2422e81b9cec1ff92d67d789` |
| [71 — broker](https://github.com/Qweasd123tg/proteus-modules-dot/pull/71) | `a0b008554544db1b22b6e81fe525b27df080c836` | `80def7b6bc48aa6abf96a3a679c2b71800204df8bb73a7bac50d20b982624280` |
| 71 — hidden-chain | тот же head | `c2cd77263f073f5b48b257e898f3a81a76e73dffdc539c4f97adedd03064a67b` |

## Что проверено

- Повторно использованы sparse baseline bytes; 55 Core и 13 Desktop файлов
  (включая нужный контекст) совпали с закреплёнными Git blob identities.
- Каждый полный порядок выше применён один раз через
  `git apply --whitespace=error-all`, затем снят в обратном порядке через
  `git apply --reverse --whitespace=error-all`. Восстановлены точные исходные
  bytes и исходный набор файлов, включая отсутствие добавленных test files.
- PR71 не пересекается изменёнными путями с другими перечисленными patches.
  Единственное пересечение Desktop PR69/70 — `src/ui/chat/pump.rs`:
  дополнительно применены resync → pump → hidden-chain, результат побайтово
  равен основному порядку; reverse также точен. Новая pairwise-матрица не нужна.
- Direct installed rustfmt 1.95.0, edition 2024, `skip_children=true`:
  проверены broker/runtime/drop-tests и Desktop pump/session/stream_batch/
  thread/chains в совместном результате. Это синтаксис/форматирование,
  не typecheck.

## Смежные callers и границы

Core: PR71 меняет приватный `LoopState::run` и его broker caller согласованно;
остальные packets не добавляют callers или `BrokerInner` constructors.
CLI feature остаётся границей conformance binary, а optional contracts API
не меняет stop/wake ownership. ContextDispatcher по-прежнему может удерживать
broker: новый self-drop путь не отправляет блокирующий Shutdown и не join-ит
себя; внешний Drop сохраняет FIFO Shutdown + join. Это не немедленный запрет
нового admission внутри уже начатого finish/reset и не доказательство
quiescence внешних writers. Terminal/worktree receipts такого обещания
также не добавляют.

Desktop: ready-batch/yield остаётся вокруг прежнего apply_batch; snapshot,
reconnect и lag остаются barriers, не text-coalescing. Resync решение остаётся
после cursor acceptance, RunSettled — после применения snapshot. Hidden-chain
guard работает в подготовке перед render, читает актуальный displayed
transcript и те же chain/motion keys; не меняет reducer, очереди или settlement.
Открытая/движущаяся цепочка сохраняет подготовку; закрытая неподвижная —
пропускает её. Между порциями возможен render: это не доказательство native
fairness, анимации или Copy.

## Что остаётся незапущенным

Не запускались project code/scripts/tests, Cargo/rustc, сборки, CI, native UI,
benchmarks или transport fixtures. Не перепроверялась полная старая матрица.
Нужны разрешённые behavioral gates ownership/lifecycle, reconnect/lag и
native hidden-update/reopen/motion/Copy; source-topology tests не проверяют
реальный UI guard. PR67 остаётся optional coordinated proposal: настоящий
Core commit, consumer pins, lockfiles и executable gates не появились от
чистого применения patches. Pins и locks не изменены.

Bounded producer queue и action-route proposals остаются **HOLD**, не входят
в эту композицию и не получают нового разрешения. Нет заявлений о готовности
к merge, полной интеграции или измеренном ускорении/RSS/latency. На другой
upstream revision нужны новые preimages и review.
