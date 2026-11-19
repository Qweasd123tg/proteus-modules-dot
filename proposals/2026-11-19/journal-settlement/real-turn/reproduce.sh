#!/bin/sh
set -eu
here=$(CDPATH= cd "$(dirname "$0")" && pwd)
src=$1
work=$2
test ! -e "$work"
mkdir -p "$work"
git -C "$src" archive 8ea2cdaf4195ae24e941354f68d4e97335d139d7 | tar -x -C "$work"
cd "$work"
git apply "$here/observe.patch"
cat "$here/probe-first.rs" >> crates/proteus-core/src/app_server/http/tests/session_reads.rs
: "${PROTEUS_TEST_REFERENCE_MODULE:?set absolute path to the same pin reference worker}"
: "${PROTEUS_TEST_SESSION_STORAGE_MODULE:?set absolute path to the same pin release worker}"
PERF7_CASES="${PERF7_CASES:-100,2000,5000}" cargo --config 'profile.release.package.proteus-core.opt-level=1' test --release --locked -p proteus-core --lib perf7_real_turn_fixed_active_history -- --nocapture --test-threads=1
