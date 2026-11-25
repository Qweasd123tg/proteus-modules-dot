# Desktop: reuse tightly allocated Codex rows in the sidebar

The existing small-catalog or short-page path already owns each decoded Codex row. Move tightly allocated fields into the sidebar row instead of copying them. Fields with spare capacity still get a tight copy, as before. The wide path, page cursor, delete handling and result order do not change.

A detached Rust fixture ran the lifted Thread List JSON producer and sidebar callback, with a synthetic service and the pinned ordered serde_json. All 11 ABBA fixture cases and the separate producer controls passed: rows, order and retained capacities matched. Where a 50-row page takes the small-catalog path, the measured callback requested 1 allocation instead of 147, and 436 bytes instead of 2,237. This is the already decoded callback scope, not a GUI, network, app RAM or latency result.

Both source leaves apply and reverse directly on current Desktop and compose with #684 in both orders.
