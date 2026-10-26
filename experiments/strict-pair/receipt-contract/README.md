# Local JSON verification receipt convention v2

Shared typed DTOs and validation for this paired example only. Not an SDK/Core
contract, signature format, permission token, execution lease, or snapshot proof.

`validate_expected` rejects invalid/empty/duplicate coverage configuration.
`verify_receipt` enforces expected identity, exact coverage, current call/cwd,
internal check-ID/digest consistency, explicit bounds and strict field parsing.
It cannot detect a consistent false statement from a dishonest trusted source.

See the [paired contract documentation](../README.md).
