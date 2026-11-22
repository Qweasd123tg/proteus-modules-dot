# Точный Proteus M200: исходники и локальная сборка

Этот рецепт собирает только проверенный набор из **200 изменений по #442 включительно**: Core 38, Modules 56, Desktop 60, Extensions 46. #443, #444, незачтённые и заменённые варианты не входят. Слияние записей с патчами в репозиторий-приёмник не применяет сами изменения к четырём продуктовым репозиториям.

## 1. Подготовить чистые checkout

Используйте отдельную пустую папку, не меняя свой рабочий checkout. В примере `RECIPE` указывает на каталог с этим README и скриптом. `DELIVERY_COMMIT` возьмите из подтверждённого результата публикации: в этом коммите все опубликованные файлы должны уже находиться в дереве репозитория-приёмника. Произвольный текущий `main` или старый основной коммит не подставляйте.

```bash
git clone https://github.com/Qweasd123tg/proteus-modules-dot.git delivery

git clone --no-checkout https://github.com/Proteus-harness/Proteus-core.git core
git clone --no-checkout https://github.com/Proteus-harness/Proteus-modules.git modules
git clone --no-checkout https://github.com/Proteus-harness/Proteus-desktop.git desktop
git clone --no-checkout https://github.com/Proteus-harness/Proteus-desktop-extensions.git extensions

git -C core -c core.autocrlf=false switch --detach 32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f
git -C modules -c core.autocrlf=false switch --detach 9469e3b12529d08b1f4a76882693e2065e842c51
git -C desktop -c core.autocrlf=false switch --detach b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
git -C extensions -c core.autocrlf=false switch --detach 892f627570369ed60d7205eb0d351c753ec4305f
```

## 2. Проверить и применить

`m200.json` задаёт порядок от 1 до 200, точные пути опубликованных файлов, Git blob SHA-1, SHA-256, выбранный вариант и его зависимости. 146 файлов уже были в основном дереве, ещё 50 пришли из #393–442; все 196 скрипт читает из указанного локального коммита. Четыре точные интеграционные версии (#244, #282, #303, #311), которых не было в опубликованном виде, лежат в `local-variants/`. Отдельно там сохранены только регрессионные тесты #247: они наносятся после 50-го изменения, но в эти 200 не засчитываются. Для восьми пар выбирается ровно `cumulative.patch`: #396, #409, #414, #418, #424, #425, #426, #432. Их `source.patch` не накладывайте.

```bash
set -e -o pipefail
(cd "$RECIPE" && sha256sum -c SHA256SUMS)
python3 "$RECIPE/apply-m200.py" --delivery ./delivery --delivery-commit "$DELIVERY_COMMIT" \
  --core ./core --modules ./modules --desktop ./desktop --extensions ./extensions --check-only
python3 "$RECIPE/apply-m200.py" --delivery ./delivery --delivery-commit "$DELIVERY_COMMIT" \
  --core ./core --modules ./modules --desktop ./desktop --extensions ./extensions | tee m200-trees.jsonl
```

`--check-only` читает и проверяет **все** байты заранее, но не изменяет checkout и не имитирует зависимые патчи. При применении скрипт делает `git apply --check` перед каждым патчем и останавливается при первом несовпадении. Уже применённые изменения останутся в одноразовых checkout. Чтобы повторить, заново создайте **только эти временные checkout** на исходных коммитах; не делайте reset или clean в своём рабочем репозитории. Контрольная точка после 150 патчей сверяет четыре дерева и Cargo.lock с зафиксированным M150. После #442 скрипт сверяет известные итоговые деревья Core, Modules и Extensions; для Desktop выводит фактический хеш, не предполагая ожидаемый. Скрипт не подключается к сети, не создаёт коммитов, не запускает сборку или тесты и не отправляет изменений. Если необходимо коммитить, делайте это отдельно после проверки результата.

## 3. Собрать и проверить на Linux

Это команды из документации четырёх закреплённых проектов, а не отчёт об уже выполненном полном прогоне. Нужны Rust 1.95.0, C-компилятор, Python 3.11+ и LLD. Для полного gate Modules также нужен Node.js 22.19+ с npm; закреплённые зависимости могут загружаться при первом запуске. Для нативного Desktop на Fedora: `libxcb-devel libxkbcommon-devel libxkbcommon-x11-devel fontconfig-devel freetype-devel`. Не заменяйте Cargo.lock и не объединяйте target четырёх независимых воркспейсов.

```bash
(cd core && cargo build --release --locked -p proteus-core && python3 scripts/test.py full)
(cd modules && cargo build --release --locked && python3 scripts/test.py full)
(cd extensions && cargo build --release --locked --workspace && cargo test --locked --workspace && \
  python3 -m unittest discover -s tests -p 'test_*.py')
(cd desktop && python3 scripts/test.py -p proteus-tabs --lib)
(cd desktop && set -o pipefail && \
  ZIG="$(python3 scripts/terminal_toolchain.py |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["ZIG"])')" && \
  ZIG="$ZIG" cargo build --release --locked -p proteus-native && \
  ZIG="$ZIG" python3 scripts/test.py)
```

Запускайте блоки последовательно. Desktop без GUI/системных зависимостей может пройти проверку `proteus-tabs`, но это не нативный gate. Готовый исполняемый файл Desktop после успешной нативной сборки: `desktop/target/release/proteus-native`.
