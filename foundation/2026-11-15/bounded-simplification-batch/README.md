# Proteus: source-only simplification batch

Один пакет шести направлений вместо серии мелких PR:

- 7 reviewed source-кандидатов, 11 затронутых файлов;
- NaN/revision behavior change отдельно на **HOLD**;
- CI/test dedup только как план, безопасных удалений tests сейчас **0**.

[Общий отчёт](REPORT.md) · [Источники](SOURCES.json) ·
[Фактические static checks](VERIFICATION.json) · [Итоговое review](REVIEW.md).

**NOT COMPILED / NOT RUN:** Rust/Cargo/rustfmt, project tests, native runtime,
GUI, provider, benchmarks и CI. Text apply/reverse и source review не равны
runtime validation. Ни upstream integration, ни performance win не заявлены.

`patches/` содержит семь отдельных кандидатов для точных баз из отчёта.
Пути внутри patch относительны к соответствующему Core/Modules/Desktop,
не к этому delivery repository. Это не инструкция применить всё автоматически.
`hold/` исключён из рекомендуемой композиции. Старый combined runtime patch
не включён. Существующие dependencies и installed builds не меняются.

[План дедупликации](TEST-DEDUP-PLAN.md) не разрешает массовое удаление тестов
или переписывание исторического evidence. Parser private API и сдвиг одного
test oracle, а также свежие source/pin изменения подробно раскрыты в отчёте.

## Позднейшая узкая квалификация

[2026-11-17: Rust before/after для single-terminal-reader](QUALIFICATION-2026-11-17.md):
те же 17 существующих pure tests PASS до/после и в независимом повторе.
Это отдельное дополнение к историческому source-only evidence выше, только для
одного unchanged patch; не весь batch и не upstream integration.
