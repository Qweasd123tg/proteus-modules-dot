# Независимый review: однократное сравнение model source

**Решение: ACCEPT. Focused native before/after подтверждены логами автора.**

- База Core: `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`.
- Патч: `model-comparison-once.patch`.
- SHA-256 патча: `087eccc2a819bea7b0746316f07c67bf8651a823ccde51ed98acf105d156c819`.
- Независимо выполнен `git apply --check` против чистой базы: PASS.
- Объём: один production-файл, 8 добавленных и 8 удалённых строк; тесты не изменены.

## Проверенные инварианты

У каждого изменённого private writer helper ровно один caller, оба обновлены.
Первое вычисление `model_source_changed` остаётся на прежнем месте и до прежних
проверок формы исходника, поэтому порядок ошибок сохраняется. Между прежними
первым и повторным вычислениями изменяется только локальный parsed document;
`config` и `baseline` неизменны, `await` отсутствует. Сравниваемые
`ProviderProfileConfig` и `ReasoningConfig` содержат обычные owned поля и
используют derived serialization, без interior mutability и побочных эффектов.
Отсутствующий baseline по-прежнему даёт `(true, false)`.

Правила наследования, проверки данных, файловые операции, locks и разрешение
целевого пути не меняются. При существующем baseline в каждом TOML/JSON save
устраняются две повторные сериализации provider-каталогов и одно повторное
сравнение. Это устранение повторной работы по исходникам, не измеренное ускорение.

## Проверки и ограничения

Для observable behavior подходят существующие persistence/load cases:
`model_names` (4), `inline_roles` (5), `instruction_bootstrap` (3),
`provider_inheritance` (3), directory precedence и unmanaged JSON:
всего 17 существующих cases. Этот scope достаточен для локального изменения
повторного model-source comparison; отдельный hook-persistence case не проверяет
новый инвариант и не является условием принятия патча. Тест счётчика вызовов или
новый framework не требуется.

Reviewer прочитал `baseline.log` и `candidate.log` и проверил точное совпадение
17 имён успешно выполненных cases. Baseline: эти 17 cases прошли. Дополнительный hook case
завершился ошибкой в `tests/support/model.rs` из-за отсутствующего
`PROTEUS_TEST_REFERENCE_MODULE`, до config persistence; процесс не запускался.
Поэтому весь первоначальный baseline command не является зелёным. Подставлять
fixture binary или расширять process/build scope ради этого case не нужно.
Candidate: `17 passed; 0 failed; 0 ignored; 0 measured; 765 filtered out`.
SHA-256 патча повторно совпал с указанным выше. Автор сообщил PASS целевого
rustfmt и diff check; reviewer native tests независимо не воспроизводил.
Условие focused before/after выполнено, дополнительных запусков не требуется.

Reviewer не запускал native tests, process/security/isolation checks или CI;
исходники не изменял. Этот review не подтверждает совместимость с отдельными
локальными исправлениями `b2c285f`, полный workspace gate или portable build.
