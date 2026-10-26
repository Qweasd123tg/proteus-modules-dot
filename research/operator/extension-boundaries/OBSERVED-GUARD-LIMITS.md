# Дополнение: пример реально проверенного, но узкого enforcement

**2026-10-26 04:24 UTC.** Исходная матрица `b7f9b12f03510f647b83036a4f16acd3f582898c7b315124960a15e9176dcf0a` сохранена без изменений. Новый отдельно принятый R57 добавляет полезный пример **OBSERVED ENFORCEMENT в named guard-enabled fixtures**, но не повышает ни одну широкую ячейку F-T/F-R/F-G/F-D до full-fidelity guarantee.

**OBSERVED ENFORCEMENT только в named guard-enabled fixtures:** opt-in helper `guardArgumentReplacement` отклонил четыре конкретных unsafe-integer replacement cases при 13 вызовах существующего pinned JS hook worker плюс initialize. Наблюдались точные errors без `error.data`, успешный следующий safe42, два Continue и семь ожидаемых replacements. Отдельно прошли 38 pure controls самого helper. Это не новый запуск данной памятки; reused independently accepted runtime evidence. [R57 review](../EVIDENCE.md#r57).

Граница намеренно уже обещания «аргументы сохранены»:

- Guard проверяет **готовый outbound value в момент вызова**, не восстанавливает precision исходного JSON.
- Вычисленный safe0 после предыдущего rounding был принят; позже другой unguarded handler вернул2^53 и тоже был принят. Это реальные counter-controls, не скрытые случаи.
- Опт-ин одного producer не покрывает остальных и не замораживает объект после проверки.
- Core/policy/approval, Restricted process, guest engine и remote connector этим runtime не выполнялись. Ordinary hook error не является здесь доказательством отказа underlying tool, и никаких прежних effects он не откатывает.

Именно так следует читать узкое observed enforcement, не deployment guarantee: указать **правило, implementation pin, fixture и наблюдаемый результат**, а затем отдельно перечислить непокрытые пути. R45 остаётся действительным наблюдением неизменённого SDK без этого opt-in helper. Общая матрица сохраняет12 SOURCE /8 DESIGN /8 UNKNOWN и0 class-wide ENFORCED; ни baseline, ни source-only исторические counts не переписаны.
