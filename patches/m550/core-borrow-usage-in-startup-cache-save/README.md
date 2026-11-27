# Borrow session usage when saving the startup view

The inline saver borrows the usage returned to the view. The deferred
saver borrows from its already-owned pending transcript. The saved header
still owns its usage, and the writer and revision ordering are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. In the release fixture with 256 stored model requests,
this removes 641 allocation/reallocation requests from the synchronous
cache-save helper. The isolated clone requested 59,008 bytes; the full helper
net byte counts fluctuate slightly across fixtures. The empty-usage control
showed no difference in number of requests. Both builds
passed 23 targeted view tests, including the existing deferred-publish
race test and byte/operation parity with successful and rejected HEAD
publication. No real provider was called.

This is not a startup latency or resident-memory measurement, and does
not remove a data copy in histories with no saved model requests.
