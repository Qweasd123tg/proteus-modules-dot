# Повтор A/B AppServer на Linux

Используйте чистые локальные копии Core и Modules с указанными в главном README коммитами.
В каталоге этого README выполните `R9_CASES=100 bash reproduce.sh /path/Core /path/Modules /path/new-fixture` (нужны Cargo 1.95 и lld). Скрипт забирает точные исходники указанных commits в отдельный каталог, добавляет синтетический тест и собирает диагностический Core. Это AppServer с настоящей обработкой хода, не сетевой тест провайдера: модуль модели локальный reference fixture. Исключена регистрация остальных unit-тестов для экономии памяти при компиляции; рабочие функции не подменяются.

Для двух сопоставимых storage worker-бинарников создайте временную копию Core на checkout `9bb1e06a3cb5773b446b4ab6d5ae43d8cf04d81c`. В свежей копии Modules на `2c2cee47ea76df12c6e208839594e32470a2c3f1`:

```sh
p=/absolute/path/to/pinned-core-copy
RUSTFLAGS='-C debuginfo=0' CARGO_BUILD_JOBS=1 CARGO_INCREMENTAL=0 cargo \
  --config "patch.'https://github.com/Proteus-harness/Proteus-core.git'.proteus-contracts.path='$p/crates/proteus-contracts'" \
  --config "patch.'https://github.com/Proteus-harness/Proteus-core.git'.proteus-session-semantics.path='$p/crates/proteus-session-semantics'" \
  build --release -p proteus-session-storage-module
```

Временный Cargo.lock обновится на локальную подстановку (не переносите его в upstream). Сохраните `target/release/proteus-session-storage-module` как `stock-worker`; примените core-патч в копии pinned-core; повторите ту же сборку и отдельно сохраните `candidate-worker`. Строго тот же worker нужен и на наполнении, и на измеряемой части отдельной пары.

Затем из каталога этого README, подставив пути:

```sh
mkdir -p /path/results /path/fixtures
TMPDIR=/path/fixtures python3 run.py /path/results/50000-stock-a 50000 \
  /path/new-fixture/core/target/release/deps/proteus_core-HASH \
  /path/new-fixture/modules/target/debug/proteus-reference-module \
  /path/stock-worker /path/new-fixture/core --cpu 2
# Повторите с 50000-candidate-a, 50000-candidate-b, 50000-stock-b.
# Указывайте один и тот же доступный CPU.
python3 summarize.py /path/results
```

`CASE` приходит непосредственно перед началом timed send. Метки wire используют монотонные часы одного хоста; их фиксирует прокси, а не рабочий код. Прокси не меняет JSON и не пишет тексты; его собственная стоимость включена в сопоставимые A/B. Подготовка/launch измерены отдельно и не входят в send. Время до записи здесь считается до первого запроса commit(`turn_opened`), не до ответа на него. Сравнение не гарантирует такую задержку на чужой машине или с другой структурой архива.

## Настройки этого прогона (R11)

Версия run.py из этого архива принудительно использует R9_FRESH_STORAGE=1: после наполнения тот же тест закрывает первый storage client и создаёт второй. Выполните одинаковую команду для 100, 50000, 100000, 125000 (соответствующие файлы — в raw/), по одному процессу и по одному размеру за запуск. Состояние ОС не сбрасывается. R9_CASES=100 с самостоятельным reproduce.sh нужен для сборки/проверки фикстуры, а не для сбора сырых трасс R11. В основной команде укажите отдельный каталог результата, существующий родитель и один доступный CPU для обеих сборок.

После завершения:
  python3 verify_cold.py /path/results/100000-stock-a /path/results/100000-candidate-a
  python3 cold-wire.py /path/results/100000-stock-a /path/results/100000-candidate-a

Проверка cold fixture проверяет наличие отдельного нового процесса, отсутствие кеш-операций при наполнении и публикацию готового head до отправки сообщения. Таймеры сравниваются внутри одного стенда с одинаковым прозрачным stdio-прокси. Скрипт summarize.py из предыдущей инструкции не нужен; вместо него здесь cold-wire.py и verify_cold.py.

## Проверка прокрутки и старой ревизии

Для варианта candidate применить core-cold-packs.patch к исходникам Core до компиляции.
После instrument.py выполнить python3 install.py /path/to/instrumented-Core (затем
strip-tests.py либо перед этим, либо после; расширение работает внутри исходного теста).
Прогоните штатный run.py со значением окружения R12_PACK_SMOKE=1 и числом сообщений 3003.
Затем python3 verify-smoke.py /path/to/run-output. В замерах производительности R12_PACK_SMOKE
должна быть выключена. При переносе exact A/B используйте один JSONL worker с R10 в обеих сборках.
