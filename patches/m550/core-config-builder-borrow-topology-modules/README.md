# Borrow the topology module inventory while constructing settings

Do not clone the whole inventory merely to iterate it. Returned settings
still own their fields. Preserve per-slot order and the original sources
for model and hook activation, with no catalog or schema changes.

Exact Core `024fb944a91382026bb2aa5c7b8da65c284d0305`. 58 targeted release tests passed per arm.
The native projection fixture compares complete response bytes after
dropping the source topology. Empty control unchanged; 13 input modules
avoid 105 allocation requests and 3,536 cumulative
requested bytes; 133 avoid 1065 requests and
36,056 bytes. These measurements exclude acquiring the
topology, catalog/schema calls, startup and process PSS. Strict apply
and reversal pass with the preceding compatible settings/replay stack.
