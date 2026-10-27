# Один extension package: read-only plan и ограниченный packaging design

## Что поставляет этот кандидат

`plan_extension_build.py` читает только Cargo.toml и extension.json из
существующего Extensions checkout, печатает JSON plan и заканчивает работу.
Нет subprocess, Cargo invocation, shell, копирования, установки, сетевого
доступа или выполнения native fixtures. Python 3.11+ нужен для stdlib tomllib.

Примеры вызова самого read-only planner:
```bash
python3 -I -B build-speed/desktop/plan_extension_build.py \
  --source /path/to/Proteus-desktop-extensions --package extension-files

python3 -I -B build-speed/desktop/plan_extension_build.py \
  --source /path/to/Proteus-desktop-extensions --all-packages
```

Выбор обязателен: один exact Cargo package name либо explicit full workspace.
Неизвестный package, дублирующее имя, несоответствие Cargo binary и
`extension.json command`, неподдержанный workspace layout — ошибка. Допускаются ровно два unique members:
`sdk` и `packages/*`, без exclusions, чтобы full path действительно включал SDK.
Planner не выводит угаданный executable path: expected_artifacts содержит
package/binary identity, не готовый artifact.

Для selected build план содержит `-p extension-files --bin files`.
Для selected tests — `-p extension-files`, без `--bin`, чтобы не исключить
integration tests и другие test targets выбранного package.
Full tests используют `--workspace`, включая SDK; не `--bins`.
Build остаётся release, тесты — прежний default test profile. Это разные
artifact sets; не требуется выполнять обе команды на каждой итерации.

Pure unit tests читают только сам planner и синтетические строковые manifests:
`python3 -I -B build-speed/desktop/test_plan_extension_build.py`.
Они не запускают Cargo или native код. Их pass не является native evidence.
Фактический статус проверки указан в candidate validation record.

## Почему пока не меняется upstream package.py

[Текущий package.py][source] всегда вызывает release workspace build, затем
размещает все binaries. `--dev` — режим размещения, не Cargo profile.
Desktop runner рассчитывает на подготовленный полный набор extensions.
Нельзя незаметно дать общему gate только один package и считать его full pass.

Минимальный будущий interface:
- `package.py --dev --package extension-files`: собрать и разместить только
  выбранный package; не удалять/перезаписывать соседние packages.
- `package.py --dev --all-packages`: явно весь набор.
- Существующий `--bundle`/ZIP/full delivery путь сохраняет полный набор.
  На первом этапе `--package` с `--bundle` или ZIP mode отклоняется,
  чтобы частичный результат нельзя было выдать за полный portable.
- Desktop `scripts/test.py`, `scripts/run.py` и release gates продолжают
  готовить полный набор. Избирательная подготовка используется только отдельным
  focused package workflow; общий launcher не приобретает skip-by-default.
- При изменении SDK/public protocol нужен full producer/consumer gate,
  а не выбранный package.
- Ни profile defaults, ни release optimization, ни provenance/notices,
  runtime dependencies или policy permissions не меняются.

Такой интерфейс можно внедрить отдельной проверяемой правкой позже. В этом
кандидате нет patch, который запускает сборку или меняет поставку.

## Cargo JSON artifact discovery: HOLD

Уже есть источник истины в Core [scripts/build_module.py][core-builder]:
он читает executable из compiler-artifact, а не угадывает target/debug.

В Desktop portable текущие пути жёстко заданы как repo/target/profile.
Inherited `CARGO_TARGET_DIR` способен отправить новую сборку в другое место,
пока assembly читает старый binary. Поэтому нельзя сейчас советовать общий
external target directory для portable.

Изолированная будущая правка должна:
1. Запросить Cargo `--message-format=json-render-diagnostics` с теми же
   package/bin/profile/locked flags; не менять оптимизации.
2. Принимать artifact только для ожидаемого package + binary target,
   не test harness/library/build script. Проверить package identity или
   manifest_path, если поле есть, а не только совпадение имени.
3. Требовать успешный exit Cargo и ровно один соответствующий executable.
   Отсутствующий/неоднозначный artifact — ошибка, без target fallback.
4. Сохранить rendered diagnostics и корректно обработать nonzero/malformed
   output без потери ошибки дочернего процесса.
5. Передать найденный path в существующий copy step; сохранить полный набор,
   версии, source pins, notices, manifest и smoke evidence.
6. Проверить обычный и absolute/relative target dirs, свежий и reused artifact,
   ошибку Cargo, duplicate/missing artifact, совпадающие имена чужих packages.
7. Повторить реальную packaging/relocation проверку перед заявлением готовности.

Пункты 5–7 затрагивают native/release packaging и не подтверждены source-only
проверкой. Поэтому exact executable patch здесь не включён. Нет обхода
запрещённого native fixture, пересборки DCP или изменения upstream.

[source]: https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/3361fc1650c4ac6f167c3e48a0fba8980a5c9038/package.py
[core-builder]: https://github.com/Proteus-harness/Proteus-core/blob/1f533a13f20a93bf164f7c8a169553b0b219bb51/scripts/build_module.py
