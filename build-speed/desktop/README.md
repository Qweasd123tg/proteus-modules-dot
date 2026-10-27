# Desktop: release-итерации без лишней переупаковки

Статус: source-only кандидат. Native build, executable, UI, Cargo tests и CI
для этого кандидата не запускались. Команды сборки/проверки ниже — рецепт для
будущего разрешённого выполнения, не сообщение о выполненной проверке и не
обход ранее запрещённого запуска. Исходные репозитории не изменяются.
Никакие изменения DCP или native fixture в пакет не входят.

## Зафиксированные источники

- [Desktop 50f8b53b686816e7e32b89901aa6ed399826fb37][desktop]
- [Core 1f533a13f20a93bf164f7c8a169553b0b219bb51][core]
- [Extensions 3361fc1650c4ac6f167c3e48a0fba8980a5c9038][extensions]
- Desktop связывается с `proteus-contracts` из Git
  `f2ef701ef53c7bd45ba3acf58360fa1e77ddfb60`, а не автоматически с соседним Core.
  Это отдельный compilation pin, не доказательство несовместимости.
- Перед переносом рецепта на новые revisions повторно прочитать manifests,
  [Desktop AGENTS][agents] и [Core testing guide][testing].

## Что действительно модульно

Desktop workspace содержит root binary `proteus-native` и library
`proteus-client-common`. `src/ui/chat`, `src/ui/settings`, `src/tabs` —
Rust `mod` внутри root crate, не отдельные binaries или shared libraries.
[Manifest][desktop-cargo] и [entrypoint][desktop-main].

```text
proteus-native -> proteus-client-common -> proteus-contracts (Git pin)
              -> proteus-contracts (тот же Git pin)
              -> gpui-kit -> patched gpui-component / renderer chain

proteus-native -- HTTP/SSE --> отдельный proteus executable
proteus-native -- stdio ----> отдельные extension binaries
```

Внешнее расширение на существующем widget protocol можно менять без
перекомпиляции Desktop. Новый нативный виджет или изменение общего контракта
требует обновления producers/consumers и соответствующих проверок.
[Process spawn][extension-process], [граница расширений][extension-boundary].

Cargo собирает compilation units/crates, а rustc incremental переиспользует
части вычислений и code generation. Изменение одного `mod` не означает
перекомпиляцию всех dependencies, но root binary обычно нужно перелинковать.
Generic/inline-код может порождаться в consumer crate; выделение crate не
обещает полной изоляции компиляции. [Rust monomorphization][monomorph].

## Основной цикл: измерение скорости и RAM release-сборки

Цель владельца — проверять runtime speed, RAM и поведение поставляемой сборки.
Поэтому основной цикл сохраняет release settings: opt-level 3, cross-crate
ThinLTO, codegen-units 1, strip. Замена на dev/fast, отключение LTO или снижение
оптимизации делает сравнение другим экспериментом, а не ускорением той же сборки.
Для component-only iteration собираем тот же release binary без полной упаковки:

```bash
cargo build --release --locked -p proteus-native --jobs 2
```

CWD — Desktop. На неизменённых dependencies Cargo может переиспользовать artifacts.
Изменение native требует relink; cross-crate ThinLTO может делать этот шаг дорогим
даже после небольшой правки. Дешёвая независимая «перелинковка одного UI-файла»
не обещается. [Release profile][desktop-cargo].

## Команды для выбранного компонента

Выполнять только в отдельной разрешённой рабочей копии, после проверки диска,
toolchain и native prerequisites. Не выполнять все строки подряд:
это альтернативы для разных затронутых компонентов.

| CWD | Изменённый компонент | Команда |
|---|---|---|
| Desktop | UI/root binary: runtime/RAM сравнение | `cargo build --release --locked -p proteus-native --jobs 2` |
| Desktop | Отдельная отладка, НЕ release performance evidence | `cargo build --locked -p proteus-native --jobs 2` |
| Desktop | Только client-common library, release | `cargo build --release --locked -p proteus-client-common --lib --jobs 2` |
| Extensions | Только files implementation | `cargo build --locked --release -p extension-files --bin files --jobs 2 --message-format=json-render-diagnostics` |
| Extensions | Явно весь набор | `cargo build --locked --release --workspace --jobs 2 --message-format=json-render-diagnostics` |
| Core | Core/backend, не UI, release | `cargo build --release --locked -p proteus-core --bin proteus --jobs 2` |

Не добавлять `cargo clean`, не удалять `target`, не менять profile, flags,
debug settings или toolchain между тёплыми итерациями.
`--jobs 2` ограничивает Cargo concurrency, но не является жёстким CPU/RAM cap.
[Существующий Desktop resource limiter][limits] дополнительно использует
низкий priority и Linux systemd scope; прямой Cargo этот wrapper не вызывает.

Для существующих unit/package проверок, когда их запуск разрешён:

- Desktop: `cargo test --locked -p proteus-client-common --lib --jobs 2 -- --test-threads=4`.
- Extensions: `cargo test --locked -p extension-files --jobs 2 -- --test-threads=4`.
- Полный Extensions gate сохраняется отдельно: `cargo test --locked --workspace --jobs 2 -- --test-threads=4`,
  затем применимые Python behavior tests по существующей документации.

Это focused evidence, не замена обязательному Desktop runner/живому окну
при соответствующей правке. Не выбирать focused tests вместо полного gate
для общей schema, SDK или нескольких взаимодействующих packages.
Нет автоматического запуска этих команд из planner.

## Build не равен Run или Install

Компонентный Cargo build только обновляет artifact. Он не копирует extension
binary в `packages/<id>/bin`, не устанавливает ZIP и не обновляет portable.

Для последующего запуска Desktop потребуются:
1. Рабочая графическая сессия и native libraries/toolchain согласно README.
2. Актуальный совместимый backend: `PROTEUS_BIN` имеет приоритет, затем
   проверяется binary рядом с клиентом и `PATH`. [Backend lookup][backend].
3. Подготовленные extension binaries и корректный `PROTEUS_EXTENSIONS_DIR`.
   Без override checkout assets обнаруживаются только для executable под
   `<desktop>/target`; внешний target directory требует явного пути.
   [Asset discovery][asset-discovery].
4. Отдельная синтетическая рабочая папка/профиль, без пользовательских
   credentials и реальных сессий в проверочных логах.

`scripts/run.py` сам подготавливает extensions через `package.py --dev`.
Это удобно для полного dev launch, но не минимальный native-only build loop.
В текущем упаковщике `--dev` означает размещение binary рядом с manifest;
он всё равно вызывает release build всего workspace. [package.py][packager].

## Ожидаемая матрица пересборки

При одинаковом toolchain/profile/features и сохранённом target:

| Правка | Cargo/rustc работа | Не требуется из-за одной этой правки |
|---|---|---|
| UI Rust mod | native target, incremental reuse и relink | Core/extension builds |
| client-common | library и зависимый native | Backend/module runtime |
| Встроенная тема JSON | native, из-за include_str! | Отдельные extensions |
| Пользовательская тема JSON | Rust build не нужен; читается при старте | Все Rust crates |
| gpui-component patch | patched crate и selected reverse dependencies | Core |
| Renderer shader | patched renderer и selected reverse dependencies | Core |
| extension-files implementation | files binary и изменённые dependencies | Desktop binary/Core |
| Extension SDK | SDK и затронутые extension binaries | Desktop при неизменном wire |
| Core runtime | Core library + proteus | Desktop при неизменном HTTP/DTO |
| Core DTO | Зависимые Core crates; Desktop после обновления его source pin | Автоматическое принятие sibling edits |
| Новый commit | Version stamp может изменить native/Core target | Все dependencies автоматически |

Матрица выведена из исходников, не измерена. Конкретные `Fresh`/dirty units
нужно зафиксировать Cargo output. Bundled [theme][theme] и [shaders][shaders]
встроены; [build.rs][build-script] следит за HEAD/ref для version provenance.

## Предложение отказаться от fast

Владелец предложил отказаться от `--fast` ради чистоты, но удаление ещё не
подтверждено. Этот кандидат ничего не удаляет. CLI `portable.py --fast` и Cargo
`[profile.fast]` — разные поверхности: первый выбирает второй только для клиента
и пропускает архив; сам профиль меняет codegen/LTO/incremental.
Точный inventory и последствия — [fast-retirement.md](fast-retirement.md).

## Почему portable — отдельный checkpoint

`portable.py --fast` вызывает Core/reference release builds, native fast
build и заново подготавливает полную переносимую папку.
Cargo может переиспользовать свежие units; нельзя говорить «всегда
перекомпилируется всё». Однако staging/copy/assembly повторяются.
[portable.py][portable].

Не менять существующие `--fast`, release gates, provenance, notices,
полный набор runtime dependencies и финальную проверку поставки.
Промежуточный компонентный build не объявляется проверенной поставкой.
После завершённой проверенной правки действуют repository delivery rules.

## Измерение и следующий небольшой разрез

Рецепт — [measurement.md](measurement.md).
Сначала сравнить release native-only loop с полной release packaging, не вводя crate split и не меняя оптимизации.

Для отдельного будущего изменения `src/diff` — небольшая std/serde boundary,
`src/tabs` — более крупная std/serde boundary без GPUI в inspected production
files. Это кандидаты, не доказанный bottleneck. Новый sibling crate должен
сохранить GPL; перенос GPL-кода в Apache client-common недопустим.
Ни dynamic ABI, ни универсальный hot reload не предлагаются.

[desktop]: https://github.com/Proteus-harness/Proteus-desktop/tree/50f8b53b686816e7e32b89901aa6ed399826fb37
[core]: https://github.com/Proteus-harness/Proteus-core/tree/1f533a13f20a93bf164f7c8a169553b0b219bb51
[extensions]: https://github.com/Proteus-harness/Proteus-desktop-extensions/tree/3361fc1650c4ac6f167c3e48a0fba8980a5c9038
[agents]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/AGENTS.md
[testing]: https://github.com/Proteus-harness/Proteus-core/blob/1f533a13f20a93bf164f7c8a169553b0b219bb51/docs/development/testing.md
[desktop-cargo]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/Cargo.toml
[desktop-main]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/main.rs#L1-L24
[extension-process]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/declarative/process.rs#L39-L69
[extension-boundary]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/README.md#L372-L390
[monomorph]: https://rustc-dev-guide.rust-lang.org/backend/monomorph.html
[limits]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/scripts/limits.py
[backend]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/backend.rs#L159-L167
[asset-discovery]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/declarative/manifest.rs#L138-L156
[packager]: https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/3361fc1650c4ac6f167c3e48a0fba8980a5c9038/package.py#L20-L29
[theme]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/ui/theme/mod.rs#L13-L40
[shaders]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/vendor/gpui-fast-wgpu/src/wgpu_renderer.rs#L24-L47
[build-script]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/build.rs
[portable]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/scripts/portable.py#L56-L125
