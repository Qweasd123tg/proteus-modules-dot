# Proteus Core: однократная сериализация отсутствующих строк read-cache

Source-only кандидат для Core `befd30516aefa6f0a0ad5db9924ad4957160b8dc`.
Patch 06 самостоятельный, меняет три Rust-файла; формат хранения, API,
настройки и постоянное состояние не меняются. Независимое source-review
не выявило блокирующего дефекта; подробности и ограничения — в REVIEW.md.

## Изменение

Тот же SELECT сначала ищет строку. Если ключ отсутствует, пропускается
предварительная JSON-сериализация в hash: payload сериализуется один раз
ограниченным writer, затем хешируются именно записываемые bytes. Нового
EXISTS-запроса, cache или dirty API нет. Внутренняя дыра определяется реальным
поиском ключа, не длиной таблицы или header.

Для существующих строк сохраняются streaming hash, проверка фактического
payload/checksum и исправление повреждений. Неизменённые строки уже раньше
не выделяли новый полный Rust payload-буфер и не переписывались SQL; это не
новая заслуга patch. Число Serialize-вызовов: отсутствующая строка 2 → 1,
неизменённая существующая 1, изменённая/повреждённая существующая 2 при успешном
первом вызове. Единственная заявленная экономия — первый encode/hash для
действительно отсутствующих ключей; замеров времени, RSS и throughput нет.

## Семантические и ресурсные оговорки

Это не универсальная эквивалентность для произвольного Serialize. Stateful
serializer может вернуть разные bytes при первом и втором вызовах либо упасть
только при втором: для отсутствующего ключа сохраняемое значение или успешность
могут измениться. Ошибка SQL до callback или неверная позиция теперь могут вообще
не вызвать serializer (раньше один вызов). Граница ошибки остаётся None;
ошибка supplier не превращается в mismatch/повторную попытку.
Целевой scope — фактические read-model DTO conversation/transcript/context,
usage/header/source. Независимый поиск по ранее проверенной карте 589 активных
исходников установил save.rs как единственный именованный production-потребитель
Updater; это focused named-consumer coverage с повторным использованием прежней
blob-проверки, не новая полная перепроверка дерева и не доказательство свойств
всех возможных generic Serialize.

Для oversized или поздно падающей **отсутствующей** строки теперь возможно
выделение принятого префикса Vec до отказа; прежний streaming precheck отвергал
её без payload Vec. serialize_bounded проверяет chunk перед extend_from_slice
и ограничивает сериализованную длину одной строки 64 MiB. Рост capacity и
allocator overhead этим не ограничены: это не точный предел RAM/RSS и не общее
снижение памяти. Общего бюджета bytes всей базы здесь не было и не добавлено;
лимит 8192 blobs относится к fingerprint, а не суммарному payload. Для валидных
новых строк итоговый Vec требовался и раньше. Existing-row precheck не меняется.

Transaction, source recheck, COMMIT, locks, truncate, common-prefix и replacement
сохраняются. Возврат None из row сам по себе не отравляет Updater и не выполняет
немедленный rollback. Проверенный save caller распространяет ошибку, затем Drop
закрывает транзакцию до replacement, как и раньше.

## Проверки и оставшиеся ограничения

Добавлены пять тестовых сценариев: missing tail/внутренняя дыра;
число вызовов и результат для unchanged/changed/corrupt; oversized existing/missing
с rollback предыдущей записи; явная ошибка Serialize; ошибка SQL preparation
без вызова hash supplier. Тесты **не запускались**. Existing rollback/reader tests
сохранены. Новые тесты не покрывают exact-limit acceptance, checksum type/length,
stateful changing-value, save-level common-prefix или все ошибки query/step.

Выполнены статические проверки: Git blob identities исходников, строгие
forward/reverse git apply, фактическое применение и обратное применение с точным
сравнением bytes, diff whitespace, установленный Rust 1.95 rustfmt parse/format
и --check, SHA-256 manifest. Компиляция, Cargo, project scripts, runtime, build,
CI и benchmarks не выполнялись. Adoption требует разрешённых применимых
type-check/test evidence; это source proposal, не доказанная runtime-готовность.

SOURCES.json фиксирует immutable upstream identities; SHA256SUMS — файлы пакета.
Внешних изменений эта рабочая задача не выполняла.
