# Desktop: session order no longer depends on UI drag geometry

Base: `Proteus-harness/Proteus-desktop@b93833f5043d1c2f10bb6c40638587f56e591ffc`.

Session marks and the affected UI callers use the same data-order helper directly. Its move, no-op, missing target and cancellation behavior is unchanged. Persisted order and project/pin/branch checks stay in the session model. Preview ordering, gestures, animation, row primitives and the distinct preferences-order helper remain unchanged. No file-format, public protocol or extension contract changes.

Apply in a Desktop checkout with `git apply --check source.patch`, then `git apply source.patch`. `sha256sum -c SHA256SUMS` checks the packet. The receipt records strict application and reversal on current main and its cumulative architecture verification overlay, plus the native test results.
