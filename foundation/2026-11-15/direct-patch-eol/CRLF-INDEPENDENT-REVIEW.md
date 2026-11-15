# Независимый source review: uniform CRLF direct_patch

## Verdict

В exact candidate source-level blocker не найден. Поддержка uniform CRLF — полезное ограниченное исправление известного EOL mismatch, не полное закрытие mixed-EOL/file-tools family. Source acceptance не означает compile/test/runtime PASS.

## Проверенные invariants

Delimiter выбирается один раз по исходнику: минимум один CRLF и каждый LF непосредственно после CR. Unterminated последний fragment не мешает CRLF detection. Source без LF, включая ending bare CR, остаётся на legacy LF path. Внутренние bare CR и literal CR в unterminated последней строке остаются данными; общего trim/replace нет.

split_lines и render_text получают один delimiter. Uniform CRLF перестаёт оставлять delimiter CR в logical lines, поэтому совпадает с parser-normalized hunk text; вставки получают тот же source delimiter независимо от LF/CRLF patch text. Существующий cursor/exact subsequence/multi-hunk алгоритм не меняется. trailing_newline определяется по выбранному delimiter, сохраняется по умолчанию и сбрасывается явным no_newline_at_eof. Поэтому EOF marker убирает целый CRLF, не оставляя delimiter CR. Empty result остаётся empty, без принудительного newline.

Все найденные production callsites private split_lines/render_text обновлены: apply_hunks использует source delimiter, Add File явно использует LF. No-hunk path roundtrips исходные bytes, включая пустые/blank/unterminated cases. Последовательные operations по-прежнему работают с текущим source каждого update, не с глобальной нормализацией файла.

Mixed LF/CRLF выбирает тот же прежний LF split/join и trailing flag. Для него matching/результат остаются legacy: LF строки можно менять без изменения untouched CRLF bytes, hunk на CRLF строке всё ещё может не совпасть. Это явно задокументировано, новая arbitrary insertion-EOL policy не введена. Pure-CR line endings также не поддерживаются как delimiters.

## Parser boundary и ограничения

Прочитаны tokenizer normalization и update/hunk parser в lib.rs. Patch trailing CR уже удаляется существующим parser; эта правка не пытается сделать literal trailing CR в hunk универсально выразимым. Claim «bare CR остаётся данными» относится к source split/render и внутреннему CR в hunk, а не к новому способу адресовать любой trailing CR через patch syntax. No-newline flag устанавливается существующим End of File marker; Core prompt semantics сообщил coordinator.

Не исправляются смешанные окончания строк или file-tools range-edit representation. File I/O/transaction authority и прочие соседние механизмы не аудировались и не менялись.

## Compile-shape и proposed tests

Изменены только private helper signatures, один Add callsite и cfg(test) module. str::split_terminator принимает &str delimiter; owned lines и splice types остаются прежними. transaction/eol_tests.rs соответствует mod eol_tests, super::* даёт PatchOperation/Hunk и private helpers; crate::parse_patch доступен дочернему module. Новых dependencies/public API нет. Компилятор не запускался.

Прочитаны семь pure proposed tests: LF/CRLF source×patch matrix; insert/remove/multi-hunks; unterminated/EOF; blank/no-hunk/empty roundtrips; bare/internal CR и no-newline source; mixed legacy match/fail; Add LF. Tests проходят через реальный parser для update/add fixtures, но Add проверяет render helper, не полный filesystem transaction. Ни один test не выполнялся. Нет утверждения об integration/persisted file acceptance или всех EOL комбинациях.

## Evidence

Coordinator сообщил восемь verified source blobs и text apply/check/after equality. Modules baseline c035142558f0fca43e9772fc0e50ca293abf1531. Independently прочитаны exact diff/pure helpers/parser и пересчитаны SHA256:

- patch: 4d632d1820b39ff458c749bfce1e78945542236f0d7f70ea8f7c1d639f5cafa8
- transaction.rs: 1431a8880b825fc8ab252a2b782e796588f90a740b022512b9409fa4ba321484
- eol_tests.rs: 7f6f68fc774351dae73c6e68639bfea821b93119e71322be81cc64cd1d2bb471
- docs/reference.md: 2f391b9008c91074f843408f06b4e2e6a1fb7b93ea44f2f8c5108b20e405892b

Rust/compiler/formatter/tests/runtime/project scripts/dependency installs не запускались. Production и публикации не менялись. Измеренный performance effect не заявляется.
