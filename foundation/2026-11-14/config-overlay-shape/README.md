# COS-1: invalid directory config shape и watcher recovery

[Source-only отчёт и proposed regressions](REPORT.md). **P3 malformed-configuration robustness candidate**, не valid-config failure, security issue или наблюдённый runtime incident.

Минимальная source-derived предпосылка: directory profile, обычный `a.json` со значением `null` и валидный `config-builder.toml`. Final ordinary-fragment fold остаётся non-object; overlay-path вызывает `expect` до schema validation. Поздний ordinary object fragment может предотвратить именно эту ветку; malformed JSON, без overlay и single-file load имеют другие normal-error paths.

Watcher напрямую вызывает loader до debounce и `Input::Invalid`. **При обычной panic-unwind политике** такой panic может завершить watcher task, после чего она не опрашивает исправленный профиль. Это source inference, не выполненный тест; whole-process crash не утверждается. Last-good assembly не заменяется этим scan, manual recovery/new watcher не исключены.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89); tree `00a3c04a70d7927d1688ea155142025f596a2874`. Позднейший upstream требует перепроверки.

Independent review подтверждает точный last-fold precondition, overlay parsing order, countercontrols и conditional task-liveness inference. До публикации повторно прочитаны полные опубликованные config-validation, profile-recovery и state-install reports; PR91–99 также проверены. Их Save/slot validation, fingerprint revert, instruction serialization и managed-overlay semantics отличаются. Targeted extracted PR84 search не дал совпадения; абсолютная новизна не гарантируется.

Минимальное исправление-кандидат: contextual Result error на merged-root boundary вместо panic, без silent null→object coercion. Per-document root validation меняет fold semantics и требует отдельного решения. Broad panic supervisor не заменяет loader Result contract. Proposed tests: invalid root/normal-error controls и controlled watcher valid→invalid→valid-but-changed recovery. Ничего из этого не реализовано/не исполнено.

Только два Markdown-документа. Нет production patch, моделей, сырых логов, приватных путей, пользовательских данных или сборок. Rust/build/tests/fixtures/runtime/GUI не запускались. Abstract model не runtime evidence. LOC/RSS/latency не измерены; merge публикует исследование, не исправляет production.
