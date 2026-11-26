# Core: reuse checked section manifests on warm full reads

The existing header read still checks all three section manifests. Full warm model and transcript readers now carry borrowed handles from that checked header rather than rechecking each manifest before visiting its pages. Named full transcript reads likewise reuse the checked transcript manifest. For valid manifests, the code path goes from six to three section checks on either full warm read, and from four to three on a named full transcript. These are counts from source, not latency or memory measurements.

Physical reads, content hashes, typed body decoding, row counts, source/revision guards and latest-page handling remain unchanged. This does not remove a durable journal pass or change cache formats, validation of untrusted input, or the public wire.

In an isolated Rust 1.95 build, 35 focused Core tests passed. The two added cases cover ordered physical reads, a source change during read, exact pinned history, malformed unused manifests and incorrectly typed body data. No Desktop timing, application memory or end-to-end speedup was measured.

Use `source.patch` only on the exact Core owner and four path preimages listed in `receipt.json`. There is no alternate. The patch can be applied independently of #799.
