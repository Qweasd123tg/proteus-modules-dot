# Уточнение слоя проверки: correction-memory wire cases

26 октября2026. Исходный synthesis snapshot `8a3837a0f02988e77e52adb1a080196bee2928e1a3d8b0afc52935804e087311` сохранён. Это обязательная поправка к STATUS.md и строке E02 в ROADMAP.md/roadmap.json, **не новое выполнение тестов**.

В frozen R17 `tests/wire.rs` три теста, но только два создают Worker и запускают собственный executable:

1. `actual_binary_restart_recovers_same_outcome_without_callback` — authored restart case.
2. `wire_cancellation_while_verifier_pending_does_not_bind_operation` — authored cancellation case.
3. `wire_reader_refuses_oversized_or_incomplete_frames_before_unbounded_read` — pure bounded-frame helper case, без запуска binary.

Правильная формулировка: **3 wire-file cases = 2 own-binary (restart/cancellation) + 1 framing helper; все uncompiled/unrun**. Прежние сокращения «wire restart3» и «three wire-restart cases» завышали число случаев этого слоя, а не число реально прошедших тестов: runtime никогда не заявлялся.

Общее число frozen R17 остаётся58, отдельной raw-compatible revision —69. Четыре actual-module pairing cases также unrun и не становятся Core integration. Эта поправка не меняет implementation/source snapshot и не утверждает SQLite/SDK/process execution.

Основание: source inspection frozen R17 test functions and Worker construction, `tests/wire.rs:27–45,153–258`; файл дополнительно hash-bound в accompanying correction receipt. При переносе synthesis следует использовать эту точную классификацию вместе с отдельным LiveKit reply-status уточнением.
