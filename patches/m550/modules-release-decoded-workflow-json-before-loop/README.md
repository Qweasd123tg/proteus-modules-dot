# Modules: release decoded workflow JSON before running the loop

The four Rust Coding Workflow implementations now hand their internally generated JSON string to the private decoder. The string drops when decoding returns the owned request, before the loop or any host callback. The serialized buffer and typed input still coexist during parsing. This does not remove an encode or parse, change the external wire format, or release the upstream worker's typed copy.

Direct Rust 1.95 library tests with the same locked dependency set passed 116 on stock and 117 on the exact candidate. Focused reruns cover supported workflow paths and preserve the typed parse error. The separate standalone worker was not run end to end; no memory, timing or durability measurement was made.

Apply only `source.patch` at the exact Modules owner and preimage in `receipt.json`. No alternate. Core #809 is an independent change. The prior unbuilt W175 variant is superseded.
