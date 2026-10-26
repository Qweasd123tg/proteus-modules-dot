# Проверка recovery patches на текущем Core

Этот пакет не меняет и не дублирует реализацию: он повторно квалифицирует
существующие Core patches из [PR #22](https://github.com/Qweasd123tg/proteus-modules-dot/pull/22)
на новых исходниках после изменений storage/SQLite.

## Закреплённые источники

- Core: `63454d4e8b1e4e6b26d088fce2a17d46f30390ae`,
  исходное дерево `6fa614531f2f6ca82ad37a195b02bc1371d5b0bd`.
- Patches: `performance/2026-10-26/core/0001-tests.patch` и
  `0002-fix.patch` из неизменяемого commit Modules
  `a0c1716756f8d5950dbf92638951f676bf8d2803`.
- Официальный reference fixture:
  `Proteus-harness/Proteus-modules@7fceaebc3bed8add9b0e3091110f59deca86ba46`,
  тот же pin, что в текущем Core `repositories.json`.
- Rust `1.95.0`; тесты запускаются через текущий `scripts/test.py`
  с отдельным явно закреплённым `PROTEUS_MODULES_SOURCE`.

Полные Git/SHA-256 identities находятся в `manifest.json`. Старые patches,
их provenance, предыдущие результаты и main не переписываются. Результат
для предыдущего Core не считается доказательством для текущего.

## Последовательность qualification

1. Создать свежие, отсутствующие ранее рабочую и evidence-папки.
   Runner не удаляет и не переиспользует существующие данные.
2. Проверить commit/tree Core и fixture, source blobs, SHA-256/Git blobs
   двух patches; применить только test patch с `git apply --index`.
3. Сверить полное tests-only дерево
   `7e973e19ebf9051ba25736ae4f0deda6eb9e95f7`.
4. Запустить ровно существующий
   `app_server::http::tests::session_reads::paged_snapshot_full_history_and_revision_checked_pages_agree`.
   Принимается только его реальный missing-index behavioral FAIL:
   exit 101, один named failure, panic в first full-history unwrap,
   ошибка `history revision changed; retry reading history`.
   Compile/link failure, нулевое число tests или другой panic не считаются
   подтверждением исходного дефекта.
5. Применить неизменённый fix patch, сверить разрешённые шесть путей,
   полное дерево `9a60cd58cc9dcd9851cb461ccdbad81a1fea3f09`,
   Git blobs и SHA-256 каждого изменённого файла.
6. Через `--list` получить текущий набор `app_server::`; затем прогнать
   **весь этот набор**. Passed names должны в точности совпасть со списком,
   без failures или ignored tests. Дополнительно обязательны HTTP regression,
   три recovery unit cases и все пять текущих startup cases.
7. Проверить `cargo fmt --all -- --check`, неизменность tracked fixture,
   отсутствие новых unstaged source changes и сохранность ожидаемого дерева.

Тесты проверяют missing/malformed/checksum/unwritable disposable index,
полноту DTO и страниц, неизменность canonical journal, границы
0/1/49/50/51/100/121 строк, отказ подменять потерянную старую revision
новым источником, отказ повреждённого canonical source и startup/resume.
Три новых recovery unit cases подключаются только fix patch:
это corrected-side coverage, а не три независимых fail-before.
Rebuild материализует полную transcript; page size 50 ограничивает число
строк страницы, а не bytes/RAM полной recovery.
Модули, contracts, authority, release, deployment и native Desktop не меняются.

## Где выполняется

Workflow `.github/workflows/check-current-core-recovery.yml` разрешён только
для точной ветки `ci/current-core-recovery-20261026` этого modules-репозитория.
У workflow только `contents: read`, закреплённые Actions, отдельный hosted
Ubuntu runner, нет shared Cargo cache и нет публикации исходников обратно
в upstream. Main и чужие ветки не запускают эту проверку.

Runner использует `GITHUB_SHA` для привязки evidence к точному bundle commit.
Артефакт `current-core-recovery-<commit>` содержит bounded `result.json`:
source/fixture identities, patch identities, manifest/runner hashes,
команды, exit codes, последние 64 KiB вывода каждой команды,
обнаруженные и прошедшие test names. Reader использует nonblocking chunks,
16 KiB carry и command deadlines с завершением process group; outer job
timeout остаётся дополнительным ограничением. Артефакт сохраняется и при
ошибке, если runner успел создать evidence. Непройденная или прерванная
стадия не считается успехом.

## Статус при упаковке

Выполнены source-only проверки: прочитаны текущие AGENTS/testing instructions,
все hunks однозначно применены в памяти, исходные Git subtrees независимо
пересчитаны, ожидаемые tests-only/fixed trees восстановлены. Rust hunks
применяются без смещения; документационный hunk имеет смещение +14 строк.
Пять изменённых Rust файлов и текущий startup-file повторно проверены
официальным formatter из toolchain 1.95.0 через stdin/stdout без записи файлов.

Новый Cargo baseline/full app-server run на этом Core при упаковке
**ещё не выполнялся**. Фактический CI outcome следует читать из артефакта
конкретного commit, не из исторического отчёта.

Это regression qualification, не измерение времени, не scheduler-latency
benchmark, не native GUI/portable/release qualification и не auto-merge.
