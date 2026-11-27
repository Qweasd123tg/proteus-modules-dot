# Allow a standalone worker SDK build without the host broker

Standalone patch for Proteus Core `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify `sha256sum -c SHA256SUMS` and apply `source.patch` to a detached Core checkout.

Both SDK and protocol continue enabling `host-broker` by default. An external worker can use `proteus-module-sdk = { …, default-features = false }` and leave out the host broker and its process-host dependency, provided another normal dependency does not re-enable it. Consumers that already disabled defaults but still use the host API must explicitly enable `host-broker`. Conformance CLI always enables the host side; SDK process interop tests retain their host fixture through dev dependencies.

The shared protocol identifier, frame/authority validation, 8 MiB default, allowed maximum and host queue policy have not changed. The independent worker and generic process-host defaults must agree whenever the host is compiled. No other repository is repinned or migrated. See receipt.json for native checks, disposable external consumer and exact Git evidence.
