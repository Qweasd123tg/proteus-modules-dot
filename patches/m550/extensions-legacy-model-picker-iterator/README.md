# Model picker: build legacy choices directly from borrowed values

The legacy Model picker no longer clones each option into a temporary list before building the real picker. It reads options in order and copies each value only into the final widget. Names without a provider prefix stay borrowed until then. The modern grouped picker and the row-building logic used by other SDK picker callers are unchanged.

A detached Rust proof used the package's pinned preserve-order JSON profile. All nine fixtures and 36 ABBA operations passed byte-for-byte ordered output checks inside the proof. In the 64-option fixture, requests fell from 602 to 473, gross requested bytes from 41,171 to 33,555, and peak requested bytes from 39,991 to 32,375. In the 256-option fixture without a catalog, requests fell from 2,329 to 1,816, and peak requested bytes from 156,955 to 125,211. Missing/empty options and requested retained bytes were unchanged.

These results cover one legacy picker build, not grouped-pick behavior, UI latency or process RAM. Raw wire bytes were not captured separately. The patch applies and reverses directly on both pinned Extensions owner and Desktop-packaged revisions, with no prerequisite.
