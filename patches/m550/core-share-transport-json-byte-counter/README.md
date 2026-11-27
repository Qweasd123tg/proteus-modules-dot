# Use one exact JSON byte counter for the process transport

Both directions now use the same existing compact Serde counter.
Raw wire limits, body and delimiter treatment, exact budget admission
and error ordering stay in the original paths.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. Twelve paired optimized counter samples on an
already parsed 37 MB synthetic storage reply measured **89.9 → 63.2 ms**
versus the former outbound counter. A large synthetic Commit structure
measured **70.9 → 57.1 ms**. Short, escaped and numeric controls retained
exact byte counts. Inbound already used the shared implementation;
this is not a change to its speed or to the worker/GUI.

On each arm, 16 focused unit cases and 29 process-session checks
passed. The unfiltered unit invocation had the same 12 unrelated
bubblewrap namespace failures in both arms on this stand.
