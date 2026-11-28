# Remove the domain layer's reverse imports of runtime contracts

Move two existing, passive serialized types, ToolTerminalRef and
ModelCallOrigin, to the domain layer. The old public paths are preserved
by direct re-exports. The wire format and runtime contracts are unchanged.

The same strict patch applies to the two exact sources in the receipt.
The contracts-only in-memory fixture checks old and new type paths,
terminal field encoding and rejection, and both origin spellings.
