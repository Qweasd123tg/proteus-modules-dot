# Desktop: avoid temporary tree roots during saved height-cache import

One production change against exact Desktop M401
(`c65544b6854c6c98b48b9189bfa328a87d866696`, identical Desktop bytes to
M400). `source.patch` changes the scalar geometry reconstruction loop
and adds one companion map test. It does not change transcript entries,
disk format/checks, height-cache limits, renderer selection, or Node.

The pinned `gpui-pre-sum-tree=0.3.10` implements `from_item(x)` as
`new(); push(x)`, and `push(x)` builds and appends the same singleton.
The importer previously created both an empty tree and a singleton for
every slice. If the singleton joined its predecessor, it also split
the consumed singleton into an empty right tree. On a join it now uses
the same predicate and `update_last` arithmetic; append-empty in the
old path was a no-op. For a non-join, the same singleton is appended
directly. No bulk packing or floating point reassociation is used, so
the order of additions, tree grouping and per-row pixel decisions are
unchanged.

## Native comparison

The production **Store** writes and drains the exact scalar file on a
previous disk worker. The reopening **HeightCache::bind** uses the real
background read path, preference fingerprint, disk header/validation
and then **HeightCache::import**. Both stock and candidate compile the
same three modules plus their original tests against exact locked
dependencies. No GPUI/compositor or app-server is substituted as if it
were running. Allocator counters measure only the single UI-thread
import, after the asynchronous scalar snapshot arrives.

| Synthetic reopened scalar geometry | Stock requested bytes / calls | Candidate requested bytes / calls |
| --- | ---: | ---: |
| 50,000 rows, 16,000 saved spans | 25,792,248 / 34,667 | 13,887,504 / 18,666 |
| Same with newer native facts and disclosure exclusion | 25,795,224 / 34,671 | 13,888,992 / 18,668 |
| 50,000 rows under real map pressure and protected native window | 27,862,056 / 37,449 | 15,025,824 / 20,196 |
| Changed revision, 3,719-row proven prefix | 1,999,872 / 2,688 | 1,076,568 / 1,447 |
| 50-row small reopen | 32,736 / 44 | 17,856 / 24 |
| Result invalidated by a changed layout while outstanding | 0 / 0 | 0 / 0 |

32 stock and 33 candidate tests pass. All six differential digests
match: exact floating-point bits for every row's prefix and estimate,
targets at the prefix and one ULP in either direction, freshness,
normalized durable values, span/revision and accounting. Retained
allocator delta is unchanged; dense peak is unchanged. Gross
allocation requests are **cumulative work**, not memory that was live
at once, process RSS/PSS, time-to-first-frame or no-cache startup.
Cases cover zero and signed-zero input, fractions, coalescing, a partial
last record, wrong layout and pre/post-import compaction. Existing disk
corruption/truncation and admission tests run unchanged.

`composition.json` records exact pre/post Git blobs, independent
ordering with prior #639 and #642, and all scoped source bytes. No
server/API/JSON map changes, so JSON insertion-order mode does not
apply. Run with Rust 1.95 and the locked Cargo vendor directory:

```sh
python3 verify.py --vendor /path/to/vendor
```
