# Modules: keep OpenCode manifest writing independent of the Rust packager

The optional OpenCode workflow's metadata writer no longer imports the full Rust/Cargo packager. Both entry points use the same small Python helpers for creation presets and atomic JSON. Helper code is loaded relative to the checkout; the optional metadata directory supplies JSON data, not Python imports. Schema, escaping, binary digest, package installation and CLI behavior are unchanged.

Use `source.patch` for Modules `7274147162cb226f05df13a52b4a271fa5619313`; use `source-after-stack.patch` instead on the cumulative tree through #972, where earlier packager edits change context. See the receipt for strict apply/reverse and isolated test evidence. The standalone metadata fixture omits the Rust packager and treats launcher bytes as data. This does not replace or test the real npm/Node install.
