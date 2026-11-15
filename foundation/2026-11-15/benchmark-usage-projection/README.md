# F3: единая проекция benchmark usage

Кандидат устраняет расхождение short/long report через одного владельца существующей completeness/projection policy. Полные totals, наблюдаемые lower bounds и coverage разделены. Это remediation известного F3 из [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85), не новая finding.

## Проверено

- Base Core `bcbda4435534a296c707a1daa250813d692f68e1`; 12 source Git blobs проверены.
- Exact patch SHA256 `c1c30727c0a76fecea815caf22bcb8ed14fdc2e6bd98ab8877027551c760866f`.
- Strict apply/check на отдельной base-copy, результат совпадает с reviewed candidate. Проверка повторена при публикации.
- Шесть targeted synthetic tests прошли на Python 3.12.14, exit 0. Только этот narrow gate; independent source и runtime evidence reviews приложены.
- Raw source numbers, grading/pipeline/filters/denominators/repeat rules не заменены новой политикой. Historical benchmark tables не пересчитывались.

## Ограничения

Нет baseline/red-green, полного harness/suite/CI gate, benchmark reruns, API/LLM/native CLI или Rust build. F1/F2/F4 остаются unresolved. Не заявляется отдельная OS/network namespace: optional preflight не прошёл; использовались отдельная копия, чистый environment и существующий sandbox. Upstream не изменён, публикация patch-пакета не означает production rollout.

`REPORT.md` и source review сохраняют исторический NOT RUN этап. Актуальный runtime статус только в `RUNTIME-SUPPLEMENT.md`, `RUNTIME-INDEPENDENT-REVIEW.md`, `RUNTIME-RESULT.json`. Исходные raw logs/launcher/private paths не публикуются; упоминания этих материалов относятся к retained evidence, проверенному reviewer.

## Выигрыш

Одна policy вместо двух расходящихся правил. `long_report.py`: 694→629 строк; общий helper 82; суммарно production LOC 777→802 (+25). Это устранение семантического дублирования, не LOC/performance оптимизация. Нет измеренного ускорения, экономии памяти/токенов или доказательства полного accounting correctness.

## Применение

Проверить точную базу, затем `git apply --check --whitespace=error shared-usage-projection.patch` и `git apply --whitespace=error shared-usage-projection.patch` в Core. Это инструкция, не upstream применение. Перепроверить остальные project gates перед интеграцией.
