# Keep worker response encoding with protocol decoding

Move existing worker JSON response constructors into the protocol frame
module, without changes to their bodies. Response data ownership, fields,
parser, transport limits, dispatch and authority checks stay unchanged.

Use source.patch on pinned Core and source-after-stack.patch on the exact
cumulative tree in the receipt. Four protocol tests and one SDK in-memory
writer test passed on each base. No worker, terminal or tool was launched.
