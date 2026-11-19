#!/bin/sh
set -eu
here=$(CDPATH= cd "$(dirname "$0")" && pwd)
src=$1
work=$2
test ! -e "$work"
mkdir -p "$work"
git -C "$src" archive 8ea2cdaf4195ae24e941354f68d4e97335d139d7 | tar -x -C "$work"
cd "$work"
git apply "$here/instrumentation.patch"
cat "$here/probe.rs" >> crates/proteus-core/src/app_server/http/tests/sse.rs
: "${PROTEUS_TEST_REFERENCE_MODULE:?set absolute path to pinned worker}"
: "${PROTEUS_TEST_SESSION_STORAGE_MODULE:?set absolute path to pinned release worker}"
cargo test --release --locked -p proteus-core --lib measure_completed_journal_scaling -- --nocapture --test-threads=1
