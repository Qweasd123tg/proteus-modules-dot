# Core: avoid duplicate lists in the opt-in Python suffix hook

The optional `python_suffix` context-preparation hook retains request-only prefix messages and the selected history suffix. Scan only the prefix with a list iterator. If all its messages survive, return the original list without copying the suffix. Otherwise extend the retained prefix from the same iterator, instead of building a second suffix list and then concatenating.

The input validation, selected user-turn boundary, request-only predicate, output order and row identities are unchanged. This is an opt-in, dependency-free reference hook. Defaults and normal Desktop startup are unchanged.

On a synthetic 8,192-message input that did not shorten, CPython traced about 128 KiB of peak allocations inside the old transform and about 1.1 KiB inside the patched transform. Inputs were allocated before tracing. Both shortening controls also lowered peak allocations; their resulting Python list could retain a little extra capacity. These figures are specific to the transform, not steady or peak Proteus process memory.

The paired checks compare return values and references and exercise both exact Python processes over NDJSON. No Rust supervisor, product startup, or performance benchmark was run.
