# Один буфер для записи SHA-256 в session-storage

База: [Proteus-modules@9469e3b](https://github.com/Proteus-harness/Proteus-modules/commit/9469e3b12529d08b1f4a76882693e2065e842c51), Core dependency pin `0c1b7572313230e5d123e95c722e1258a2e9ecd6`. Проверенный локальный commit `3f66ba9a70d103b0d9048e137ab348876e943be3`. SHA-256 `source.patch`: `fe51f50d99b4a0217634406c2f943351863e4e74f6e43da697bb30a83410bee5`.

Общий `digest_hex` и пять мест в JSONL/SQLite строили отдельную строку для каждого байта уже вычисленного digest. Теперь шестнадцатеричные цифры записываются в одну строку с заранее известной длиной; все пути вызывают одну реализацию. Это не изменение алгоритма SHA-256 или формата: остаются 64 строчных символа, включая нули. Не добавлены зависимости; не меняются байты входа, выбор префикса, правила валидации, проверки размера и содержимого chunks или порядок I/O.

## Что измерили

Вызовы alloc, alloc_zeroed и realloc на тестовом потоке вокруг обычных функций хранилища. Три прохода после прогрева на каждом варианте; все значения повторились. Запись исходных данных, создание tempdir, сверка с эталоном и печать не измерялись. Одна запись с фиксированными UUID для snapshots; один и тот же детерминированный payload 4 MiB для chunked blob. Для последнего измерялся весь `unpack_expected`, а не отдельная модель стоимости.

| Операция | Вызовы Rust allocator, до → после | Запрошено байт, до → после |
|---|---:|---:|
| Открытие JSONL snapshot без prefix hint | 42 → 8 | 66 625 → 66 321 |
| Открытие SQLite snapshot без prefix hint | 44 → 10 | 985 → 681 |
| Fingerprint прочитанного префикса, любой backend | 35 → 1 | 368 → 64 |
| Полная проверка и распаковка 4 MiB, 98 chunks | 5 709 → 2 343 | 17 856 996 → 17 826 900 |

В последней строке разница в основном по числу мелких выделений: −3 366 вызовов и −30 096 запрошенных байт. Результат не означает экономию 4 MiB, изменение числа хеширований, снижение peak RSS или такое же ускорение открытия Desktop. Внутренние выделения C SQLite не учитываются. В обоих вариантах совпали прочитанная запись и ранее записанный SHA префикса, все 4 MiB распакованного blob, SHA payload и SHA manifest. Дополнительно 4096 входов сравнили с прежним форматированием; две фиксированные известные SHA-256 константы включены в патч.

## Проверки и применение

* Основной патч и вариант поверх [#246](https://github.com/Qweasd123tg/proteus-modules-dot/pull/246) независимо прошли `cargo fmt --all --check`, `git diff --check` и `cargo test --locked --offline -p session-storage -p proteus-session-storage-module -- --test-threads=2`: 64 unit + 2 process, 0 ошибок, 1 существующий ignored perf-test в каждом прогоне. Включены проверки повреждённого журнала, shared chunks, неизменности префикса и terminal reuse.
* Штатный Python runner с общей Cargo metadata в offline-окружении не нашёл Android-only `android_system_properties 0.1.5`, поэтому целевые тесты выполнены через Cargo напрямую с исходным lockfile. Полный workspace не запускался.
* Dev-пакет штатно собран и установлен в изолированный staging: `python3 package.py --profile dev --package session-storage --install /absolute/staging-path`. SHA-256 установленного worker совпал с manifest. Рабочая установка пользователя не затронута.
* Обычно применяйте **только** `source.patch`. Если уже установлен #246 (заимствованное чтение SQLite BLOB), используйте **вместо него** `after-246.patch`: это тот же патч с контекстом SQL EOF после #246, не дополнительная оптимизация и не замена #246. Прямое наложение основного варианта поверх #246 конфликтует по соседним строкам.

## Воспроизведение измерения

В двух чистых checkout базы, в одном до пробы применить `git apply /path/to/source.patch`. Из корня каждого:
```sh
cp /path/to/allocation_probe.rs storage/session-storage/src/digest_probe.rs
printf '\n#[cfg(test)]\nmod digest_probe;\n' >> storage/session-storage/src/lib.rs
cargo test --locked -p session-storage --lib measure_storage_digest_allocations -- --nocapture --test-threads=1
```
Файлы probe не входят в продукт. В `results.csv` сохранены исходные пары счётчиков с fingerprint каждого результата. Blob fixture: 4 194 304 исходных байта, manifest 9140 байт, 98 chunks; SHA-256 оригинала `a6cd70544ef56cab2ba30a5e2a534964706ef9bbe6b767c63cf3d8e86fc044a2`, manifest `83880d3d0daebceebb0f1f5baa6ce37c83154ee34d37cc33b75fd75356b01ca6`.
