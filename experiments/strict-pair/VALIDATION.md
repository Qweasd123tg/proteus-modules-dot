# Strict-pair v2 validation

This branch is a source-reviewed CI candidate. Runtime validation is pending at
initial publication; no local compile/test pass is claimed.

Run from the repository root with official Rust 1.95.0 and Python 3.11+:

```sh
STRICT_PAIR_DIR=experiments/strict-pair \
PAIRING_REVIEW_MANIFEST=tests/strict-json-pairing/Cargo.toml \
bash scripts/check-strict-pair.sh
```

The gate requires 81 workspace tests and eight independent pairing cases, with
no failed, ignored, measured or filtered tests. It also checks format, the
positive/negative authored producer examples, exact generated policy versus
fixture and TOML, release content digest/bytes, five assertion identities and
call-ID correlation. `validation/` retains logs, source digests and JSON outputs.

These are authored modules against the pinned SDK, including own-executable
wire tests. Reader callbacks/history are synthetic. No actual Core host, live
model, user project/hook, official filesystem reader deployment, crash replay,
concurrency guarantee or receipt authenticity is claimed. A strict policy binds
the configured suite; it cannot make a weak suite semantically useful.

`PUBLICATION.json` maps reviewed source hashes to public paths. Only the independent
manifest's relative dependency paths changed; no Rust source bytes changed.
