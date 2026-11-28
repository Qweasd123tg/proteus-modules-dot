# Modules: keep the Codex and repo-aware context profiles independent

Base: `Proteus-harness/Proteus-modules@b476a8cca8f0906455753014622d8fbdc08e7899`.

Codex no longer constructs a full repo-aware configuration to call four shared context providers. Each profile passes only the inputs the shared helper consumes. Both config schemas, file checks, provider order, request payloads and result tagging remain unchanged. A configured memory provider still receives limit zero, while search at limit zero still dispatches nothing.

Apply in the Modules checkout with `git apply --check source.patch`, then `git apply source.patch`. `sha256sum -c SHA256SUMS` checks the packet. The receipt records strict application and reversal on current main and its cumulative architecture overlay, and the selected native tests. Provider tests use in-memory fakes, without external tools, providers or a real model.
