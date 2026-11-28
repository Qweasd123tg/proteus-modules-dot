# Core: keep the completed-transcript type with event publication

Base: `Proteus-harness/Proteus-core@550603155239238fdf73777d53d77f327d1e7a71`.

The event publisher owns the existing internal completed transcript value, with its same rows, cursor and conversion from in-memory history. The read model supplies it rather than owning a data type the publisher has to import back. Binding refresh still calls the projection as before. No change to event flow, freshness or identity checks, storage, SSE output, or Desktop/extension contracts.

Apply in the Core checkout with `git apply --check source.patch`, then `git apply source.patch`. `sha256sum -c SHA256SUMS` checks the packet. The receipt identifies both strict apply/reverse trees and native tests using in-memory event fixtures, without a storage worker or provider.
