# Proteus: установка, snapshot и относительные пути

Проверка 2026-11-13. Production-файлы не изменялись, публикации нет.

## Ревизии

`git ls-remote origin refs/heads/main` подтвердил:
- Core: `89997df995df7c39b713e16aba216ecb19c8f497`
- Modules: `3270dc0f894eaf4d0360306052b806099b8f5351`
- Desktop: `75bf201764278eac4b50d156650edcf1429101ff`

Среда: Linux x86_64, Rust/Cargo 1.95.0, Python 3.12.14, Git 2.52.0. Cargo работал offline; fixtures собираются в отдельных target-каталогах. Известные CARGO_BUILD_TARGET installer, SDK gate, desktop shortcut, Ghostty cache и portable protocol gate повторно не считаются.

## 1. P2: относительный `--bundle` меняет значение после смены cwd

**Подтверждено без mock упаковщика.** `build_packages` сохраняет `destination` строкой, но запускает `package.py` в checkout Modules. Modules правильно разрешает полученный путь относительно своего cwd. Core должен был разрешить путь до перехода границы процесса.

- `python3 scripts/build_module.py --profile release --bundle direct-bundle`, запущенный из Core, возвращает 0; `Core/direct-bundle` отсутствует, результат находится в `Modules/direct-bundle`.
- `PROTEUS_HOME=relative-runtime sh install.sh` тоже возвращает 0 и печатает Installed.
- Core публикуется в `Core/relative-runtime/releases/<id>/proteus`, а модули остаются в `Modules/relative-runtime/releases/.<id>.tmp/bin/`.
- В опубликованном snapshot вообще нет module binary. Host-wrapper запускается, model-wrapper возвращает 127 (`not found`).
- Положительный контроль: тот же fixture, те же production scripts, тот же Cargo cache, но абсолютный PROTEUS_HOME. Install и model-wrapper возвращают 0.

Источники:
- [Core scripts/build_module.py:37–46](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/scripts/build_module.py#L37-L46)
- [Core install.sh:64–72](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/install.sh#L64-L72)
- [Modules package.py:176–180](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/package.py#L176-L180)

Направление исправления: нормализовать destination на стороне Core до subprocess cwd; перед публикацией проверять фактическое наличие ожидаемых module manifests/binaries. Простое устранение этой ошибки не делает относительный PROTEUS_HOME независимым от cwd при дальнейшем запуске wrapper; это отдельная оговорка интерфейса.

Evidence: `probe_relative_bundle.py`, `relative-results*.json`, `relative-probe*.log`, `relative-fixture*/commands.log`. Неизменённые install.sh, build_module.py, sources.py, package.py; настоящие Cargo/rustc, manifests, artifact parsing, SHA-256 и filesystem publish. Только содержимое тяжёлых Core/module crates заменено двумя минимальными binaries.

## 2. P2: ошибка обновления managed config не откатывает уже включённый release

**Подтверждено реальной filesystem-ошибкой.** Installer переключает `current`, устанавливает wrappers и снимает cleanup traps до копирования managed fragments/prompts.

1. Полностью устанавливается B.
2. Существующий читаемый `configs/fragments/codex-runtime.toml` получает режим 0444. Пользователь процесса обычный uid 1000, не root.
3. Сборка C и модулей успешна, затем обычный `cp` завершается `Permission denied` на этом fragment.
4. Installer возвращает 1, но `current` уже указывает на C; новый wrapper `--version` показывает C.
5. Первый managed fragment (`openai-chatgpt.toml`) уже C, следующий (`codex-runtime.toml`) остался B. Старый snapshot B сохранён, но автоматически не выбран обратно.

Это не сбой Cargo и не mock `cp`. Ошибка возникает в штатной операции после commit point. Доказаны частичная активация и смешанные файлы; реальный сбой model/profile из-за несовместимости содержимого не симулировался. В fixture версии fragments отмечены безвредными комментариями.

Источники:
- [Core install.sh:91–117](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/install.sh#L91-L117)
- [Core install.sh:127–158](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/install.sh#L127-L158)

Направление исправления: подготовить и проверить managed assets до переключения release и сохранить rollback для уже изменённых файлов; явная политика для разных filesystem и пользовательских named configs. Один предварительный access-check не гарантирует отсутствие последующей ошибки записи.

Evidence: `probe_installer_snapshot.py`, `results*.json` (`config_failure`), `fixture*/commands.log`. Installer неизменён; реальные Cargo и filesystem. Тяжёлая Core binary заменена fixture-хостом, модульный producer заменён маленьким локальным fixture producer.

## 3. P2: запущенный host не привязан к своему snapshot модулей

**Подтверждена сквозная цепочка wrapper → production process-host → worker.** Wrapper экспортирует PATH с символическим `current/bin`, а не с однажды выбранным конкретным release. После новой установки PATH старого процесса не меняется текстуально, но разрешает уже другой каталог.

Результаты одного живого host-процесса:

| Шаг | Host | Worker |
|---|---|---|
| Запуск установленного A | A | A |
| Установка B, прежний worker ещё работает | A | A |
| Тот же host после reset/restart worker | A | **B** |
| Контроль: host A с PATH на конкретный snapshot A, после reset | A | A |
| Новый запуск wrapper после установки B | B | B |

Использован неизменённый `proteus-process-host` из указанного Core commit: `ProcessHost::request/reset` и настоящий дочерний JSONL worker. Production Core components хранят bare command в `ProcessSpec`; broker при новой generation запускает тот же spec через `ProcessTransport`, а trusted launch использует `Command::new` без закрепления release. Сам Core/model/v3 handshake здесь не запускался; несовместимость конкретных контрактов A/B не утверждается. Подтверждён переход executable поколения под живым старым хостом, который при несовместимом обновлении способен дать ошибку протокола вместо однородной сборки.

Источники:
- [Core install.sh:46–60](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/install.sh#L46-L60)
- [ProcessComponentConfig::process_spec](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/config.rs#L67-L86)
- [Component broker ensure_worker](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-module-protocol/src/v3/runtime.rs#L162-L184)
- [Trusted launch](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-process-host/src/launch.rs#L7-L17)

Направление исправления: разрешать current в конкретный snapshot один раз при запуске wrapper и использовать его для exec и PATH. Это не решает общую проблему mutable managed config из пункта 2 и не требует backward-compatibility shim.

Evidence: `probe_installer_snapshot.py`, `results*.json` (`live_snapshot`). Модульный producer fixture, не полноценная сборка Modules; процессный transport и lifecycle настоящие.

## Проверки и ограничения

- Core Python scripts: **9 passed** (`core-python-tests.log`).
- Modules package tests: **13 passed** (`modules-package-tests.log`).
- Изолированные reproductions содержат assertions и положительные controls. Повторные чистые запуски сохраняются отдельно.
- `git diff --check` Core/Modules: passed; checkout остаются clean.
- Полный Core gate, real-provider evaluation, Native GUI, полная сборка portable и Windows/macOS не запускались. Это не отчёт о проверке всего проекта.
- Не выполнялись изменения production-файлов, git commit, push или PR.

## Повторение

В среде с Rust toolchain и доступными Cargo dependencies:

```sh
python3 probe_relative_bundle.py --core /path/Proteus-core --modules /path/Proteus-modules --output /path/new-relative-fixture
python3 probe_installer_snapshot.py --core /path/Proteus-core --output /path/new-snapshot-fixture
```

Output-каталоги должны быть новыми. Скрипты используют локальные repo HEAD и реальные offline Cargo builds; не запускают реальных моделей, не читают secrets и задают изолированные HOME/config/runtime.
