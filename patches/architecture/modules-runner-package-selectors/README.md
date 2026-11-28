# Use Cargo package selection for test fixture preparation

The Modules runner reads explicit package selectors before the argument
separator. Equivalent selector spellings trigger the same existing setup.
A test name or a libtest argument no longer looks like a selected package.
The Cargo command and each base's fixture implementations stay unchanged;
uncertain storage scopes still resolve the pinned harness.

Apply source.patch to pinned upstream or source-after-stack.patch to the
cumulative tree in receipt.json. Verification used isolated Python mocks
for all subprocess operations, not real Cargo, installers or workers.
