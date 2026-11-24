# Reuse an owned fragment when copying a response

A single large, tightly allocated response fragment can go straight into the clipboard payload. Mixed parts stay ordered and loose buffers are not retained.

Apply `source.patch` to the exact Desktop preimage in `receipt.json`. The isolated native assembly test passed 25 checks. For a two-MiB fragment, material buffer requests went from three to one and requested-heap peak was about halved for both Core and Codex. Mixed responses use fewer allocations without a material peak change. No GPUI, system clipboard or process memory claim.
