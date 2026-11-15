# Независимый source review: UTF-8 poll boundary

## Verdict

В exact candidate source-level blocker не найден. Узко исправляется известная потеря UTF-8 на границе незавершающих polls: incomplete trailing scalar удерживается в существующем byte buffer до продолжения или последней выдачи. Это не новая finding и не compile/test/runtime PASS.

## Алгоритм и lifecycle

Прочитан полный diff трёх файлов. Helper забирает buffer, проверяет только последние не более трёх bytes и возвращает всё, кроме легитимно incomplete suffix. Максимальный неполный UTF-8 scalar занимает три bytes. Если начало проверки попало внутрь уже завершённого scalar, continuation bytes дают definite errors и пропускаются; это не создаёт ложного удержания. valid_up_to + Some(error_len) обеспечивает продвижение; None удерживает именно конечный prefix через split_off. Полный buffer не сканируется и новый per-session state не добавляется.

Definite invalid/overlong/surrogate/out-of-range prefixes остаются в текущей выдаче и идут через прежний lossy decoder. Binary bytes, совпавшие с допустимым incomplete prefix, могут задержаться до следующей выдачи; patch не распознаёт binary encoding и не обещает немедленность для любого binary suffix. При продолжении invalid bytes снова выходят по прежним правилам. Пустые polls не потребляют pending prefix; final_output возвращает всё без удержания.

`final_output = exited || readers.is_closed()` соответствует **последней доступной выдаче**, не доказанному EOF. Оба существующих caller удаляют session на collected.exited. ReaderCompletions.is_closed включает EOF, ReadFailed и DrainExpired. Поэтому flush необходим и при неполном завершении чтения: удержанным bytes иначе может не быть следующего poll. Wait/deadline/drain/cancellation policy не менялась. Поздние reader bytes после terminal removal остаются вне scope.

## Буфер, gaps и rendering

Существующий append buffer limit/head-tail gap не меняется. Когда dropped_bytes > 0, сохранённый buffer имеет SESSION_BUFFER_LIMIT bytes; удержание максимум трёх оставляет его заведомо длиннее половины лимита, поэтому прежний split_at(SESSION_BUFFER_LIMIT / 2) безопасен. Head и tail по-прежнему отдельно lossy-decode вокруг omission marker; новый helper не соединяет их через dropped middle.

Output_bytes остаётся количеством bytes текущего Collected, а не total produced или UTF-8 rendered length: deferred suffix учитывается при последующей выдаче. dropped counter обнуляется на сборе как прежде, pending bytes не объявляются dropped. Новое удержание не меняет raw capture. Не заявляется устранение corruption на middle truncation boundaries, interleaving независимых streams или terminal late-reader loss.

## Compile-shape и шесть proposed tests

Private helper использует стандартные Vec/str APIs без новых dependencies/DTO. cfg(test) mod tests в output.rs соответствует output/tests.rs; дочерний модуль получает private helper/render/Collected/constants через super::* и existing imports. Borrow output.buffer заканчивается до следующих полей Collected; дополнительный async/lifetime boundary отсутствует. Компилятор не запускался.

Прочитаны все шесть pure test functions: все пары двух poll boundaries для ASCII/2/3/4-byte scalars и mixed text; одно-byte+empty polls; definite invalid cases и invalid-prefix + valid continuation; final incomplete flush; render и output_bytes/session metadata; dropped-middle render safety с retained suffix. Fixtures не запускают processes и не вызывают wait_and_collect. Это хороший предложенный regression scope, но не выполненное доказательство: нет интеграционного теста collector final_output selection/reader timing, нет exhaustive byte-space proof. Source reasoning выше отдельно покрывает эти bounded invariants.

Документация корректно ограничивается text preview, отличает terminal status от EOF и сохраняет прежние truncation/raw capture semantics.

## Evidence и ограничения

Coordinator сообщил 9 source blobs и text apply/check/byte equality. Baseline Modules c035142558f0fca43e9772fc0e50ca293abf1531. Independently пересчитаны SHA256:

- patch: 73a1b93e7cd5f6186bc66b595654d8f76505ff528752c0929e7d598e04e34020
- output.rs: ee2e6e223466ab5dc26279bb0b1d7e31fcdb284dba066e1411589bee14fea756
- output/tests.rs: 783ba0706fb1ff93fdf61b891e0fdd765fb7dbd2b38394574aa30e3eac10a6a7
- docs/reference.md: 44b74f3f39b8ade6ef470e626d5f7c110a0eb99ccdd2903b985cef24ec38ebfb

Rust/compiler/formatter/tests/runtime/process execution/project scripts/dependency installs не запускались. Production и публикации не менялись. Рассмотрена только output UTF-8 correctness boundary; соседние подсистемы не аудировались. Performance не измерялся.
