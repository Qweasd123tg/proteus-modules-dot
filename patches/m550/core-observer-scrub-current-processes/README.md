# Core history benchmark: avoid re-redacting retired process rows

In the private clone diagnostic, a successful sample updates only the retained rows for its observed process identities. Redact those plus all emitted rows; do not replace already-redacted containers for retired rows. If a sample or redaction is interrupted, retain the original full sweep on the next successful recovery pass.

The real sampler and private observer logic were exercised on inert process fixtures. All 266 successful paired samples matched, including emitted redaction, retained state and counters. Two interrupted attempts verified that the next success also scrubs partial rows from processes that had since exited. In the one-live-process fixture after 262 identity observations, normal redaction visits fell from 263 to two per sample; recovery still visits the full retained set.

This change is limited to the diagnostic observer and does not change shared sampler state or application performance. No actual process sampling, endpoint or product benchmark ran.
