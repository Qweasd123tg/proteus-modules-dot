# Exact sources and derivation

* SDK/Core: `Proteus-harness/Proteus-core` at
  `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`, unchanged.
* Inspected reference reader/controller: `Proteus-harness/Proteus-modules` at
  `04114bbe85f179895e2b8553b6169a284caaeae3`, unchanged. This is not claimed to be
  a jointly built SDK/reference release.
* Gate starting point: our published draft PR1 example at
  `29d31fb36397008b7677cd5df4943031e24e8fdf`, copied into this isolated workspace;
  original source/publication trees were not edited.
* Producer starting point: our separately verified standalone v1 milestone;
  its source hash manifest is retained separately. This paired version changes
  producer and consumer together, introducing only the local receipt v2.

The exact inspected upstream file hashes and source links remain in
[producer source notes](json-contracts/SOURCES.md) and the inherited
[gate source notes](hermes-verify-evidence/SOURCES.md). Statements there about
the prior v1 receipt are historical; the paired README and shared DTOs define
this feature. New source/test hashes will be recorded after validation.

Design decisions grounded in those sources: nested read calls retain normal
BoundTools approval/journal/cancellation; AfterTool may transform returned bytes;
the original project_check domain success does not establish runner counts;
BeforeStop history is not a full filesystem/turn attestation. The local strict
contract therefore binds policy/coverage without pretending to add Core-owned
authority, atomicity or cryptographic authenticity.
