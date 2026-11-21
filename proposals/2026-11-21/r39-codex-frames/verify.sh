#!/usr/bin/env bash
# Run against the exact repository revision without changing the supplied checkout.
# Set DEPS to a prebuilt rustc dependency directory only for the local cached mode.
set -eu -o pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "${1:?provide Proteus-desktop checkout}" && pwd)
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
cd "$work"
if [[ -n ${DEPS:-} ]]; then
    git -C "$repo" archive "$base" crates/codex-client | tar -xf -
    git init -q
    opts=(--edition=2024 -L dependency="$DEPS" -C opt-level=2 -C debuginfo=0 -C strip=symbols -C link-arg=-fuse-ld=lld --extern serde="$DEPS/libserde-780a710be38d9f70.rlib" --extern serde_json="$DEPS/libserde_json-9aca34a9012bed43.rlib" --extern async_channel="$DEPS/libasync_channel-b36713eeb7071719.rlib")
    export CARGO_PKG_VERSION=0.1.0-alpha.3
    export CARGO_MANIFEST_DIR="$PWD/crates/codex-client"
else
    git clone -q --no-checkout "$repo" repo
    cd repo
    git checkout -q --detach "$base"
    export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-"$work/target"}
fi
process=crates/codex-client/src/process.rs
crate=crates/codex-client/src/lib.rs
for arm in stock candidate; do
    echo "=== $arm ==="
    if [[ $arm == candidate ]]; then
        git apply --check --whitespace=error-all "$here/source.patch"
        git apply "$here/source.patch"
    fi
    rustfmt --edition 2024 --check "$process"
    if [[ -n ${DEPS:-} ]]; then
        rustc "${opts[@]}" --test "$crate" -o unit
        ./unit --test-threads=1
        rustc "${opts[@]}" --crate-type=rlib --crate-name=proteus_codex_client "$crate" -o libproteus_codex_client.rlib
        rustc "${opts[@]}" --extern proteus_codex_client=libproteus_codex_client.rlib --test crates/codex-client/tests/transport.rs -o transport
        ./transport --test-threads=1
    else
        cargo test --locked -p proteus-codex-client
    fi

    # Supply the same probe with a one-line adapter for each private reader API.
    cp "$here/probe.rs" crates/codex-client/src/r39_probe.rs
    printf '\n#[cfg(test)]\n#[path = "r39_probe.rs"]\nmod r39_probe;\n' >> "$process"
    probe=crates/codex-client/src/r39_probe.rs
    printf '\nfn drive(r: &mut impl BufRead, limit: usize, mut emit: impl FnMut(&[u8]) -> Result<(), Error>) -> Result<(), Error> {\n' >> "$probe"
    if [[ $arm == stock ]]; then
        echo 'while let Some(line) = read_frame(r, limit)? { emit(&line)?; } Ok(()) }' >> "$probe"
    else
        echo 'read_frames(r, limit, &mut emit) }' >> "$probe"
    fi
    if [[ -n ${DEPS:-} ]]; then
        rustc "${opts[@]}" --test "$crate" -o unit
        ./unit framing_allocations --nocapture --test-threads=1
    else
        cargo test --locked --release -p proteus-codex-client --lib -- framing_allocations --nocapture --test-threads=1
    fi
    git -C "$repo" show "$base:$process" > "$process"
done
