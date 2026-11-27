# Reuse the Content-Length header line buffer within one frame

Keep one scratch vector for this header block. Clear it before reading
the next line and drop it before allocating the body. Line boundaries,
the aggregate header limit and body length parsing remain in the same paths.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. In a release probe of 10,000 ordinary frames per
reader size, fresh allocation requests went **30,000 → 20,000**.
The fragmented and contiguous multiline controls also used fewer combined
requests, though the contiguous multiline case used more reallocations
(84 → 10,021). This does not measure peak or idle memory.

Both arms passed 16 scoped unit tests and 29 session tests, including a
real local Content-Length round trip. The sandbox suite is not included.
The newline-JSON session-history path does not use this header reader.
