# Unified exec: сохранять незавершённый UTF-8 символ между polls

## Статус и scope

**Source-only candidate для известного initial-modules P2/PR85**, не новая
находка и не подтверждённый runtime fix. Исследовалась только корректность
model-visible UTF-8 output collection. Изменение не касается command execution,
input handling, session ownership, процесса отмены или платформенного isolation.

Свежие refs на 2026-11-15: Modules
`c035142558f0fca43e9772fc0e50ca293abf1531`, Core
`bcbda4435534a296c707a1daa250813d692f68e1`, delivery
`0d465f1c84ce77a8e9f88353ac23d98e1d4663b2` (PR114).
PR113/114 остаются отдельными uncompiled candidates. OTM-1 не решается.

## Причина

Общий `wait_and_collect`, используемый exec и последующими polls, полностью
забирает byte buffer. `render_result` независимо применяет lossy UTF-8 decode
к каждой выдаче. Корректный символ, чьи bytes попали по разные стороны poll,
превращается в replacement characters, хотя concatenated stream валиден.
Например, `F0 9F` и последующие `98 80` должны образовать один `😀`.

Исторический reproduction сохранён в `PRIOR-UTF8.md` только как provenance и
dedup. Старый process test не запускался заново и не доказывает этот patch.

## Минимальное изменение общей причины

В существующий collector добавлен private `take_ready_bytes`. Перед live poll
он оставляет в прежнем session buffer только незавершённый trailing UTF-8
prefix, максимум три bytes. Остальные bytes перемещаются в `Collected` как
раньше. Следующий output chunk дополняет тот же buffer; отдельный decoder state,
cache, protocol field, public abstraction или dependency не добавлены.

Helper смотрит только на последние три bytes через `std::str::from_utf8`:
- `error_len = Some(n)` означает definite invalid sequence; scanner пропускает
  её, но сами bytes остаются в текущей выдаче для прежнего lossy decode.
- `error_len = None` обозначает incomplete trailing prefix; только он остаётся
  в session buffer до следующего poll.

Такое различие и длина incomplete suffix определены
[стандартным Rust Utf8Error contract](https://doc.rust-lang.org/std/str/struct.Utf8Error.html#method.error_len).
Если last-three window начинается внутри предыдущего полного символа, его
continuation bytes дают definite errors и не удерживаются. Максимум три bytes
просматриваются; полный накопленный output заново не валидируется этим helper.

## Terminal, binary и truncation границы

- Заведомо невалидные, overlong и произвольные binary bytes не получают нового
  формата. Existing lossy renderer продолжает заменять их replacement characters.
  До трёх binary bytes, совпадающих с корректным incomplete prefix, могут быть
  отложены до продолжения/terminal выдачи: это необходимая неоднозначность streaming decode.
- Flush происходит при `exited` **или** закрытии всех readers. Здесь `exited`
  означает последнюю доступную выдачу: оба существующих caller затем удаляют
  session handle. Это **не** утверждение о полном EOF. Удержание bytes после этой
  точки потеряло бы их, поэтому остаток выдаётся через прежний lossy decoder.
- `readers.is_closed()` может означать EOF, read failure или drain expiry.
  Helper не превращает эти причины в успешное/полное чтение и не меняет delays.
- Existing exit/drain/deadline policy, поздние bytes после terminal удаления,
  interleaving отдельных stdout/stderr streams и UTF-8 разрезы внутри head/tail
  truncation не исправляются. Claim ограничен poll boundary одного уже
  наблюдаемого byte stream при последующем поступлении его continuation.
- При dropped-middle preview renderer как прежде отдельно декодирует head и
  tail вокруг omission marker. Удерживается только последний suffix tail,
  без соединения данных через вырезанный участок. Buffer после удержания
  максимум трёх bytes всё ещё длиннее существующей head boundary.
- `output_bytes` считает bytes текущей выдачи, поэтому задержанный prefix
  учитывается в следующей выдаче. Truncation flags/counts не переопределяются.
  Raw capture/terminal append происходят раньше collection и не меняются.

Helper заимствует mutable buffer только внутри существующего lock, переносит
основной Vec и копирует не более трёх retained bytes через `split_off` при
incomplete suffix. Это bounded source observation, не измерение RSS/CPU/latency.

## Evidence и следующие проверки

- `SOURCES.json`, `READ-VERIFICATION.json`: девять exact source blobs, все Git
  identities совпали. Чтение было ограничено названными safe output boundaries;
  полное materialization файла не означает аудит соседних функций.
- `utf8-poll-boundary.patch` (before/after snapshots retained locally, not published): production output.rs
  190 → 222 строки (включая test-module declaration), новый test файл 138 строк,
  существующая reference documentation +8 строк. Это correctness fix, не −LOC refactor.
- Шесть proposed pure tests: все пары poll splits для ASCII/2/3/4-byte символов;
  single-byte и пустые polls; invalid/overlong binary; final incomplete flush;
  rendered metadata/однократная выдача символа; dropped-middle preview.
  **Не запускались**, не являются process/reader integration evidence.
- `PATCH-VERIFICATION.json`: только text `git apply --check`/apply и exact byte
  comparison трёх after files в изолированной копии.
- `COMPOSITION.json`: оба text-only порядка с PR113 применяются и дают одинаковые
  bytes; это не совместная компиляция. PR114 относится к другому, Core, дереву.
- `UTF8-POLL-INDEPENDENT-REVIEW.md`: independent exact source review.

Rust/cargo/rustfmt/clippy, project scripts/tests, command/process/PTY runtime,
provider calls и installations не выполнялись. Upstream refs не менялись.
До принятия нужны toolchain/formatting/compilation, эти focused tests и целевая
проверка существующего exec/poll boundary с разрезанными UTF-8 bytes, invalid
binary и final incomplete output. Никакой execution PASS здесь не заявляется.
