# Module bundle destination retains caller path identity

## Результат и scope

Минимальный candidate для **известного PR85 build-portability №1**, не новая finding. Core `build_packages` теперь разрешает `--bundle` тем же `Path(...).resolve()`, которым уже разрешает `--target-dir`, прежде чем передать команду дочернему packager с другим cwd.

Общий invariant: **caller-owned output paths не меняют значение при смене рабочего каталога дочерней команды**. Новый helper/framework не добавлен; устранена несогласованность двух path-аргументов одной границы.

Фактически выполнены actual `build_packages` command-construction tests, Python **3.12.14**, `-I -B -S`:

- Baseline: **1 expected assertion failure**, `--bundle` остаётся `delivered runtime`, тогда как `--target-dir` уже абсолютный от caller cwd.
- Candidate: **5/5 passed**, без errors/skips.
- Packager, Cargo и любые child commands этой функции **не исполнялись**: `subprocess.check_output` замокан до вызова. Никакой реальной доставки/установки или изменения permissions.
- Strict apply/check и byte comparison успешны; независимый pre-run review выполнен, final evidence review хранится отдельно.

Это targeted boundary gate, не full packaging integration, не Rust/runtime gate и не новый реальный benchmark.

## Pins, contract и дедуп

- Core `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Delivery `f34cc3594268bc923c8383fef5f3d23021f0e0dc`, после PR142.
- Шесть source/doc blobs подтверждены Git blob/SHA256 (`SOURCES.json`, `READ-VERIFICATION.json`). Полный Modules `package.py` сохранён только для точной provenance; этот pass рассматривает лишь parsing/forwarding `--bundle` и `destination.resolve`, не прочие installation/security paths. Modules source не импортировался и не исполнялся.

Известный [build-portability report, пункт 1](https://github.com/Qweasd123tg/proteus-modules-dot/blob/f34cc3594268bc923c8383fef5f3d23021f0e0dc/research/proteus-continuous-audit-2026-11-13/evidence/build-portability/REPORT.md) уже описал реальную доставку в неверный каталог. Его историческое reproduction не повторялось и не считается результатом этого прохода.

Это не PR141: там выбранный executable basename расходился с metadata; здесь независимая ошибка **output destination** на Core→Modules boundary. Это также не PR142: concurrent portable publication/snapshot semantics не меняются. Candidate standalone относительно указанного Core SHA.

## Source chain

1. [Core parser](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/scripts/build_module.py#L49-L57) принимает `--bundle` как `Path`, без требования абсолютного пути, и передаёт его в `build_packages`.
2. [build_packages](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/scripts/build_module.py#L37-L46) сериализует destination буквально, но вызывает `check_output(..., cwd=source)` в checkout Modules. Соседний `--target-dir` уже разрешается в caller cwd.
3. [Modules parser/dispatch](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/package.py#L307-L327) принимает bundle как `Path` и передаёт его далее; [destination.resolve](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/package.py#L176-L180) выполняется в cwd дочерней команды. Поэтому переданный относительный текст имеет уже другую базу. Это source-level связь; consumer не запускался здесь.

Существующий `scripts/test.py` вызывает `build_packages(env=env)` без destination. Новый positive control сохраняет именно этот JSON-artifact return path. `test_conformance_selection.py` прочитан для действующего test scope; существующие Cargo/build tests не запускались.

## Patch

`module-bundle-path.patch`, SHA256 `4b69a3375a45496e4d199c52c8ccd783516ad8ffbd815adda65affd7c16d287d`:

```diff
- command += ["--bundle", str(destination)] if destination else ["--print-artifacts"]
+ command += ["--bundle", str(Path(destination).resolve())] if destination else ["--print-artifacts"]
```

Добавлен также docstring общего path invariant. Production diff **+2/−1**; отдельный test module — 114 строк. Не меняются child cwd, source selection, profile, env, reuse flag, artifact JSON shape, return-None при destination или exception propagation. Нет новых dependencies, output directories helper не создаёт. Никакого ускорения или общего packaging refactor не заявляется.

Обычный абсолютный путь остаётся тем же аргументом, что проверено control с пробелом/Unicode. Это **не обещание literal сохранения любого absolute string**: `resolve()` нормализует `..` и symlink spelling. Consumer уже выполнял такую нормализацию позже. Эквивалентность их значения для stable absolute paths следует из source; actual consumer behavior, symlinks и конкурентное изменение filesystem не тестировались.

## Фактические controls и повтор

Тестовый loader импортирует точный `build_module.py` с временным stdlib `sources` stub, восстанавливая `sys.modules`, включая прежние записи. Каждый test задаёт synthetic Modules checkout, отличный от caller cwd, и подставляет Mock вместо `check_output` до вызова helper. Временный chdir ограничен контекстом и восстанавливается. Никакие command/binary/package files не создаются или запускаются.

Candidate tests:

1. Relative bundle и relative target-dir получают caller prefix; profile, env identity, `--no-build`, interpreter и foreign cwd сохраняются; bundle directories не появляются.
2. `.` / `../output` / programmatic string destination получают ожидаемый absolute path.
3. Ordinary absolute bundle с пробелом и Unicode остаётся одним неизменным argv token.
4. Отсутствующий bundle сохраняет `--print-artifacts` и decoded JSON result, абсолютный target-dir и `env=None`.
5. Исходный `CalledProcessError` от mocked packager не поглощается и не заменяется.

Baseline запускает только test 1, candidate — все пять. Всего шесть executions: один expected red и пять green, не шесть passed. Exact logs/exit codes сохранены в `runtime/`, summary — `TEST-RESULTS.json`.

```sh
HOME="$PACKAGE/runtime/$MODE/home" TMPDIR="$PACKAGE/runtime/$MODE/tmp" \
  python3 -I -B -S "$PACKAGE/run_target.py" \
  "$PACKAGE/runtime/$MODE/scripts" "$PACKAGE/runtime/$MODE-expected.json" "$MODE"
```

`$MODE` — `baseline` или `candidate`. Baseline — `sources/core` плюс тот же новый test file; candidate — `after`. Драйвер проверяет оба source/test SHA256 до/после, test module path и точное число tests; loader проверяет production module path. Driver SHA256 `1035583a0bfff713b46f52190e7389a3860f83d960d2c7d1992d84e05d77d215`.

Strict `git apply --check --whitespace=error` и apply выполнены в отдельной копии; оба файла совпадают с `after/` (`APPLY-CHECK.json`). Это source application check, не реальная установка.

## Ограничения

Не запускались packager, source resolver, Git/Cargo builders, Rust, native binary, actual CLI subprocess, existing/full test suite, real bundle delivery, install, API или benchmark. Проверено построение команды настоящим helper на synthetic paths, а не физическое расположение доставленного executable. Upstream и production не менялись.

`PRE-RUN-REVIEW.md` содержит независимую проверку точного кода/driver до запуска. Final source/evidence verdict хранится в `INDEPENDENT-REVIEW.md`. Candidate не следует описывать как production-qualified installation fix.
