# Core: admission guard для abandoned invocation

Изолированный review bundle для `Qweasd123tg/proteus-modules-dot`.
Исходный Core не изменяется: patches применяются только в свежей временной
копии GitHub-hosted runner. Existing modules, performance bundle, PR #23
и их workflows остаются неизменными. Merge и auto-merge не включаются.

## Проверяемая проблема

Caller может отказаться от invocation во время блокирующего restart handshake,
при потере admission ACK либо пока root ждёт свободного места. Старое продвижение
очереди может передать такую работу writer; у истёкшего queued parent может
остаться активный nested child.

Fix повторно проверяет async terminal receiver после handshake, требует
доставленного ACK и проверяет отмену/deadline перед каждым activation.
Отклонение queued parent отменяет его nested tree перед итеративным продвижением
живого follower. Общие cancel semantics и generation failure domain сохраняются.

## Текущая source revision

- Core base: `63454d4e8b1e4e6b26d088fce2a17d46f30390ae`.
- `01-admission-tests.patch`: пять независимых regression cases,
  runtime test module и opt-in barrier только для generation-2 fixture handshake.
  Test helper использует текущие `ProcessWake`, `signal::channel` и
  пятую `wake`-позицию `LoopState::new`. Production admission logic
  tests-only стадией не меняется.
- `02-admission-fix.patch`: broker ACK, runtime admission/activation,
  cancellation helper и ближайшая русская архитектурная документация.
  Старые reviewed guard semantics сохранены; hunks привязаны к новой source.
- `manifest.json`: SHA256 inputs, Git blobs upstream/test/fixed стадий,
  exact test names, assertion markers, deadlines и отдельно historical evidence.
- `run_validation.py`: identities, patch application и bounded
  `result.json` с фактическими tree/commit/hash/argv/exit/test evidence.

Оба текущих patch SHA256 независимо совпали у автора и интегратора.
Каждая unified hunk и её счётчики проверены в памяти на точном current source;
исходные Git blobs совпали с official tree. Это не локальный `git apply`.
Независимый source/runner review обновлён: STATIC PASS.
Installed official Rust 1.95 stdin formatter подтвердил byte-identity всех
четырёх изменённых Rust files. Локальных builds/tests, source execution,
записи файлов или caches не было. Remote evidence новой revision ещё ожидается.

## Обязательные remote gates

1. Official Rust `1.95.0`; immutable Core source checkout.
2. Tests-only patch: каждый из пяти cases выполняется отдельным exact filter.
   Требуются exit 101, ровно его именованный FAIL, обычный libtest failure summary
   и конкретное reviewed assertion message. Compile/setup errors, empty filter,
   unrelated panic и timeout не считаются воспроизведением.
3. Fixed patch: весь `proteus-module-protocol` package.
   Обязательны пять новых PASS, существующий cancel-tree/reuse case
   и все 21 existing broker cases.
4. Отдельный реальный-module gate: весь `proteus-core --test module_swap`,
   все 16 текущих cases. Current Core `repositories.json` по-прежнему
   фиксирует Modules `7fceaebc3bed8add9b0e3091110f59deca86ba46`;
   его locked Core dependency graph остаётся upstream
   `bee0e409e746e2df9db32748d4f8ea02201bd4af`.
   Официальный `scripts/test.py` собирает fresh reference module и DCP fixture;
   prebuilt fixture overrides удаляются. Patched Core остаётся consumer.
5. Обязательный `cargo fmt --all -- --check` после behavioral gates;
   чистота tracked source; bounded evidence upload для exact bundle SHA.

Libtest output captured, без `--nocapture`, test threads=1.
Selector-based process-group watchdog получает declared deadline каждого check:
baseline 900 s, formatting 300 s, protocol package 1800 s, module_swap 3600 s.
Job deadline 90 min — дополнительная общая граница, не сумма обещанных SLA.

## Историческое evidence — не PASS текущей source

Предыдущий bundle commit `704504a3d9f5e0db25881d95a3fca065fd566546`
проверял Core `7435f2a6d90e532665ebed4da67526b609158fc8`.
[Run 40417973972](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40417973972)
прошёл независимый artifact audit: пять exact baseline behavioral failures,
затем protocol 52 PASS, module_swap 16 PASS, cargo fmt PASS, без timeouts.
Artifact `12696745620`, ZIP SHA256
`c2a218776741fd8000de14d8bdc7ff012681b2c8985a2e3eabaf103161a8360b`;
result SHA256
`5eaf47b428885fc8ff94858231049f37b4ff44dad9958a83bb38835c728e96ab`.

Upstream event-driven wakeup поменял constructor/channel API.
Простая замена manifest pin была бы недостаточна: test helper адаптирован,
production hunks и source identities пересверены. Старое evidence сохранено
в commit history и manifest, но не переносится как результат новой проверки.

## Границы утверждений

- Успешная отправка ACK не означает получение handle caller-ом.
- Guard до dispatch не исключает более позднюю гонку с отменой.
- Уже начавшаяся запись/работа module не получает гарантии отсутствия effects
  или rollback.
- Test watchdog ограничивает наблюдение; это не доказательство reclamation
  намертво зависшего admission thread.
- Direct admission-state tests не являются отдельной проверкой wake-loop scheduling.
- Full workspace, живой GUI, portable delivery и измерение производительности
  этим bundle не доказываются.
