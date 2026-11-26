# Modules: release typed workflow input before running the worker loop

The worker bridge owns the task, history, config and runtime while serializing them. It now drops that typed input after serialization succeeds, before passing the JSON string to the workflow. Serialization, decoding, callback and return behavior stay the same. This does not remove either JSON pass. #810 independently concerns the inner JSON string and is not required.

The actual standalone Coding Workflow executable was checked in four exact source variants: stock, bridge only, #810 only and both. Across 24 detached invocations through the locked SDK v3/v22 broker, Single Loop and Codex preserved ordered callbacks, typed results, the missing-history transport error and the empty-history workflow error. The model and dispatcher were fixtures. This did not test current Core integration, persistent checkpoints, cancellation or real sessions. No timing or RAM was measured.

Apply only `source.patch` to the exact Modules owner and preimage in `receipt.json`. No alternate.
