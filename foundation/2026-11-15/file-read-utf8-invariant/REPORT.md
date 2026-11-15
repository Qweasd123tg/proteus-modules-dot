# Bounded file reads: один UTF-8 invariant для двух readers

## Итог

Подготовлен **source-only candidate для известного initial-modules #4**, не новая finding и не повышение его прежней P3 severity. Вместо отдельного EOF if вводится одна маленькая crate-private borrowed decode policy для ranged read_file и read_many_files:

**Незавершённый последний scalar можно отбросить только у известной reader-у byte-budget boundary; observed EOF требует строгого UTF-8. Invalid interior bytes не исправляются.**

Смысл изменения — одинаковый invariant в двух raw-byte readers и отделение raw validation от усечения уже валидного String. Независимый exact source review не нашёл blockers. Compile/tests/runtime не выполнялись.

## Версии

Fresh refs в начале/конце, 2026-11-15:
- Modules `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core main `bcbda4435534a296c707a1daa250813d692f68e1`.
- Actual Modules Core pin `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Delivery main `b26bcd0c7de6895d12a61b6b11a3c43e6f674d0e`, включая PR118 HOLD.

PR115 касается lossy decoding текстового shell collector. Его binary/EOF contract не переносится в строгий UTF-8 file reader. PR116 direct_patch EOL, PR117 context-stop и PR118 completion-budget HOLD — отдельные направления; accounting и delivery HOLD этим patch не закрыты.

## Причина и изменение

До candidate read_many вызывает один utf8_prefix и для raw файла, и для готового rendered String. Helper всегда допускает incomplete suffix, даже если read_to_end достиг EOF, поэтому bytes valid+C3 дают successful valid без truncation. Ranged read_file уже различает budget cut и complete line, но содержит отдельную реализацию policy.

1. **Новый read_text.rs:** decode_read_bytes возвращает borrowed &str. Стандартный validator сохраняется; incomplete-tail exception существует в одном месте и только при явном at_budget_boundary.
2. **read_many raw read:** take(limit+1) по-прежнему ограничивает чтение. Только bytes.len()>limit выбирает budget boundary. Если прочитано <=limit, bounded read достиг EOF, включая равенство limit, и incomplete scalar становится прежним typed tool error path.
3. **Старая metadata.len() не управляет permissive decoding.** Поле truncated сохраняет прежнюю консервативную формулу с original_bytes, но старый больший размер не является доказательством budget cut. Файл, укоротившийся до malformed suffix, больше не получает разрешение скрыть этот suffix.
4. **read_file range:** использует тот же decoder с прежним условием end<line.len() || !complete. Error wording, output, byte/line limits, metadata и scan behavior сохраняются.
5. **Rendered String:** уже гарантированно UTF-8. Удалены повторное fallible decoding, недостижимый error branch и создание replacement String; остаются char-boundary selection и in-place truncate.
6. **Full read:** остаётся прежний owned String::from_utf8. Общая abstraction не навязывает ему лишнюю копию.

Нет новых public DTO, process versions, dependencies, flags, filesystem actions или framework. Никаких изменений authority/path resolution, write/edit coordination или process management.

## Точные пределы

- Observed EOF не равен любой физической границе файла. В ranged reader read==allowance без LF по-прежнему считается incomplete, даже если реальный EOF случайно ровно там. Без дополнительного чтения EOF не доказан. Candidate сохраняет эту прежнюю bounded range semantics.
- Unread suffix после budget не валидируется. Successful prefix не обещает, что весь большой файл корректен.
- original_bytes остаётся metadata snapshot, не гарантией snapshot-consistent file contents. Более сильная filesystem consistency здесь не вводится.
- Range line-ending normalization и read-range→edit CRLF issue не исправляются.
- Shell binary/lossy decoding из PR115 намеренно не переиспользуется.

## Польза без фиктивных runtime claims

Две независимые raw-byte decode policy sites становятся одной. Общий decoder заимствует bytes, не создавая String. Для numbered rendered-output truncation удалён путь повторной validation/allocation; это факт исходников, не измеренное ускорение или число runtime allocations.

Четыре изменённых production prefixes перед первым cfg(test) дают 680→677 строк. Это небольшой побочный эффект, не цель candidate. Методика в MEASUREMENTS.json. Основной результат — отсутствие расхождения EOF/budget semantics и невозможность передать старую metadata estimate как основание для permissive raw decoding в read_many.

## Семь предложенных тестов, NOT RUN

- Два pure decoder tests: все incomplete prefix lengths двух-/трёх-/четырёхбайтовых scalar, invalid interior/overlong/surrogate bytes, empty/valid text и borrowed pointer.
- Два read_many internal tests: observed EOF при limit equality и большем limit, в том числе с завышенной старой metadata; реальные budget cuts, invalid interior bytes, сохранение консервативной metadata на valid shortened file.
- Три ToolModule-style tests: strict small observed EOF во full/ranged/batch/numbered modes; explicit truncation metadata при намеренном scalar cut; numbered rendered String, бюджет которого попадает внутрь scalar.
- Existing range budget/scan tests не изменены.

Эти tests только написаны и прочитаны независимо. Они не компилировались и не запускались. Нужен разрешённый focused file-tools gate на exact patch, затем применимый общий gate; исторический reproduction из prior report не является проверкой fix.

## Verification и композиция

- 10 baseline source blobs сверены с Git SHA; SOURCES.json и PUBLICATION-VERIFICATION.json.
- bounded-read-utf8.patch прошёл только git apply --check --whitespace=error и текстовое применение; bytes совпали с after/.
- Независимый exact review: FILE-READ-INDEPENDENT-REVIEW.md.
- Changed-file sets не пересекаются с PR115, PR116 или PR117. COMPOSITION.json фиксирует именно это сравнение, **не combined apply/build/runtime**.
- PR118 оставлен на HOLD. Никакая его новая API/ack схема не добавлялась.

## Артефакты

- Patch SHA256: `61f6e9e6b1ec75e4237fdf041445382bb7f1955138b9739d914c3da5b718bccd`.
- Baseline source provenance: `SOURCES.json`; полные снимки исходников не публикуются.
- `PUBLICATION-VERIFICATION.json`, `MEASUREMENTS.json`, `COMPOSITION.json`, independent review.
- `PRIOR-INITIAL-MODULES.md` содержит только относящийся к read_many UTF-8 исторический excerpt.

Не запускались Rust/cargo/compiler/formatter/tests/project scripts/fixtures/приложение/providers. Ничего не устанавливалось. Production, upstream refs и публикации не менялись. Готов только **непроверенный source candidate**, не production fix.
