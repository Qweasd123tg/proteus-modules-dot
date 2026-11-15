# Attachment relocation: HOLD, no patch

Bounded source-only follow-up to the already published resume-integrity P2, not a new finding. Core bcbda4435534a296c707a1daa250813d692f68e1, Modules c035142558f0fca43e9772fc0e50ca293abf1531; delivery f88f8a28c9622e756adfcfa26dee157ff85e81af (#131). Start/end refs unchanged. 22 exact source blobs verified in SOURCE-VERIFICATION.json.

## Decisive facts

- The documented stopped-session relocation updates the authoritative workspace and current ImageStore root (runtime-and-events.md:1646–1654; runtime/builder.rs:276–287).
- Admission stores an absolute canonical path in ImageRef; native model encoding consumes that path rather than resolving the durable content id (runtime/images.rs:63–87; model-pack/adapters/images.rs:5–18).
- ImageRef equality includes path. Image parts use Exact canonical-part identity, and the journal validates this identity for history and ModelRequestRecorded. Changing path under the same PartId before these records is not a contract-preserving fix (projection/part_identity.rs:23–29,70; projection.rs:247–250,537–552).
- Shared ModelService holds an adapter and RequestShaper, not a session attachment resolver. BoundModel records the request before start_prepared. Thus late transient materialization is a plausible avenue, not implemented or proven here (model_service.rs:16–38; bound_model.rs:275–306).

## Why no small patch

The root cause is a durable content identity conflated with an execution-location hint. A resume-only rewrite would collide with canonical identity; weakening ImageRef/part equality or inventing new IDs merely to bypass validation is not proposed. A model-only late projection would require a correctly bound resolver with specified session/no-session/detached/auxiliary behavior and an explicit recorded-versus-executed representation contract. Broad identity/DTO changes require coordinated producer, consumer, replay and client work. Those choices have not been validated by this bounded pass.

This is a HOLD on the small candidate, not a proof that a safe repair is impossible. No resolver framework, compatibility shim, path fallback or new permission rule is proposed.

PR34 concerns image IO/ownership, not relocation identity. PR113 and PR131 concern inline tool-result media, not stored user ImageRef. OpenCode's user-image projection explicitly requires inline data; that separate limitation is unchanged and is not evidence that fixing native model relocation alone fixes every workflow.

## Evidence limits

Independent source review: INDEPENDENT-REVIEW.md. The earlier resume-integrity report supplied the historical reproduction; this pass did not repeat it. No project test, import, Rust compile, provider call, filesystem relocation, runtime or benchmark was executed. The investigation produced no production or test patch; this publication adds documentation only. Upstream runtime remains unchanged. Future qualification would need the actual supported relocation scenario, unchanged journal/history identity, new model execution paths, and replay/ordinary-session controls on the selected implementation.
