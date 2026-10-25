# Strict-pair v2 validation

Remote authored validation passed on commit
`2a840e4c9e92a77b3ab3608cefde186d819cfd03`:
[push run 40246122819](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40246122819).
All strict-job steps succeeded, including source recheck and artifact upload.
The first artifact also bundled inherited baseline files; only its `strict-pair/`,
strict log/digests and toolchain outputs constitute this feature's evidence.
Subsequent uploads select those paths explicitly. No local compile/test pass is
claimed; remote execution used official Rust/Cargo 1.95.0 on Ubuntu 24.04.

Run from the repository root with official Rust 1.95.0 and Python 3.11+:

```sh
STRICT_PAIR_DIR=experiments/strict-pair \
PAIRING_REVIEW_MANIFEST=tests/strict-json-pairing/Cargo.toml \
bash scripts/check-strict-pair.sh
```

The run passed 81 workspace tests and eight independent pairing cases, with
no failed, ignored, measured or filtered tests. It also checks format, the
positive/negative authored producer examples, exact generated policy versus
fixture and TOML, release content digest/bytes, five assertion identities and
call-ID correlation. `validation/` retains logs, source digests and JSON outputs.

These are authored modules against the pinned SDK, including own-executable
wire tests. Reader callbacks/history are synthetic. No actual Core host, live
model, user project/hook, official filesystem reader deployment, crash replay,
concurrency guarantee or receipt authenticity is claimed. A strict policy binds
the configured suite; it cannot make a weak suite semantically useful.

The separate `tests/strict-ci-controls` Python suite tests the artifact validator
using invented records/logs. Its 18 controls are not Rust product tests and are
reported separately.

`PUBLICATION.json` maps reviewed source hashes to public paths. Only the independent
manifest's relative dependency paths, README validation wording and profile comment
changed; no Rust source or fixture semantic bytes changed. `CI_VALIDATION.json`
records the initial successful exact revision and output digests.
