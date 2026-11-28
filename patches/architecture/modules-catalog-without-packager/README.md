# Let the source catalog run without the packager

The catalog reads package manifests and writes its JSON through a data-only
helper. It does not import the packager. Catalog output and validation are
unchanged, and catalog entries still point to the same package.py build
command for installation.

Apply source.patch to the pinned upstream base and source-after-stack.patch
to the exact cumulative base in receipt.json. Each variant ran the real CLI
under isolated Python with no packager or build tools, matched baseline bytes,
and rejected a malformed preset without overwriting the prior catalog.
The committed catalog check and Python regression suites passed on both bases.
