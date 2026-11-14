# Proteus: упаковка и переносимость, дополнительный проход

Дата: 2026-11-13. Две воспроизведённые границы: установка Core при явном native Cargo target и Linux shortcut при переносе portable. Production-код не менялся; push, PR и установка в пользовательские каталоги не выполнялись.

## 1. P2: Core installer успешно устанавливает старый executable после успешной новой сборки

**Подтверждено.** [install.sh:12–17](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/install.sh#L12-L17) сохраняет Cargo configuration, включая `CARGO_BUILD_TARGET`, но [строка 66](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/install.sh#L64-L68) копирует предполагаемый `<target-dir>/release/proteus`. При `CARGO_BUILD_TARGET=x86_64-unknown-linux-gnu` свежий executable находится в `<target-dir>/x86_64-unknown-linux-gnu/release/proteus`. Это native target текущей машины, не cross-compilation.

### Реальное воспроизведение

Исполнен неизменённый `install.sh` из указанного commit, настоящий Cargo/rustc 1.95.0, offline tiny package с теми же package/bin names. Для исключения несвязанных сборок `scripts/build_module.py` заменён локальным stub; все действия installer с Core binary, release snapshot, current symlink, installed wrapper и configs настоящие.

1. Первый запуск без явного target собирает и устанавливает binary, выводящий `OLD`.
2. Исходник меняется на `NEW`, задаётся `CARGO_BUILD_TARGET` с native host.
3. Второй installer завершается **0** и публикует новый snapshot.
4. Свежесобранный target-specific executable выводит **NEW**.
5. Установленный wrapper и его новый snapshot всё ещё выводят **OLD**.

Контроль с новым пустым target-dir: новая сборка проходит, затем installer падает на `cp .../release/proteus`; snapshot не публикуется. Тихая неверная установка возникает именно в warm checkout, где остался старый conventional artifact.

**Связь с предыдущим аудитом:** причина аналогична ранее найденной ошибке SDK gate в Desktop `release.py`, но это отдельный подтверждённый consumer и последствие: не ложный smoke gate, а успешная установка старого Core. Не следует считать это независимым новым классом ошибки. Module bundler в настоящем проекте уже получает executable из Cargo JSON, поэтому исправление должно выровнять выбор Core artifact, а не угадать ещё один путь.

**Направление исправления:** выбирать единственный `compiler-artifact.executable` нужного package/bin после подтверждённого успешного Cargo build. Учитывать действующий target/config без ручного формирования layout. Регрессия: OLD warm build → NEW native-targeted build → установленный wrapper обязан вывести NEW; cold targeted build тоже должен завершаться успешно.

Доказательства: `probe_core_install_target.py`, `core-install-results.json`, `core-install-fixture/commands.log`. Полный Core и его модули не собирались; модель/провайдер не вызывались.

## 2. P3: installer ярлыка сообщает успех, но ярлык не запускается после переноса в часть допустимых Linux-путей

**Подтверждено настоящим GLib/GIO, не парсером-имитацией.** [scripts/portable/install-shortcut:20–27](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable/install-shortcut#L20-L27) подставляет путь без кодирования `.desktop` key values / `Exec` field codes. Обычных внешних кавычек недостаточно.

В каждом случае запущен неизменённый installer, затем настоящий `gio launch` созданного `.desktop`. GPUI binary заменён harmless marker script. Все каталоги установки/XDG изолированы; прямой запуск того же executable успешен во всех 6 случаях.

| Каталог | Installer | `gio launch` | Marker |
|---|---:|---:|---|
| `Portable` | 0 | 0 | создан |
| `Portable folder` | 0 | 0 | создан |
| `Portable тест` | 0 | 0 | создан |
| `Portable 100%` | 0 | 1 | не создан |
| `Portable "test"` | 0 | 1 | не создан |
| `Portable\test` | 0 | 1 | не создан |

Для `%` `desktop-file-validate` обнаруживает invalid field code `%/`, а GIO пытается найти другой executable path, где исчезли `%/`. Для кавычек и backslash `desktop-file-validate` возвращает 0, но GIO отказывается загрузить application information. Поэтому одной syntax validation без фактического запуска недостаточно.

**Направление исправления:** сериализовать `Exec` и `TryExec` по их реальной `.desktop` семантике, не shell quoting. В частности, literal percent для Exec требует отдельной обработки; backslash и quoted path требуют учёта key-value и argument layers. Добавить поведенческую matrix к текущему shortcut test. Временно использовать путь без этих символов и переустановить shortcut.

Доказательства: `probe_shortcut_paths.py`, `shortcut-results.json`, `shortcut.log`, generated `.desktop` files в `shortcut-fixtures-repro/`. Нативное окно приложения не запускалось; доказан запуск desktop entry, а не GUI smoke.

## SHA и проверки

Все четыре remote `main` проверены read-only через `git ls-remote origin refs/heads/main` во время этого прохода:

- Core: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Modules: `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Desktop: `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions: `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.

Целевые существующие тесты Desktop: `test_release_shortcut.py` **1 passed**, `test_release_cargo_binary.py` **39 passed**. Оба reproduction scripts прошли свои assertions. Desktop audit checkout: `git status --short` пустой, `git diff --check` чисто. Core installer bytes взяты через `git show HEAD:install.sh`; его SHA256 записан в result JSON.

## Охват и ограничения

Просмотрены production packaging/launcher/source-resolution/metadata scripts Desktop, package.py Modules и Extensions, Core install.sh и scripts/build_module.py. В `coverage.tsv` перечислены проверенные source files и hashes. Это не утверждение о полном чтении всех четырёх репозиториев.

Из этого прохода исключены уже известные Ghostty warm-cache pin, joint Desktop/Extensions protocol validation и catalog checkout/revision проблемы. Полная сборка приложения, GUI session, весь Rust gate, настоящая установка у владельца, live providers и release publication не выполнялись. Реальные пользовательские профили/секреты не читались. Report содержит только синтетические fixtures.
