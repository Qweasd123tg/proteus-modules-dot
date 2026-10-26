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

## Состав и происхождение

- Core base: `7435f2a6d90e532665ebed4da67526b609158fc8`.
- `01-admission-tests.patch`: пять независимых regression cases,
  runtime test module и opt-in barrier только для generation-2 fixture handshake.
  Production admission logic этой стадией не меняется.
- `02-admission-fix.patch`: broker ACK, runtime admission/activation,
  cancellation helper и ближайшая русская архитектурная документация.
- `manifest.json`: SHA256 входных файлов, Git blobs исходной/test/fixed стадий,
  exact test names, assertion markers и command deadlines.
- `run_validation.py`: сверка identities, применение patches, проверки и
  bounded `result.json` с фактическими tree/commit/hash/argv/exit/test evidence.

Оба исходных patch SHA256 независимо совпали у автора и интегратора.
Затем installed official Rust 1.95 rustfmt через stdin/stdout нормализовал
только новый test file; production Rust bytes остались неизменными.
Исходный и нормализованный hashes сохранены в manifest.
Каждая unified hunk и её счётчики проверены в памяти на точном upstream source;
исходные Git blob identities совпали с connector. Это не локальный `git apply`.
Независимое source review: STATIC PASS. Локальные compiler/tests
не запускались из-за защищённого порога свободного диска. Formatter работал
только через pipes, без записи файлов; full cargo fmt gate остаётся remote.

## Remote gates

1. Official Rust `1.95.0`; immutable Core source checkout.
2. Tests-only patch: каждый из пяти cases выполняется отдельным exact filter.
   Требуются exit 101, ровно его именованный FAIL, обычный libtest failure summary
   и конкретное reviewed assertion message. Compile/setup errors, empty filter,
   unrelated panic и timeout не считаются воспроизведением.
3. Fixed patch: весь `proteus-module-protocol` package. Обязательны пять новых PASS,
   существующий cancel-tree/reuse case и 21 existing broker test.
4. Отдельный реальный-module gate: весь `proteus-core --test module_swap`,
   все 16 текущих cases. Runner явно получает Modules
   `7fceaebc3bed8add9b0e3091110f59deca86ba46`; его locked Core dependency graph
   остаётся upstream `bee0e409e746e2df9db32748d4f8ea02201bd4af`.
   Официальный `scripts/test.py` собирает fresh reference module и DCP fixture;
   prebuilt fixture overrides удаляются. Patched Core остаётся consumer.
5. Обязательный `cargo fmt --all -- --check` после behavioral gates;
   чистота tracked source после tests; bounded evidence upload для exact bundle SHA.

Libtest output captured, без `--nocapture`, test threads=1.
Selector-based process-group watchdog получает declared deadline каждого check:
baseline 900 s, formatting 300 s, protocol package 1800 s, module_swap 3600 s.
Job deadline 90 min — дополнительная общая граница, не сумма обещанных SLA.

## Границы утверждений

- Успешная отправка ACK не означает получение handle caller-ом.
- Проверка до dispatch не исключает более позднюю гонку с отменой.
- Уже начавшаяся запись/работа module не получает гарантию отсутствия effects
  или rollback.
- Test watchdog ограничивает наблюдение; это не доказательство reclamation
  намертво зависшего admission thread.
- Пока нет remote evidence: runtime PASS не заявлен.
- Full workspace, живой GUI, portable delivery и измерение производительности
  этим bundle не доказываются.
