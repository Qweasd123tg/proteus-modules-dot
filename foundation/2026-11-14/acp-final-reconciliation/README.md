# DS-11: canonical final и ACP terminal reconciliation

[Source-only отчёт и proposed regression](REPORT.md). **P3 custom-workflow interoperability candidate**, не наблюдённый stock/runtime incident. Это развитие ранее опубликованной **не повышенной до finding гипотезы** acp-cli: теперь описан contract-valid model-free producer и полная source chain. Не новая неизвестная тема и не выполненная wire-репродукция.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89), tree `00a3c04a70d7927d1688ea155142025f596a2874`.

## Узкий witness

Custom workflow без model/tools и active hooks публикует commentary C, затем успешно возвращает новые canonical assistant messages [C,F] и output.text=F.text. Final F не был streamed. Source path ACP считает наличие любого ранее опубликованного assistant text достаточным, чтобы подавить fallback F; canonical F при этом сохраняется.

**Canonical message не равен status summary.** Existing ModelCallingWorkflow вправе вернуть output.text=`done`, отличный от response.messages. Поэтому нельзя исправлять это слепым добавлением всякого отличающегося output.text. Witness требует именно distinct persisted final F, не просто иной status text. Optional TurnFinished/TurnOutput не заменяют его presentation в проверенной ветке.

Независимый source review подтвердил custom producer route, single-item event contract и consumer branch. Proposed fixture не создана/исполнена, default-profile occurrence не установлен. Canonical history не потеряна, provider/billing/security effects не заявляются.

## Проверка и упрощение

Proposed ACP regression должен проверить весь session/prompt flow и canonical C/F, а не только unit fallback. Controls: без commentary, explicit final event, exact-once Unicode completion, peer/reasoning-only text и status-only output. Это планы, не прогоны.

Направление: одна accepted-completion identity boundary, reuse canonical IDs и prefix-aware projector. Не replay всего snapshot, не module-name exception и не inference finality по непустой строке. LOC/RSS/latency не измерены.

Дедупликация: полный опубликованный acp-cli report и targeted PR84; прежняя unpromoted гипотеза явно признана. Полная повторная проверка всех historical reports не заявляется.

Только два Markdown-документа. Нет исходников, моделей, сырых логов, приватных путей, пользовательских данных или сборок. Rust/project tests/ACP/GUI/provider не запускались. Abstract model не runtime evidence. Merge публикует исследование, не исправляет runtime.
