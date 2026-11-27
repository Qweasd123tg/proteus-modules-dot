# Move the source call ID into the transcript binding index

The replay scan already owns the binding. Move the call ID into the
index key and keep only the child thread, session ID and session directory
as the value. Finishing a card still borrows that value. The durable journal
format and ownership, admission and duplicate validation are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 155 targeted release tests passed per arm.
The validated late-binding test still attaches a stable child link to the
original completed card. The renderer probe matches card IDs, status, and
metadata for zero, one and 256 call IDs. It deliberately feeds two bindings
per ID to exercise existing replacement semantics in the private scan.
Durable validation still rejects duplicate bindings.

The no-binding control is unchanged. The 256-ID renderer fixture saves
512 allocation requests and 37,792 cumulative bytes.
This measures allocation traffic during replay, not whole-app time or PSS.
Strict forward and reverse apply checks pass alone and with Dot #908 in
both orders.
