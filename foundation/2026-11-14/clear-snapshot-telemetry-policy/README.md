# Coherent clear snapshot и telemetry policy: source-only материалы

**Один кандидат coherence и одно предложение policy, не два новых бага.** Production-код не меняется. Rust/Tokio/HTTP/fault tests не запускались. Иллюстративные Python-модели не являются runtime evidence и не включены в пакет.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89), дерево `00a3c04a70d7927d1688ea155142025f596a2874`. PR91–93 production не меняют. Позднейший upstream требует повторной проверки.

## DS-5: кандидат snapshot coherence

[DS-5](DS-5.md), **P2 source-only candidate**: concurrent successful clear и conversation read могут соединить старые messages/context с новой committed revision. Причинный interleaving выведен из locks/source, но не воспроизведён в Rust/HTTP. Canonical clear остаётся корректным, последующий read может быть согласованным; постоянное воскрешение истории не утверждается.

Направление упрощения: единая publication boundary для messages + associated context + revision. Не добавлять общий run_lock к каждому reader: внутри active run это может создать deadlock. Proposed regression должен детерминированно подтвердить read-side boundary; одного sleep или обычного Poll::Pending недостаточно.

## ET-1: policy discussion и исправленная классификация

[ET-1](ET-1-policy.md) **не установленный defect, без P2/P3 и без прибавления к bug count**. Invalid UTF-8 auxiliary log прерывает context response, в том числе для sessions с тем же resolved log path. Но существующий тест `context_map/tests.rs:239–240` прямо требует Err для `[0xff, newline]`.

**Correction:** первоначальное утверждение об отсутствии такого теста и классификация как пропущенного бага сняты после дополнительного независимого review. Это проверенная source-level характеристика намеренно тестируемой fail-fast policy. Выбор между fail-fast и tolerant diagnostic mode остаётся продуктовым решением. Policy не изменена; strict canonical journal validation не предлагается ослаблять.

## Проверка, дедупликация и границы

Независимые reviews обоих материалов прочитаны; ключевые locks и invalid-UTF-8 assertion повторно сверены по исходникам. DS-5 отличён от DS-3 dropped-run reconciliation и DS-4 uncommitted-prefix display: здесь обычная успешная операция и mixed snapshot. ET-1 относится к auxiliary telemetry policy, не к journal integrity, context timeout или безопасности.

Дедупликация тематическая: релевантные опубликованные reports и targeted fragments полного extracted PR84. Полное повторное чтение всех 97 reports не заявляется; отсутствие совпадения не доказывает абсолютной новизны. Подробности в каждом отчёте.

Качественный потенциальный выигрыш: один snapshot contract вместо разрозненных чтений и явная telemetry policy вместо неоговорённого ожидания fallback. LOC/RSS/latency и частота проблем не измерены. Предложенные regression/policy-change checks не реализованы и не выполнены.

Только три Markdown-документа. Нет моделей, сырых логов, приватных путей, пользовательских данных или сборок. Merge означает публикацию исследования и correction record, не внедрение исправлений.
