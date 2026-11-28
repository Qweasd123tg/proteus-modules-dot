# Desktop: separate module.json from provider discovery

Base: `Proteus-harness/Proteus-desktop@dd51ad4af74756dacf5b2473a758a3109c1fce80`.

The installer and provider discovery now use the same existing module manifest types and validators directly. Installation no longer imports discovery for these definitions. Each caller retains its existing admission, checksum, executable, path, and publication checks. Inventory keeps its permissive presence projection. No changes to module formats, credential access, authentication execution, Extension protocol, or visual design.

Apply in a Desktop checkout with `git apply --check source.patch`, then `git apply source.patch`. Verify packet files with `sha256sum -c SHA256SUMS`. The receipt records strict apply and inverse on main and its cumulative verification overlay, plus native tests using synthetic files and no program launch.
