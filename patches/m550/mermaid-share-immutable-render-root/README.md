# Share rendered Mermaid roots

The render cache and views share one immutable SVG-bearing root instead of cloning it. Cache caps, owner tracking, rendered bytes and error behavior are unchanged.

Apply `source.patch` to Extensions tree `f3864b8b8bbc147301229cdc4365c2b1795b99ad`. This is the canonical base, not a port to another SDK revision.

The actual Mermaid worker produced the same 15 replies in both arms. With eight identical charts, retained requested memory in the Rust extension fell from 2,094,302 to 474,718 bytes. The first-render peak was unchanged. This is not whole-app PSS.
