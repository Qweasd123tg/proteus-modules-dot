# Move standalone streamed messages into persistent history

A standalone MessageCompleted already owns its message. Move it to
persistent history and keep the necessary independent model copy.
Messages on the terminal response or model failure remain borrowed;
the caller still receives their payloads. ID deduplication, selected
tools, ordering, checkpoint and failure paths are unchanged.

Exact Modules basis: f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
In one typed synthetic completion containing 168000 bytes of Unicode
assistant text, the admission loop saved 2 Rust allocation
requests (168160 requested bytes). Duplicate and borrowed batch
admission counts were unchanged. Both histories and checkpoint counts
were identical. Five checks and a standalone optimized library per arm,
including offline stream retry and failure controls. No timing, peak
memory, live provider, or live tool claim.
