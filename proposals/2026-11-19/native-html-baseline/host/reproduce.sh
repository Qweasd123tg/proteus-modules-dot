#!/usr/bin/env bash
# Linux, Rust 1.95, cargo, Python 3, patch; the second argument is a new directory.
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
DESKTOP=$(cd "$1" && pwd)
mkdir -p "$2"; WORK=$(cd "$2" && pwd); mkdir -p "$WORK/bin"
CPU=${CPU:-0}
python3 "$DIR/prepare.py" "$DESKTOP" "$WORK/stock"
python3 "$DIR/prepare.py" "$DESKTOP" "$WORK/after" --patch "$DIR/../candidate/defer-rich-text-only.patch"
for side in stock after; do
  target="$WORK/target-$side"
  common=(--manifest-path "$WORK/$side/Cargo.toml" --target-dir "$target" --release --locked)
  # Use --offline when dependencies already exist locally.
  for entry in 'state-qual scoped time' 'state-qual scoped,heap heap' 'liveprobe scoped live'                'state-qual default default' 'pushcounts scoped push-rich_text' 'pushcounts default push-default'; do
    read -r bin feature output <<< "$entry"
    flags=(); if [[ $feature != default ]]; then flags=(--features "$feature"); fi
    cargo build "${common[@]}" --bin "$bin" "${flags[@]}"
    cp "$target/release/$bin" "$WORK/bin/$side-$output"
  done
done
python3 "$DIR/proof.py" "$WORK/bin" "$DIR/cases.jsonl" "$WORK/proof.json"
python3 "$DIR/run.py" "$WORK/bin" "$DIR/cases.jsonl" "$WORK/timing.json" --cpu "$CPU"
python3 "$DIR/live.py" "$WORK/bin" "$DIR/cases.jsonl" --cpu "$CPU" >"$WORK/live.json"
