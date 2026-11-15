# Direct patch: согласовать split/render для uniform CRLF

## Статус и граница

**Source-only candidate для uniformly-CRLF части известного tools-integration
P2/PR85.** Это не новая находка, не полное закрытие семейства EOL и не runtime fix,
проверенный компиляцией или исполнением. Mixed-EOL matching и file-tools
range-read → exact-edit mismatch остаются нерешёнными.

Свежие refs на 2026-11-15: Modules
`c035142558f0fca43e9772fc0e50ca293abf1531`, Core
`bcbda4435534a296c707a1daa250813d692f68e1`, delivery
`0c7549f7a623eed007215e32acdbefed6d4536ed` (PR115).
Actual Modules Core pin: `41bdfffa6e70228278b4abc758b7f81a12672f35`.
PR113–115 остаются отдельными uncompiled candidates; OTM-1 не объявляется исправленным.

## Причина

Patch parser читает line-based текст без CRLF separators. Source splitter
использует только LF, поэтому CR остаётся частью каждой строки CRLF source.
Обычный context/removal text без CR не совпадает с такими source lines.
Простое игнорирование CR только при поиске недостаточно: replacement/context
собираются из patch и могли бы изменить newline convention.

Историческое воспроизведение в PR85 использовалось только для dedup и provenance. Ни тот process/file test, ни новый candidate здесь не запускались.

## Выбранный узкий contract

Для одного update `apply_hunks` один раз выбирает delimiter из исходного текста:

- CRLF, если есть хотя бы один CRLF и **каждый** существующий LF входит в CRLF;
- LF во всех остальных случаях, включая empty/no-newline и mixed LF/CRLF input.

Один выбранный delimiter используется существующими split, trailing-newline
check и render. Hunk matcher/cursor/splice остаются прежними. Нет whole-file
replace/normalization, line-object framework, новой публичной DTO или mapping
между отдельными representations. Add File явно продолжает использовать LF,
независимо от line endings самого patch.

Для uniform CRLF поддерживаются обычные replacement/insertion/removal/context
и несколько hunks с сохранением source CRLF. Unterminated last line остаётся
unterminated; bare CR не удаляется как delimiter. Файл без newline не содержит
информации о конвенции и сохраняет прежний LF path.
Это не расширяет parser: его прежнее удаление trailing CR ограничивает
выражение literal CR в конце hunk line. Сохранение таких source bytes не
означает, что любой из них можно явно адресовать этим patch format.

`*** End of File` в **direct_patch** означает убрать final newline, а не Codex
anchoring marker; это подтверждено выбранным Core prompt. Для uniform CRLF
убирается полный CRLF terminator, без оставленного CR. Codex patch не меняется.

## Почему mixed cases не расширены

Для mixed source выбран буквально прежний LF path: splitter оставляет CR в
строках, matching exact и renderer join LF. Ранее работавшее изменение LF line
сохраняет соседние CRLF bytes; matching CRLF line через обычный hunk по-прежнему
может не работать. Этот patch **не** выбирает для mixed insertion «первую»,
«большинство» или соседнюю newline convention и не нормализует файл целиком.
Legacy EOF/matching semantics mixed path также не переопределяются.

Полное mixed-EOL редактирование потребовало бы отдельно выбранной политики
для добавленных строк и сохранения separator каждого исходного line. Здесь
такое расширение удержано, а не спрятано за ложным заявлением универсальной поддержки.
Отдельное file-tools exact-range представление не меняется.

## Стоимость и неизменяемые boundaries

Inference добавляет source scan без создания нормализованной полной копии;
существующие Vec<String>, hunk matching и render остаются. Дополнительная работа
и delimiter не являются измеренной performance оптимизацией. Production file
308 → 322 строки (включая test-module declaration); цель correctness обычного
CRLF пути, не сокращение LOC.

Изменены только EOL split/render и явный LF argument существующего Add renderer.
Transaction planning/commit, file authority, rollback, permissions и path
правила не менялись и не исследовались как отдельная задача. Никаких файловых
операций приложения, command execution или safety regression fixtures не запускалось.

## Evidence

- `SOURCES.json`: восемь exact Modules/Core-pin blobs,
  Git identities совпали. Materialization соседних функций не означает их аудит.
- `direct-patch-eol.patch`: один production Rust файл,
  новый pure test файл и существующая reference documentation (+10 строк).
- Семь proposed tests через настоящий parser и pure `apply_hunks`/render:
  LF/CRLF source × LF/CRLF patch; insert/remove/multiple hunks; unterminated
  last line и EOF marker; empty/blank/no-hunk roundtrips; bare CR и no-EOL LF;
  unchanged mixed path; Add File LF. **Не запускались** и не проверяют commit/file I/O.
- `PATCH-VERIFICATION.json`: только text `git apply --check`, apply и byte
  comparison трёх after files в отдельной копии. Алгоритм patch application
  проекта не выполнялся и не подменялся Python-моделью.
- `COMPOSITION.json`: оба text-only порядка с PR115 применяются и дают
  одинаковые bytes, включая две независимые правки docs/reference.md.
  Это не compile/runtime integration.
- `CRLF-INDEPENDENT-REVIEW.md`: независимый exact source review.

Rust/cargo/rustfmt/clippy, project scripts/tests, приложение, providers и
installations не выполнялись. Upstream production/refs не менялись.
До принятия нужны formatting/compilation и focused direct-patch tests,
затем существующий file/transaction boundary regression на обычном CRLF input.
Непроверенные стадии не названы PASS.
