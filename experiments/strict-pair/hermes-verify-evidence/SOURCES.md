# Источники и атрибуция

Самостоятельная реализация по идее bounded verification-before-stop. Python-код
Hermes не копировался; совместимость с его API/ledger не заявляется.

* Hermes `8084684936a951e6c539675f8f81e5b5c35b866f`:
  [verification_stop.py](https://github.com/NousResearch/hermes-agent/blob/8084684936a951e6c539675f8f81e5b5c35b866f/agent/verification_stop.py)
  — opt-in gate, bounded attempts, пассивный verification ledger;
  [turn_stop_gates.py](https://github.com/NousResearch/hermes-agent/blob/8084684936a951e6c539675f8f81e5b5c35b866f/agent/turn_stop_gates.py)
  — реальное включение gate в stop path. Hermes сам по себе не использует нашу receipt.
* Proteus core `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`:
  [hook.rs](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/hook.rs)
  — `BeforeStop`, `ContinueTurn`, ordered chain;
  [reviewed_workflow.rs](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/reviewed_workflow.rs)
  — checkpoint перед stop review, host-owned attempt/cap;
  [SDK](https://github.com/Proteus-harness/Proteus-core/tree/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-module-sdk)
  — публичные DTO и процессный runtime, не локальный fork;
  [starter](https://github.com/Proteus-harness/Proteus-core/tree/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/examples/modules/rust-tool)
  — standalone workspace и exact dependency pin.

Дата чтения: 2026-10-25. Статическое чтение не означает execution-tested integration.
