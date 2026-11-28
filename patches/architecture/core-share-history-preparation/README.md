# Let live runtime and replay share Core history preparation

Standalone Core patch for `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify the packet with `sha256sum -c SHA256SUMS` and run `git apply --check source.patch` before applying it. The same patch is compatible with the verified Core stack through #957.

History update preparation and the existing compaction validator now belong to one private Core module. Live runtime, checkpoint handling and replay call it directly. Replay no longer goes through live runtime to get this validator. The code that writes, reconciles or refreshes live history remains under runtime.

The rules for the persisted user message, declared compactions and allowed new messages are unchanged, as are the owned-history buffer reuse and durable revision checks. No public protocol, storage, model or tool implementation changes. See `receipt.json` for the exact applicability and targeted native tests. The app-server tests use synthetic signals and pinned local storage/model fixtures.
