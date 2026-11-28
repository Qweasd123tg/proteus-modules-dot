# Share physical configuration identity between references and write locks

The reference and lock paths now use the same search for a canonicalizable
ancestor. References still parse and restore role selectors. A lock still
uses the physical file only. Missing suffix spelling and save-target
behavior remain distinct and unchanged. No access or file format changes.

Use source.patch for pinned Core, or source-after-stack.patch for the
cumulative tree. Both offline test binaries ran four exact in-process
fixtures, including a temporary symlink and a missing lexical suffix.
