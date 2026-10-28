# Измерение build cost отдельно от runtime speed/RAM

Это будущий рецепт, не выполненный benchmark. Не запускать native сборки,
тесты или окно до отдельного разрешённого этапа и достаточного свободного
диска. Текущий disk floor — причина не создавать новый target сейчас.

## Не менять сравниваемый продукт

Основной baseline и candidate используют один release profile Desktop:
opt-level 3, ThinLTO, codegen-units 1, strip. Fast/dev — другие эксперименты,
их runtime/RAM нельзя выдавать за результат shipping release.
Для сравнения фиксируются также exact Core, Modules и Extensions binaries,
config, features, native libraries, launcher environment и графическая среда.

Одинаковые release flags сами по себе не доказывают один и тот же executable.
Записать binary SHA-256/размер, Cargo package/target identity и фактический
resolved feature graph выбранного scope. Cargo.lock не фиксирует включённые
features. При переходе workspace → selected package feature unification может
измениться; сначала сопоставить graph, а не считать artifact эквивалентным.
Разные source edits закономерно дают разные hashes: identities нужны для
точного attribution, не как требование равенства разных версий.

Сравнение native-only build и portable build отвечает на вопрос стоимости
оркестрации/упаковки. Оно не доказывает изменение скорости работы приложения.

## Build measurement

1. Зафиксировать commits и dirty diff, lockfiles, Cargo config, фактический
   rustc/Cargo version, OS/CPU/RAM, linker, Cargo env и свободный диск.
   Не сохранять credentials или полный пользовательский environment.
2. Использовать существующий стабильный target и фиксированные release flags.
   Не очищать target ради baseline. Если нужен cold baseline, новый отдельный
   target возможен только после разрешения и проверки диска; иначе отметить
   cold measurement как not-run.
3. В разрешённом release build добавить `--timings` и `-vv`, сохранить
   Cargo stdout/stderr. Пример команды для Desktop:
   `cargo build --release --locked -p proteus-native --jobs 2 --timings -vv`.
   Системный measurement wrapper может измерять wall/CPU/RSS; его точный
   вариант должен быть одинаковым в baseline/candidate.
4. Отдельно зафиксировать warm no-op и warm edit rebuild. Для edit использовать
   одну и ту же reviewed правку и неизменную revision stamping policy.
   Не подменять source edit одним touch: такой probe измеряет иной случай.
5. Разделять preparation, Cargo compile/link, copy/assembly и archive.
   Native-only цикл не вызывает portable или extension packaging.
6. Повторные контролируемые измерения проводить только в согласованном
   observation window, не запускать циклы без ограничения нагрузки.
   Сравнивать median/range, а не выбирать единственный лучший результат.

Минимальный receipt:
```json
{
  "schema": 1,
  "status": "not-run",
  "profile": "release",
  "source_commits": {},
  "command_argv": [],
  "environment_fingerprint": {},
  "resolved_feature_graph": {"digest": null, "evidence": null},
  "artifact": {"package_id": null, "target_name": null, "executable_sha256": null, "bytes": null, "compiler_artifact_evidence": null},
  "cache_state": "unknown",
  "dirty_units": [],
  "wall_seconds": null,
  "cpu_seconds": null,
  "peak_rss_kib": null,
  "target_bytes_before": null,
  "target_bytes_after": null,
  "compile_link_evidence": null
}
```

Cargo timings и процессный peak RSS имеют разные границы наблюдения.
Не называть RSS одного процесса суммарной памятью всего process tree;
если нужен общий peak, применять один и тот же способ измерения process group/
cgroup и описать его. Параллельные rustc/linker процессы учитывать явно.

## Runtime measurement

Только после разрешённого native smoke и подтверждения exact executable paths:
- сравнивать одинаковую release сборку компонентов и одинаковый набор extensions;
- одинаковые synthetic workspace, transcript/data, окно, масштаб и renderer;
- измерять startup/first frame, idle и representative interaction раздельно;
- RAM записывать отдельно для Desktop, backend, extension processes и суммарно;
- одинаково учитывать RSS/PSS/shared mappings и прогрев;
- отделять first-run shader/font/cache preparation от тёплого состояния;
- не использовать live credentials/пользовательские сессии в публичных artifacts.

Быстрее Cargo build не означает быстрее runtime или меньше RAM.
Component-only build не обновляет portable: нельзя случайно сравнить новый
target binary со старой установленной копией. Перед каждым разрешённым запуском
проверить точный executable/source identity и пути runtime dependencies.

## Cache policy для отдельного будущего изменения

[Desktop CI][ci] сейчас сохраняет registry/git/npm, но не compiled target;
`CARGO_INCREMENTAL=0` не запрещает cache обычных compiled dependencies.
Не включать incremental и не расширять disk cache автоматически.

Для будущего target cache потребуются раздельные namespaces по workspace/
section, OS/image/arch/target, toolchain, profile/features и build flags.
Primary key с source revision, restore prefix только для совместимого
окружения, после restore всегда Cargo freshness validation.
Наличие binary на диске само по себе не доказывает свежесть.
Сначала оценить disk budget и стоимость передачи cache.

[ci]: https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/.github/workflows/release.yml#L21-L73
