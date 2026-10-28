# Fast retirement: inventory, не выполненное удаление

Владелец предложил отказаться от `--fast` ради чистоты; затем уточнил,
что измеряет runtime speed/RAM поставляемой сборки. Основной build recipe
поэтому использует неизменённый release profile.
Решение удалить fast ещё не подтверждено; этот кандидат ничего не удаляет.

## Две разные поверхности

| Поверхность | Текущая семантика |
|---|---|
| CLI `scripts/portable.py --fast` | Core/reference release; native profile fast; полный assembly; архив пропускается |
| Cargo `[profile.fast]` | inherits release, opt3, lto=false, CGU16, incremental=true; native CGU256 |
| CLI `--no-archive` | Пропускает архив независимо от профиля; без --debug/--fast остаётся release |
| CLI `--debug` | Core/reference/native dev outputs в target/debug; extension packager всё ещё release |
| Без CLI mode flags | Release native/Core/reference, full assembly и archive |

`lto=false` означает отсутствие cross-crate LTO, а не строгий `"off"`.
Fast и release runtime/RAM не следует смешивать в одном comparison baseline.

## Exact inventory на закреплённых revisions

В Desktop проверены 32 non-vendor файла: Markdown docs, Python scripts,
workspace manifests и workflow; дополнительно прочитан .cargo/config.toml.
В этих файлах найдены следующие references:

| Файл | Строки | Что менялось бы при одобренном удалении |
|---|---|---|
| Cargo.toml | 63–73 | Комментарий, profile.fast, profile.fast.package.proteus-native |
| scripts/portable.py | 103, 122–123, 127 | CLI flag, native profile selection, archive condition |
| AGENTS.md | 36 | Рекомендованный delivery command |
| README.md | 33, 226, 230, 327 | Quickstart, режимы portable, объяснение profile |
| docs/ui-handoff-2026-10-23.md | 78 | Историческая handoff команда; явно отметить смену, не скрывать историю |
| Core AGENTS.md | 359 | Cross-repository portable instruction |
| Extensions AGENTS.md | 26 | Cross-repository portable instruction |

Desktop release workflow вызывает `python3 scripts/portable.py` без fast.
Extensions package.py не использует profile fast; его --dev остаётся release.
В inspected Desktop Python tests ссылок --fast/profile.fast не найдено.
Отсутствие таких строк не доказывает покрытие CLI behavior.

## Последствия возможного решения

- Для release iteration без архива существующий equivalent по цели:
  `python3 scripts/portable.py --no-archive`; это уже **другой native profile**,
  чем прежний --fast, а не идентичная переименованная команда.
- Полная release поставка остаётся `python3 scripts/portable.py`.
- Component-only release build остаётся
  `cargo build --release --locked -p proteus-native --jobs 2`.
- Артефакт native меняет расположение target/fast → target/release.
  Старый target/fast не удалять автоматически: это отдельное решение по диску.
- Первый release build после fast может компилировать ранее не созданные
  release artifacts; время нельзя сравнить с warm fast как равный cache state.
- ThinLTO/CGU1 release сохраняются для честных runtime/RAM сравнений.
- Если удаление одобрено: обновить все живые references согласованно; не оставлять
  молчаливый alias, который меняет profile под старым именем.
- До утверждения сохранять нынешнюю CLI/Cargo семантику и документацию upstream.

Источники: [Desktop Cargo][cargo], [portable.py][portable],
[Desktop README][readme], [Desktop AGENTS][agents], [handoff][handoff],
[Core AGENTS][core-agents], [Extensions AGENTS][ext-agents], [workflow][workflow].

[cargo]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/Cargo.toml#L57-L81
[portable]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/scripts/portable.py#L93-L129
[readme]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/README.md
[agents]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/AGENTS.md#L36
[handoff]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/docs/ui-handoff-2026-10-23.md#L78
[core-agents]: https://github.com/Proteus-harness/Proteus-core/blob/1f533a13f20a93bf164f7c8a169553b0b219bb51/AGENTS.md#L359
[ext-agents]: https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/3361fc1650c4ac6f167c3e48a0fba8980a5c9038/AGENTS.md#L26
[workflow]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/.github/workflows/release.yml#L123-L124
