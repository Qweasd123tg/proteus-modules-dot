# Proteus: профили установки и потерянное выборочное обновление

2026-11-13. Две новые функциональные находки, production-код не менялся, публикаций нет.

## Ревизии и метод

`git ls-remote origin refs/heads/main` повторно подтвердил:

- Core `89997df995df7c39b713e16aba216ecb19c8f497`;
- Modules `3270dc0f894eaf4d0360306052b806099b8f5351`;
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`;
- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.

Из Git HEAD взяты неизменённые production `install.sh`, `build_module.py`, `sources.py`, `package.py` обоих производителей, Desktop packaging scripts и все tracked Core configs. Настоящие subprocess CLI, Cargo/rustc offline, Git, filesystem copy/rename. Для скорости вместо тяжёлых приложений используются минимальные Rust producers. Ни Cargo, ни filesystem, ни упаковщики не mock-ались. HOME, config/install roots и targets отдельные, реальные данные пользователя не используются.

Повторено четыре раза с чистыми fixture roots. Два последних полных прогона дополнены настоящим Core CLI `inspect topology`, который только читает и разрешает config, без workers, GUI и model calls. Это ранее собранный чистый Core указанного HEAD, SHA256 executable: `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`. Полный Core не пересобирался ради упаковщика.

## 1. P2: CLI installer забывает поставляемый профиль CodeMode

`configs/` документирован как набор поставляемых profiles/fragments/prompts для installer. Modules README для CodeMode предлагает установить пакет и выбрать поставляемый opt-in `code-mode.config.toml`. Но hardcoded список `install_config` в Core не содержит этого файла.

### Воспроизведённая цепочка

1. Чистый HOME/config root, исходные актуальные tracked configs, неизменённый `install.sh`. Реальный Cargo собирает минимальный Core и независимые model-pack/code-mode fixture binaries; настоящие `build_module.py` и Modules `package.py` устанавливают их.
2. CLI installer возвращает **0**, `current/bin/proteus-code-mode-module` существует и запускается. Все остальные tracked `*.config.toml` установлены. Единственный отсутствующий файл: **`code-mode.config.toml`**.
3. Повторная штатная установка снова возвращает **0**, но не добавляет профиль.
4. Настоящий Core CLI с этим config root: `--config code-mode inspect topology --format json` возвращает **1**: `config name 'code-mode' was not found`.
5. Положительный контроль: неизменённый Desktop portable launcher копирует **тот же** набор tracked configs в отдельный чистый config root. SHA256 CodeMode profile совпадает с исходником. Настоящий Core CLI с этим config root возвращает **0**, topology содержит `"profile": "code-mode"`.

Это не доказательство ошибки самого движка CodeMode и не сбой запуска настоящего worker: здесь подтверждены доставка и named resolution. Полный code-mode worker в installer fixture заменён маленьким executable; его presence проверяет доставку, не функциональность JavaScript. Explicit path к исходному profile остаётся рабочим обходом. Пользователь, ранее запускавший portable, может не заметить ошибку, потому что тот уже установил файл в общий config-dir.

Источники:
- [Core install.sh:117–125](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/install.sh#L117-L125): закрытый список named configs;
- [Core configs/code-mode.config.toml](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/configs/code-mode.config.toml): существующий поставляемый профиль;
- [Core configuration.md:130–150](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/configuration.md#L130-L150): назначение configs и правила установки;
- [Modules CodeMode README](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/code-mode/README.md): установка пакета и выбор поставляемого профиля;
- [Desktop launcher:18–30](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable/proteus-native#L18-L30): перенос полного набора configs;
- [Core config/loading.rs:298–330](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/loading.rs#L298-L330): named config resolution не ищет произвольный checkout.

Направление исправления: добавить профиль в installer и regression, сопоставляющий поставляемые profiles и результат чистой/повторной установки. Не перезаписывать existing user named configs.

## 2. P2: параллельные portable updates разных компонентов молча теряют уже успешное обновление

Каждый `portable.py` читает metadata и копирует готовый `build/Proteus` в свою stage **до** сборки. Между чтением базы и публикацией нет общей блокировки или проверки generation. `publish()` заменяет весь bundle, поэтому отдельная поздняя операция возвращает невыбранные компоненты к состоянию своей старой stage.

### Воспроизведённая цепочка

Используется обычный default base `build/Proteus`, без внешнего `--base` и без symlinks. Оба обновления запускались настоящими отдельными CLI-процессами.

1. Исходная portable содержит Core A, Extensions A.
2. Запущен `portable.py --components core --no-archive`. Stage уже создана; настоящий Core Cargo build временно ждёт test-only barrier в минимальном `build.rs`.
3. Пока Core собирается, другой CLI выполняет `--components extensions --no-archive`. Настоящие Extensions `package.py` + Cargo строят B. Команда завершается **0**. Исполняемый файл из опубликованного bundle печатает **EXTENSION-B**; metadata указывает действительный fixture Git commit B.
4. Барьер Core отпущен. Первый CLI завершает сборку/валидацию/публикацию и возвращает **0**. Core теперь B, но тот же Extensions executable снова печатает **EXTENSION-A**. Его source commit также откатился на A.
5. Положительный контроль: те же команды, sources и producers, выполненные последовательно, сохраняют **Core B + Extensions B**.

Это реальный откат содержимого уже успешно установленной другой группы, не только устаревший provenance. Ни одна команда не сообщила конфликт. `Proteus.previous` не помогает: второй update успевает закончить publication/cleanup до публикации первого. Задержка build script лишь детерминирует обычное пересечение двух сборок; production scripts не перехватывались и не исправлялись.

Источники:
- [Desktop portable.py:163–188](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable.py#L163-L188): ранние read/copy base, сборка и безусловный publish;
- [portable_state.py:133–148](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable_state.py#L133-L148): rollback rename не является serialization/generation check;
- [BUILDING.md](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/BUILDING.md): выбранные компоненты обновляются, остальные переносятся из готовой базы.

Условие: пересекающиеся процессы, обновляющие один destination. Однопроцессная последовательная работа исправна. Для одного явно общего запуска `--components core extensions` эта находка неприменима; отдельная известная проблема проверки их протокола здесь не исследуется.

Направление исправления: serialize операции от чтения/копирования default base до publication либо проверять generation базы непосредственно перед publish под общей блокировкой и явно отклонять stale stage. Блокировка только вокруг двух rename не предотвращает потерю уже опубликованного обновления.

## Проверки и воспроизведение

- Desktop `test_release_cargo_binary.py`: **39 passed**.
- Modules `tests/test_package.py`: **13 passed**.
- Изолированный сценарий: четыре повтора, последние два с настоящим read-only Core topology check.
- Production изменения, commit/push/PR, полный release gate, native GUI и live providers не выполнялись.
- Старые symlink base, stale single-package provenance, relative install root, partial config failure, host drift, Cargo target path и systemd limiter повторно не считаются. Для fixture использован документированный `PROTEUS_BUILD_SHARE=100`.

```sh
python3 probe_release_manifests.py \
  --core /path/Proteus-core --modules /path/Proteus-modules \
  --desktop /path/Proteus-desktop --extensions /path/Proteus-desktop-extensions \
  --core-binary /path/existing/proteus \
  --output /path/new-empty-fixture-directory
```

Нужны Cargo/rustc на PATH. Cargo работает offline, tiny producers не требуют сторонних crates. `--core-binary` необязателен; без него проверяются installer и filesystem/launcher, но не настоящий Core named resolution. В архив входят только reproducer, report, компактные logs/results последних двух прогонов и focused test logs, без binaries, targets или checkout.
