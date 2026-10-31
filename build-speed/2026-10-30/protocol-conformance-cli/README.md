# Conformance CLI: opt-in dependency boundary

Предложение для Core `befd30516aefa6f0a0ad5db9924ad4957160b8dc`:
`conformance-cli-feature-final.patch`. Точная идентичность patch и baseline —
в `SOURCES.json`; проверка пакета — `SHA256SUMS`.

Protocol library больше не включает clap без необходимости. Существующий
conformance binary требует feature `conformance-cli`; его parser, protocol
checks, worker authority и schema validation не изменены. Нового crate,
дублирующего CLI, runtime option или compatibility wrapper нет.

`scripts/test.py full` явно включает feature и сохраняет unit tests бинарника.
Manual CI сохраняет полный gate и standalone Rust starter/conformance smoke,
обновляет явную сборку CLI и добавляет mocked runner-selection regression.
Обновлены существующие команды в архитектурном документе и пяти примерах,
а также testing guide. Всего 11 путей. Regression source проверяет full,
library-default и explicit-feature selection без запуска Cargo внутри fixture;
сам тест в этом проходе не запускался.

Независимое source review не выявило blocker. Строгое forward/reverse применение
полных файлов и точное восстановление baseline/candidate проверены отдельно.
Автор проверил оба порядка композиции с contracts-runtime proposal `dcb6de94`;
эта композиция не является исполненным dependency resolution.

Optional dependency не означает отсутствие clap во всей сборке: Core имеет
свою direct edge, другие modules могут тоже использовать clap, Cargo features
объединяются. Cargo.lock сохраняет dependency для соответствующих targets;
версии/pins и lockfile вручную не изменены. Modules фактически использует Core
`1f533a13f20a93bf164f7c8a169553b0b219bb51`: нужен настоящий Core integration
commit и обычные consumer/lock gates, чтобы новый cut дошёл до workers.

Остаются **неисполненными**: runner unittest; --locked protocol default и CLI
feature tests; Core full gate; Rust starter smoke; normal dependency tree
выбранного worker и consumer integration. Не запускались project code, tests,
scripts, Cargo, builds, CI или benchmarks. Это source-reviewed candidate, не
merge-ready интеграция и не измеренная экономия времени/RAM.
