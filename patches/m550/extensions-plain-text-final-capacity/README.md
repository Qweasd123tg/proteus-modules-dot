# Markdown text/plain: reserve the final text and closing tag together

On unescaped text the renderer previously grew the HTML allocation again just
to append `</div>`. The retained rich-text helper then copied the full body to
drop its spare capacity. Reserve the bytes of the final literal run and ending
before appending either. This combines their growth, allowing the existing SDK
to retain the tight owned HTML allocation. Branches that already have capacity
need no allocation. Link and prior escaped spans still use the old append path.
Escaping, URL recognition, output schema, parser/IPC limits and SDK are unchanged.

**Base:** exact 151 native Cargo input files from Extensions M372, tree
`efb04eaac751a7c77d96df32f1031f831615b890` (includes #611). First compared the
locally composed M368+read-back #611 to all 151 M372 bytes/modes including
license symlinks. Only `packages/markdown-render/src/plain.rs` changes; no
dependency, package or lock changes.

**Checks:** on Linux x86_64 and Rust/Cargo 1.95.0, 52 native unit tests, 3
process tests and a paired allocator proof passed in each arm under the
locked Cargo inputs. A real Markdown executable received seven protocol-v4
plain requests, including long Unicode lines, CR/LF, literal NUL, late
escaping, a final URL with an escaped query, HTML-like text, empty input
and close/reopen in another session. Exact serialized responses are
3,213,116 bytes (SHA256 `b0bbd2732530b822fb70e356ba06e012e0ae18cd15b5c41981fe9f4684191a96`).

| Actual plain renderer fixture | Total allocator bytes requested before → after |
| --- | ---: |
| Ordinary 1,080,041-byte HTML | 4,320,574 → 1,080,469 |
| Linked prefix + large final literal run | 293,604,185 → 290,363,762 |
| Late-escaped HTML control | 4,320,579 → 4,320,579 |
| Empty input | 539 → 469 |

Both large improved cases removed one allocation and one reallocation.
The meter counts requested allocator layouts on the calling thread around
the native `plain::render`, including parsing, and verifies exact HTML and
retained capacity. These are cumulative requested bytes, not live heap,
process PSS/RSS, renderer latency, or whole app startup metrics.

**Reproduce** with Rust/Cargo 1.95.0 and the verified locked Cargo vendor:

    python3 proof.py --baseline /path/Extensions-M372-native-inputs.tar.gz       --vendor /path/vendor --work /path/scratch

The test runs in a temporary copy and checks exact application, one-file
mode-preserving change, unchanged lock, native suites, process wire and
allocation controls, then exactly restores all 151 source inputs on reversal.
Only source.patch is the product change.
