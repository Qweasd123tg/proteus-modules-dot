# Remove incidental reverse imports into Core

This standalone patch targets Proteus Core `024fb944a91382026bb2aa5c7b8da65c284d0305`. Check `sha256sum -c SHA256SUMS` in this directory, then `git apply --check /path/to/source.patch` in a detached Core checkout.

- A context provider's existing interface is a crate-local leaf. The Core assembly and process adapter use the same trait, but the adapter no longer imports the assembly module for it.
- Home-path expansion is a shared leaf with the same implementation, and the public `core::expand_user_path` path still works. The sandbox uses the leaf directly without changing path handling or sandbox policy.
- MCP runtime tools import the canonical config type from the domain, instead of reaching up to a Core re-export.

This is a source layering change. It removes four direct reverse import sites; the process Workflow still reaches `WorkflowHostRuntime`. No Cargo, IPC, callback, runtime selection, or permission contract changes. The next step is to move Workflow composition (not its authority) out of the transport-facing adapter, with native checkpoint and cancellation coverage.

Validation: 113 native Core release tests passed (path handling, sandbox, bound context, MCP and HTTP). Standalone and exact selected prior source trees apply and reverse; selected-context proof is source-only.
