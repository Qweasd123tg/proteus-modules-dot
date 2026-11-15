# Proteus: shared owners follow-up после #165

Один пакет подготовленных изменений, без изменения active CI, upstream или
установленного Proteus. Главный результат: skills CI получает существующего
общего владельца вместо четырёх копий, с реально выполненными Python controls
и сохранёнными обеими compatibility lanes. Остальные изменения дополняют
эту тему, но не выдаются за крупный архитектурный рывок.

## Что входит

| Кандидат | Польза | Проверка и граница |
| --- | --- | --- |
| [Skills](skills/REPORT.md) | 4 дубликата → existing owner; 15 повторных test definitions убраны, net −276 active-source строк | 37 expected outcomes; 15 unique Python controls, 60 executions baseline/candidate × 2 lanes. **Repository-layout only:** standalone current package и 4 private entrypoints не сохраняются. Это proposal, не active adoption. |
| [Envelope](envelope/REPORT.md) | Existing success test охватывает все 3 policies и monitor/receipt agreement; 35 method names прежние | Mocked/file tests и fault injections реально исполнены. Только preparatory guard: отдельное применение отвергается frozen source gate; требуется явная active revision. |
| [Core mailbox](runtime/REPORT.md) | Две running-delivery реализации → один private owner, net −10 production строк | Source-only. Разные admission/idle paths не объединены; native tests NOT RUN. |
| [Model metadata](metadata/REPORT.md) | Catalog/quota используют один metadata 401-refresh path в existing transport, net −2 production строки | Source-only. Inference retry и разные endpoint cache/DTO policies не объединены; 1 proposed test method/6 cases NOT RUN. |
| [Instruction prefix](instructions/REPORT.md) | OpenAI/Anthropic делят один canonical-prefix algorithm, provider wrappers различны | Source-only, production **+2 строки**, не оптимизация allocations. 1 proposed native test/12 table iterations NOT RUN. |

Новых frameworks, dependency crates, общей модели provider state или
универсального supervisor не добавлено. Нет обещания CPU/RAM/frame-time/CI
ускорения. Source extraction не равен runtime qualification.

## Существенная корректировка после review

Первый skills candidate пропускал новый shared owner в финальной проверке
`lock_only.sh`. Второй reviewer нашёл это до публикации. Финальный patch
проверяет shared files и там; exact extracted post-check прошёл на unchanged
inputs и разрешённом Cargo.lock-only изменении, отверг shared mutation.
Устаревший 34-outcome результат заменён финальным 37-outcome результатом.
Все финальные freezes/hashes и две independent reviews относятся к final
patch `571def00d3461f9a1a67e72b579f035cf8667b25713a7067f97d254cc0a46749`.

## Проверка publisher

- Fresh heads повторно проверены: delivery `cbd9ec315f88f85708d26d47cc2193970a7c904b`,
  Core `9437c61785cdb5933a980e7d683afb7e85f352e9`, Modules
  `42ae75355256190d01b569c85633b333d573f052`. Modules Core dependency pin
  `185225a7103088c444788374ca425d230060f55a` не меняется.
- 248 source-identity records сверены с fresh trees (182 distinct repo paths,
  с перекрытием между направлениями), отдельно два Core dependency files
  re-fetched на exact pin. Это не ручной аудит всего репозитория.
- Все 5 patches: strict whitespace apply-check, zero-fuzz/no-offset apply,
  reverse и exact baseline restoration. Два порядка двух новых Modules
  patches дают одинаковые materialized bytes. Это text composition, не
  cross-repository/runtime integration.
- Independent source/evidence reviews приложены к каждому направлению.
  Skills review включает pre-run и actual evidence; envelope reviewer
  независимо повторил controls, добавил disk-only receipt mutation и
  подтвердил конкретный negative frozen-source refusal.
- Test executions разных revisions/lanes/reviewers **не складываются в
  количество уникальных tests**. Failed negative controls не называются
  runtime PASS.

## Не выполнено и не изменено

Rust/Cargo/rustfmt, actual Core probe, full package/lock-resolution gate,
hosted CI, native UI, provider/runtime integration и benchmarks здесь NOT RUN.
Skills выполнял tiny authored Python children; envelope использовал mocks и
temporary files. Никакой перенос их результата на Rust behavior не допускается.

Не меняются active workflows, исходники upstream, dependencies/pins,
historical validation snapshots и NaN HOLD #165. Desktop HOLD не включён
ради увеличения числа кандидатов. Skills packaging tradeoff и envelope
active-freeze gate должны быть решены до adoption; этот merge лишь публикует
проверенные предложения и границы их доказательств.

Пакет содержит только allowlisted patches, concise reports/reviews, identities
и verification summaries. Полные source snapshots, raw logs, private paths,
superseded candidates и служебные API dumps исключены.
