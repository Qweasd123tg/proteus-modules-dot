# Proteus: согласованность выборочных установок

2026-11-13. Два новых наблюдения, без изменений production-кода и публикации.

## Ревизии и метод

Удалённый `refs/heads/main` повторно сверен через `git ls-remote`:
- Core `89997df995df7c39b713e16aba216ecb19c8f497`;
- Modules `3270dc0f894eaf4d0360306052b806099b8f5351`;
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`.

Проверялись неизменённые Python-скрипты, полученные через `git show HEAD:path`, настоящие CLI subprocesses, Cargo/rustc, Git commits, копирование, SHA-256 и публикация. Для быстрого изолированного эксперимента полноценные приложения заменены минимальными Core/Modules Rust binaries. Mock компилятора, package producer, файлового копирования и rename не использовался. HOME, target и поставки отдельные, реальных credentials/model providers нет.

Rust/Cargo 1.95.0, Linux x86_64, Python 3.12.14. Для изолированного fixture выбран документированный `PROTEUS_BUILD_SHARE=100`: default limiter в этой среде не может подключиться к systemd user bus. Это уже известное ограничение, не новая находка.

## 1. P2, условный: stage следует за symlink и изменяет исходную базу до публикации

`portable.py --base BASE --components core --no-archive` должен создавать результат в Desktop/build/Proteus, не изменять внешний BASE. Начальная проверка принимает исполняемый `BASE/bin/proteus`, даже если это абсолютный symlink на отдельный рабочий executable. Stage копируется с `symlinks=True`; затем `install_file` делает `shutil.copy2` поверх этой ссылки. В результате копирование идёт в исходный executable, а не в изолированную stage.

### Подтверждённые сценарии

1. Внешняя база запускает `BASE-A`, текущая выходная поставка тоже A.
2. Реальный Cargo собирает Core B. Последующая реальная проверка notices завершается `has no license file` (fixture Core checkout сознательно без LICENSE).
3. CLI возвращает **1**; выходная поставка остаётся A. Но внешний `BASE/bin/proteus` уже запускает **CORE-B**. Его release metadata осталась прежней.
4. Положительный контроль с обычным файлом вместо symlink: та же ошибка возвращает 1, исходная база остаётся A.
5. После добавления правильного LICENSE успешный вариант возвращает **0**, но также изменяет внешний BASE. Новый опубликованный runtime сохраняет ссылку на общий исходный executable, а не самостоятельную копию.

Это не утверждение о стандартной portable, где такие binaries обычные файлы. Условие: пользовательский `--base` содержит принимаемый валидатором symlink на writable executable. Такой BASE следует либо отвергать до работы, либо материализовать независимым образом. Проблема функциональная: нарушены изоляция stage, сохранность базы при ошибке и независимость результата.

Источники:
- [Desktop portable.py:39–43](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable.py#L39-L43), copy2 следует по target symlink;
- [portable.py:60–70](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable.py#L60-L70), Core install;
- [portable.py:180–188](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable.py#L180-L188), копирование stage с сохранением ссылок;
- [portable_state.py:15–46](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable_state.py#L15-L46), текущая проверка базы;
- [BUILDING.md](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/BUILDING.md), результат не поверх внешнего BASE и сохранение базы при ошибке.

Направление исправления: определить политику symlink для готового bundle; проверять/материализовать весь выбранный destination path до writes, не только конечный файл. Простая смена copy2 на rename решит конечную ссылку, но не symlink родительского каталога.

## 2. P3: штатное обновление одного модуля оставляет неверный release provenance

Документированная команда Modules `package.py --package demo --install BASE` заменяет binary/module metadata, но не инвалидирует и не обновляет верхний `share/release-sources.json`.

### Подтверждённая цепочка

1. Настоящий Git commit A и настоящая сборка MODULE-A; готовая база содержит соответствующие Modules commit A и binary_sha256 A.
2. Новый Git commit B меняет исполняемое содержимое, version/exports остаются прежними, как при обычной локальной разработке. Реальная `--install` строит и устанавливает **MODULE-B**.
3. `module.json.sha256` правильно указывает на B, а верхняя запись остаётся побайтно A.
4. Desktop `--reuse-binaries --base BASE --no-archive` возвращает **0** и распространяет MODULE-B вместе с **binary_sha256 A и Modules commit A**. Начальная/финальная проверки не замечают противоречия.
5. Последующее `--components core` тоже успешно: общий binary_sha256 пересчитывается и становится B, но источник Modules по-прежнему объявлен commit A, без per-package override.

Это не повреждение установленного executable: B запускается, его собственная checksum верна. Ошибка в данных о составе поставки, которая воспроизводится штатными командами и мешает воспроизведению/debug релиза. Не утверждается обход release.assets или CI: официальный release gate здесь не запускался.

Источники:
- [Modules package.py:318–327](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/package.py#L318-L327), install без верхней provenance;
- [Modules README](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/README.md), штатная выборочная установка;
- [Desktop portable.py:99–116](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable.py#L99-L116), сохранение источников невыбранных групп;
- [portable.py:180–188](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable.py#L180-L188), reuse копирует запись целиком;
- [portable_state.py:15–46](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/scripts/portable_state.py#L15-L46), записи hash/provenance не сверяются с байтами.

Направление исправления: для single-package update явно обновлять/инвалидировать provenance выбранного пакета и общий digest, не присваивая новый commit всему набору других Modules. На границе portable проверять согласованность recorded bytes и уметь сообщать local/unknown provenance вместо ложного exact source.

## Проверки и повторение

- `scripts/test_release_cargo_binary.py`: **39 passed**.
- Modules `tests/test_package.py`: **13 passed**.
- Полный fixture повторён с чистыми каталогами дважды; assertions подтверждают наблюдаемые дефекты, а не исправление.
- Скрипт и команды не меняют исходные репозитории. Полный Core/Desktop runtime gate, GUI, model evaluations, macOS/Windows не проверялись.
- Известные relative bundle, partial config publication, host snapshot drift, sdk target и systemd limiter повторно не считаются.

```sh
python3 probe_install_consistency.py \
  --desktop /path/Proteus-desktop \
  --modules /path/Proteus-modules \
  --output /path/new-empty-fixture-directory
```

Нужны Cargo/rustc на PATH; Cargo работает offline, fixture не имеет сторонних dependencies. Output должен ещё не существовать. `results.json` сохраняет исходные SHA, source hashes, состояния до/после; `commands.log` содержит реальные exit codes. В архиве только reproducer, report, компактные JSON/log evidence и логи focused tests, без target/binaries/checkout.
