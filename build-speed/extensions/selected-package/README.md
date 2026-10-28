# Выборочная сборка одного расширения

Патч к `Proteus-harness/Proteus-desktop-extensions` на ревизии
`3361fc1650c4ac6f167c3e48a0fba8980a5c9038`. Исходный репозиторий здесь не
изменяется; доставка — отдельный draft PR только в `proteus-modules-dot`.
Upstream author: Proteus Project. Исходные тексты и лицензии сохраняют
upstream provenance; полные `LICENSE-GPL` и `LICENSE-APACHE` этой ревизии
включены в `source-bundle.json`. Лицензия harness не перелицензирует эти данные.

## Изменение

После отдельного применения патча к указанной ревизии:

```bash
python3 package.py --package quota                 # только dist/quota.zip
python3 package.py --package quota --output /tmp/extensions
python3 package.py --package quota --dev           # только packages/quota/bin/quota
```

Это команды **использования будущего патча**, не команды текущей проверки.
Они собирают Cargo package `extension-quota`, bin `quota`, плюс необходимые
зависимости/SDK. Core, Desktop и соседние extensions не собираются. Готовый
ZIP устанавливается существующим интерфейсом «Клиент → Расширения» без
пересборки клиента; новый установщик каталогов не добавляется.

Селектор принимает ID папки (`quota`), а не Cargo имя (`extension-quota`).
Повторный `--package`, комбинация с `--bundle` и `--dev --output` отвергаются
до Cargo. Без селектора старые режимы остаются прежними: все extensions,
release, прежние `binaries/place/assemble/develop`. В том числе старое
угадывание target path **в полном режиме** намеренно не исправляется этим
узким патчем. Исторический read-only planner и full delivery gates не меняются.
Этот реализованный интерфейс заменяет только прежнее предложение интерфейса
в `build-speed/desktop/extension-selection-design.md`.

Выбранный artifact определяется по точному Cargo manifest path, имени bin,
kind, non-test profile и executable из успешного Cargo JSON stream. Нужны
нулевой exit и ровно один boolean-success build-finished; stale-path fallback
нет. Compiler diagnostics сохраняются. ZIP и dev binary публикуются целым
файлом через temporary на том же filesystem и replace; ошибка до replace
оставляет старые байты. Это атомарная видимость rename, не fsync/crash durability.
Существующий Desktop installer использует validation, staging и best-effort
rollback; строгая crash-atomic замена непустого каталога здесь не заявляется.

## Что проверено и что не проверено

`source-bundle.json` содержит точные upstream bytes `package.py`, README,
workspace Cargo.toml и всех 11 пар Cargo/extension manifests. SHA-256 и Git
blob SHA проверяются. Unified diff применяется чистым Python без fuzzy offsets;
результат сверяется с digest именно проверенного candidate и полного набора
37 authored tests. Четыре старых helper AST должны совпадать с baseline.

```bash
python3 -B -m unittest discover -s build-speed/extensions/selected-package -p test_check.py -v
python3 -I -B build-speed/extensions/selected-package/check.py --output /tmp/selected-package-evidence
```

Требуется Python 3.11+ для checker (`tomllib`), без внешних Python packages.
Проверка офлайн: 10 negative reconstruction controls и 37 fixture/mock controls;
импорт candidate и тесты окружены запретом настоящих subprocess/network calls.
Все test assets — маленькие синтетические байты; бинарники не исполняются.
Это проверка Python orchestration/selection/rollback, **не** реальная сборка
Cargo, не проверка runtime compatibility или relocation готового ZIP.
Такие проверки, а также применение к upstream, остаются отдельным этапом.

Workflow запускается только push в `ci/extension-selected-package-20261028`
с изменением этой папки или самого workflow. PR trigger отсутствует. Он
checkout-ит только harness, не upstream; не устанавливает Rust, не запускает
Cargo, portable, Core/Desktop/extensions, apt или релизную сборку.
