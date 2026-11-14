# CLI install → Desktop catalog: установленный модуль ошибочно регистрируется заново

2026-11-13. **Новая подтверждённая P2-находка** в обнаружении установленного backend и построении запроса обновления. Production не менялся, ничего не опубликовано.

## Что ломается

Core `install.sh` создаёт настоящий shell launcher `~/.local/bin/proteus`, который запускает `~/.proteus/current/proteus`; metadata модулей находится в `~/.proteus/current/share/modules`. Desktop поддерживает backend из `PROTEUS_BIN` либо найденный `proteus` на PATH.

Но `Inventory::local` только canonicalize-ит путь launcher. Shell script не является symlink, поэтому обнаружение ищет metadata в `~/.local/share/modules`, не в активном snapshot. Реально установленный пакет пропадает из inventory.

Если пакет ещё не обновлялся из Desktop catalog и у него нет отдельного receipt, UI использует inventory для обнаружения bundled replacement. Из-за пустого inventory получается `component_packages.replace=[]`. При обновлении уже подключённого `memory-pack` настоящий Core отвечает:

```text
HTTP 400
component already exists: memory-pack
```

То есть штатная CLI-установка запускается, её модуль работает, но первое обновление этого модуля из Desktop catalog не подключается. Это не ошибка Cargo, не пропавший executable и не отказ протокола worker. Старый профиль остаётся исправным. В данном тесте потери данных нет.

## Проверенная цепочка

1. Изолированный HOME с раскладкой `install.sh`: `.local/bin/proteus`, `.proteus/current → releases/fixture`, Core в snapshot, модуль в `bin`, metadata в `share/modules`.
2. Текст launcher извлечён **дословно из текущего `install.sh`**. Вместо повторной сборки installer fixture использованы уже собранные настоящие Core и `proteus-memory-pack-module`, скопированные в эту раскладку. Сам `install.sh` в этом проходе не запускался.
3. Настоящий Core запускается через этот launcher. HTTP слушает только loopback, профиль использует bare `proteus-memory-pack-module`, как поставляемый Codex fragment. GET `/config/builder` возвращает 200 и реальный schema/tool-pack этого модуля.
4. Выполняются неизменённая `inventory.rs`, извлечённая функция `backend::proteus_binary` и дословный блок выбора replacements из `ui/settings/catalog/component.rs`.
5. Два входа дают одинаковую ошибку: явный `PROTEUS_BIN` на CLI launcher и отсутствие `PROTEUS_BIN` с `.local/bin` на PATH. Inventory пуст, replace пуст.
6. Получившийся payload отправлен настоящему Core `/config/builder`: **400, component already exists**. Bytes исходного profile не изменились.
7. Положительный контроль меняет **только вход обнаружения inventory** на прямой snapshot executable или `current/proteus`. Тот же snapshot, профиль, пакет и запущенный Core: inventory находит metadata, replace содержит `memory-pack` с проверяемым expected_executable. Payload принимается с **200**, command компонента переключается на новый установленный путь.

Два последних полных прогона: `run-1794580096265664976`, `run-1794580123588475346` (точный последний каталог также указан в `run-5.log`). В последнем дополнительно проверен default PATH fallback без `PROTEUS_BIN`. Более ранние подготовительные прогоны не нужны для воспроизведения.

`expected_invariant.py` формулирует исправленный контракт и на текущих данных ожидаемо завершается **1**: CLI-installed module must be visible through its supported backend launcher. Это намеренно красный regression, не неожиданная ошибка стенда.

## Исходники и HEAD

Повторная сверка main через GitHub fetch_commit:
- Core `89997df995df7c39b713e16aba216ecb19c8f497`;
- Modules `3270dc0f894eaf4d0360306052b806099b8f5351`;
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`;
- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.

Root cause и связанная граница:
- [Core install.sh, launcher и snapshot](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/install.sh#L43-L73).
- [Desktop backend selection](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/backend.rs#L159-L168).
- [Inventory: local и read_modules](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/catalog/inventory.rs#L31-L95).
- [Inventory: resolve_binary](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/catalog/inventory.rs#L147-L160).
- [Desktop: bundled.is_some необходимо для replacement](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/catalog/component.rs#L33-L76).
- [Core: пустой replace означает новую регистрацию](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder/component_packages.rs#L44-L53).
- [Штатный профиль memory-pack с bare command](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/configs/fragments/codex-components.toml#L18-L22).

Core binary SHA256 `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`.
Memory binary SHA256 `85ca5e582712e1f8ece3e6358e96c7a1f71325f571814d598ca9d46af83e9730`.
Production-source SHA256 записаны в `source-hashes.json`.

## Границы доказательства

Настоящие: filesystem, shell launcher, Core HTTP/profile transaction, JSONL memory worker handshake/schema, exact inventory and replacement-selection logic. Synthetic: малый model-free workflow только для профиля и data-only substitutes GUI snapshot/receipt types в Rust projection. Extension discovery не задействован и возвращает пустые списки fixture. `make_probe.py` показывает все границы projection; проверяемый selection block не переписывается.

Не выполнялись: native GUI/click, Git download/build модуля из каталога, полный `install.sh`, полный Core/Desktop gate, модельные вызовы. «Установка из каталога end-to-end в GUI» не заявляется: доказана цепочка принятия решения UI → настоящий Core endpoint после подготовки пакета. Известные parallel portable lost update, code-mode omission и прошлые packaging issues сюда не включены.

Положительный контроль не означает, что достаточно поменять только PROTEUS_BIN при обычном прямом запуске: для такого запуска должен оставаться корректный PATH модулей. В тесте работающий Core в обоих случаях уже стартовал через официальный wrapper; менялся только input обнаружения на стороне Desktop.

## Направление исправления

Дать Desktop надёжный runtime/package root или фактический resolved executable от **активного backend**, а не выводить layout только из пути launcher. Поддержать штатный CLI snapshot, portable и явно заданный backend. Не подменять любую внешнюю установку содержимым `PROTEUS_HOME` лишь по совпадению имени пакета. Сохранить проверку expected_executable Core: её ослабление ошибку inventory не исправляет.

Regression: install.sh-style wrapper + bare component command + отсутствие catalog receipt → inventory видит установленный пакет → update формирует explicit replacement → save успешен, без второй регистрации. Контроли: portable/direct snapshot, current symlink, unrelated custom backend.

## Воспроизведение

```sh
python3 make_probe.py --desktop /path/Proteus-desktop
CARGO_TARGET_DIR="$PWD/target" cargo build --offline --manifest-path probe/Cargo.toml
python3 repro.py \
  --core /path/Proteus-core --modules /path/Proteus-modules \
  --core-binary /path/built/proteus \
  --module-binary /path/built/proteus-memory-pack-module
python3 expected_invariant.py run-.../results.json  # expected 1 before fix
```

Для offline build нужны cached anyhow/serde/serde_json; lockfile включён. Артефакт не содержит binaries, Cargo targets, user data или credentials. В HTTP используется только синтетический loopback token fixture.
