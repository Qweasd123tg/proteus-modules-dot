# Check whether an input is blank without flattening it

The input state tests Unicode whitespace directly on borrowed Rope chunks. The same predicate replaces materializing the input at five boolean-only sites; attachments and other conditions stay in place.

The exact predicate passed 48 native fixture cases. For a 2 MiB whitespace draft the requested peak dropped from 4,194,320 to 256 bytes; an emoji-leading long draft likewise kept only small traversal metadata. This measures the predicate, not an entire render, UI latency or app RAM.
