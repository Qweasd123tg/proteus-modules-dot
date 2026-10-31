# Дополнение: совместимость общего payload событий

База Core: `befd30516aefa6f0a0ad5db9924ad4957160b8dc`.
Предложение: [PR73](https://github.com/Qweasd123tg/proteus-modules-dot/pull/73),
head `6a57de168a3a4b2f8baaec929b0cf50d8da62941`, patch SHA-256
`87aa0e1f52641b015068552faad926aa36e7473ca421a2d7ceefc064ebcc1a17`.

## Статическое применение

Проверен порядок: PR63 terminal → PR65 worktree → PR66 journal → PR68 CLI →
optional PR67 runtime + typed-Core → PR71 broker → PR72 writer → PR73 shared event.
Каждый patch применён со строгой проверкой whitespace; обратное применение
восстановило точные исходные bytes и отсутствие новых файлов. Это source
composition, **не** compilation, behavioral tests или готовая интеграция.

Единственное новое пересечение путей — `docs/guides/runtime-and-events.md`
с PR66. Перестановка PR73 перед PR66 также применяется и обращается точно;
конечные bytes совпадают. Изменения руководства находятся в разных hunks.
Прежние packets не пересекают `app_server.rs` и изменённые event/ACP/HTTP
Rust-файлы. Новая полная pairwise-матрица не выполнялась.

## Потребители и API

- Сверены Git blob identities всех 594 Rust-файлов pinned дерева; поиск
  потребителей выполнен по 589 active-файлам. Пять research-файлов исключены
  из semantic coverage. Прежние packets не добавляют raw AppServer consumers.
- Все 14 raw handle subscription sites покрыты caller inventory предложения
  и миграцией shared test helpers. Оставшийся owned `Receiver<AppServerEvent>`
  относится к отдельному HTTP activity channel, а не raw publisher.
- **Public Rust API меняется:** `AppServerHandle::subscribe` возвращает
  `broadcast::Receiver<Arc<AppServerEvent>>`. Внешним callers вне pinned дерева
  нужна собственная миграция; это не drop-in Rust-совместимость.
- ACP заимствует event и клонирует только потребляемые owned поля; HTTP activity
  watcher заимствует event. Publisher принимает прежний owned event, а его
  внутренний send error содержит Arc. Известные callers не требуют старого
  типа payload ошибки.
- View/pending mutation предшествует Arc allocation; порядок sequenced → raw →
  pending watch сохранён. `AppSubscription::recv` по-прежнему возвращает owned
  event, фильтрует covered seq до преобразования и сохраняет Shutdown exception.
- Contracts DTO, boxed StdioOutput, JSON wire, capacities, lag/drop policy,
  action routing и pins не изменены. Shared ownership не гарантирует отсутствие
  deep clone при каждом accepted SSE/stdio delivery.

Не запускались project code/scripts/tests, Cargo, build, CI, runtime или
benchmarks. Compile/consumer/behavioral gates остаются обязательны; измеренный
выигрыш не заявляется. Optional PR67 и PR73 не становятся обязательными друг
для друга от успешного статического применения. Queue и action-route HOLD
не затронуты.
