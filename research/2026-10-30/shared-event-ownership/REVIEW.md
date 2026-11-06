# Independent source-only acceptance

Reviewed base: `befd30516aefa6f0a0ad5db9924ad4957160b8dc`.
Final patch SHA-256 independently read: `87aa0e1f52641b015068552faad926aa36e7473ca421a2d7ceefc064ebcc1a17`.

**Accepted as a source-only proposal, not as compiled, tested, benchmarked or deployable code.** No remaining static blocker found in the reviewed diff.

Pinned source inventory is complete: 594 Rust blobs hash-verified; all 589 active Rust files searched and classified. Five `examples/research/` files were hash-verified only, excluded from semantic review according to repository guidance. External Rust consumers are outside this completeness claim. Review found missing raw caller migrations in HTTP turns tests, profile-watch helpers and app-server tests; all three were corrected and independently rereviewed.

Production review confirms one Arc payload shared by both rings; view and pending mutation before freezing; sequenced-before-raw-before-pending-watch ordering; borrowed sequence guard before owned conversion; preserved Shutdown exception, lag/resync/close paths and snapshot revision retry. No new cache, receiver adapter, lock, config, DTO or wire change. Owned subscription output remains independently mutable. Retained Arc owners can extend payload lifetime beyond ring eviction.

HTTP activity uses borrowed classification. ACP clones consumed Runtime data and approval identity for its owned work, without moving fields out of borrowed events. Raw test consumers borrow or explicitly copy required ownership. Reviewed serialization sites do not serialize the new Arc itself; no serde `rc` feature or Contracts change is required by this patch. Documentation explicitly identifies the intentional public Rust API change and unchanged JSON/Box output boundary.

Five new regression cases were read, not run. Their assertions cover shared identities, failed-send ownership, raw lag/lifetime, independent owned output and covered Shutdown. They do not establish runtime behavior, performance or a complete race/closure test gate. Author reports strict forward/reverse patch application and exact-byte comparison; those are static artifact checks, not compilation.

No project code, tests, scripts, Cargo, build, CI or native process execution was authorized or performed during this review. Any execution, publication or adoption requires its separately applicable authority and gates.
