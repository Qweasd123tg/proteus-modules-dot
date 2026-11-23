# Core Git status: fixed borrowed field slots

Apply `source.patch` to the exact Core V4 source
`Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`.
Only `crates/proteus-core/src/app_server/http/workspace/git/status.rs` changes.

The porcelain-v2 scanner expects 9, 10, or 11 fields for tracked, rename,
or conflict records. It puts the same borrowed `splitn` fields in a fixed
array instead of a scratch Vec. A missing field is still an error; an
empty field is not missing. Git arguments, byte/row limits, NUL framing,
UTF-8 and rename validation order, literal paths and prefix handling,
private index records and visible fields are unchanged. No config,
security, or write-policy changes. The earlier #280 Git log change and
#537 profile watcher change touch different source files.

The pinned Rust 1.95 debug and optimized builds each passed seven paired
tests. The proof extracts the scanner and its branch/XY helpers from
both exact files, plus the original NUL framing, stage formatter, and
limits. Shims stand in for the runner, prefix lookup and error DTO.
The fixture compares all result fields (including private index bytes),
the inert call order, and error precedence. It includes 5,688 generated
and cutoff pairs in addition to explicit malformed, UTF-8, rename,
prefix and limit cases.

In each build mode, the same 1,000 synthetic tracked/rename/conflict
records produced these allocator requests within the inert scan:

| | Stock | Fixed fields |
| --- | ---: | ---: |
| Allocations | 2,337 | 1,337 |
| Reallocations | 2,009 | 9 |
| Alloc + realloc requested bytes | 881,736 | 433,736 |

The counter includes remaining scan allocations; it counts requested
sizes, not live memory. This is not a latency, peak/RSS, real Git,
HTTP/Serde or whole Core validation.

To reproduce, supply the **unpatched** pinned source and an existing
private scratch directory. The script verifies Git-blob and SHA-256
identities, applies and reverses the patch exactly without Git, and
compiles only the inert source lift with the pinned compiler. No Cargo,
Git subprocess, network or real working tree is used in the proof.

```sh
ws="$CORE/crates/proteus-core/src/app_server/http/workspace"
sha256sum -c SHA256SUMS
python3 -B proof.py --stock "$ws/git/status.rs" --git-ref "$ws/git.rs" \
  --revision-ref "$ws/git/revision.rs" --workspace-ref "$ws.rs" \
  --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
