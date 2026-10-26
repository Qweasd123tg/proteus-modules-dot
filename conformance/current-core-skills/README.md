# Проверка совместимости: Core1fc + portable SDK3f

Отдельный вариант `../core-skills` из PR10, commit
`e9a01ddf30a3240597fb427e2f29091f600e1240`. Исходный пакет, lockfile,
документация и его принятые результаты не изменены.

- Host Core и SDK authored probe: `1fc3ef223d10322815dd9290a50d045bc95402bb`.
- Portable executable: неизменённые исходники и lockfile из
  `592ad5cab6ab35fa181756a42607a32a696d9ccd`; его SDK остаётся
  `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`.
- Два самостоятельных Cargo workspace/графа. Совпадающие имена crates не
  означают единый Git source identity. Переноса portable на SDK1fc нет.

Повторяются те же **11 причинных сценариев**, в том же порядке и с теми же
assertions (`scenarios.json`; описание в `../core-skills/README.md`). В Rust
изменён только `core_commit` в отчёте, в manifest — два `rev`, в scenarios —
ожидаемый pin. Адаптация API или ослабление проверок не выполнены.

## Двухфазная проверка

Первая экспериментальная CI-фаза делает только resolution/fetch/metadata,
без компиляции и запуска Rust. Исходный host lockfile используется как seed;
`cargo update --workspace` не является доказательством минимального diff.
Lock-only CI40300268434 завершён успешно на commit `f0260bc8a84c4e77e8494475a659c50e0c3c0724`.
Новый `Cargo.lock` содержит только замену Git source identity у пяти Proteus
crates с3f на1fc; остальные bytes/versions/checksums/dependencies сохранены.
Host граф:246packages; portable:144packages. См. `LOCK-DELTA.json`.
Независимый review полного lock/metadata и runtime-source composition обязателен
**до** публикации commit, включающего runtime workflow.

Этот отдельный commit закрепляет новый lockfile и переключает
тот же workflow на исходный authored gate `ci/run.sh`: 11 Core checks,
11 отдельных verifier controls, 4 capture controls, неизменённый внешний
resource envelope с 35 mock controls. Сборка — только hosted, минимум 8 GiB
на входе; sampled reserve 1 GiB, 1800 s envelope, bounded pipes/archive.
Локальная компиляция из-за дискового резерва не разрешена.

Это проверка конкретной mixed-pin пары и model-free
`RuntimeRegistry/context callback/BoundTools`, не общий приём current Core,
полный agent turn, reference assembly, provider eval, sandbox, TOCTOU защита
или доказательство завершения всех descendants. Старое runtime acceptance
PR10 не распространяется на этот вариант. Binary bytes не публикуются;
неизменность одного executable до/после внутри текущего run проверяет
source-reviewed capture. Portable пересобирается из неизменённых source/lock/SDK3f
в отдельном графе; побитное равенство бинарнику старого PR10 между runs не
заявляется, поскольку старые binary bytes не опубликованы.

Frozen portable сохраняет deprecated serde_yaml/unsafe-libyaml; миграции
парсера и полного dependency-security audit здесь нет.
