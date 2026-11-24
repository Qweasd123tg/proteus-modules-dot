# Desktop: share one immutable Codex model catalog per app-server

Model discovery, retry and pagination still run as before. The cache retains the
same Arc slice that Workspace, windows and Chat bindings already expect, instead
of cloning every model record on each chat open. Old tab and menu snapshots keep
their own Arc ownership; no mutable sharing or borrowing crosses the worker boundary.

The bounded native fixture checks exact catalog cache/install ownership with an
in-memory loader, actual Arc/Mutex and threaded controls. 10 A/B/B/A scenarios and
80 allocation ledgers passed. On four warm installs of 64 short records, additional
requested heap retained by the views was 73,376→0 B. With one synthetic 2 MiB
description it was 8,457,160→0 B. The initial catalog still owns its data.
Not a GPUI, Codex process, startup time or PSS benchmark. Exact M441 source, no
prerequisites on the independently verified owner head. See the receipt.
