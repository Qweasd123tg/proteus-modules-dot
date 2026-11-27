# Skip a second walk over prompt history with no tool calls

While collecting the complete set of result IDs, note whether any native
ToolCall was seen. If none was seen, no synthetic abort reply can be
needed. Histories with calls still scan all parts of the original
history twice and use the original result matching and insertion logic.

Exact Modules basis: f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
The separate 5,000- and 50,000-part text fixtures drop from 10,000 to
5,000 and 100,000 to 50,000 part visits. The empty, result-only, fulfilled
late-call and missing-call fixtures retain typed semantics and order.
Seven offline checks pass per arm and both standalone optimized
libraries build. No CPU time, memory, or end-to-end startup claim.
