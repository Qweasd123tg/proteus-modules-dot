"""Insert the pinned conformance function into a no-window binary, unchanged."""

import argparse
from pathlib import Path

PRELUDE = '''#![allow(dead_code)]
#[path="../declarative/mod.rs"] mod declarative;
#[path="../preferences.rs"] mod preferences;
use proteus_diff as diff;
use declarative::widget;
mod scope { pub mod official {
use crate::declarative::protocol::*;
pub '''
EPILOGUE = '''
} }
fn main(){ scope::official::shipped_processes_conform_to_the_public_ui_protocol(); println!("pinned conformance body passed");}
'''


def prepare(desktop, runner):
    source = (desktop / "src/declarative/protocol.rs").read_text()
    start = source.index("fn shipped_processes_conform_to_the_public_ui_protocol()")
    # The pinned module has no further items before its closing brace.
    end = source.index("\n    }\n}", start) + 6
    function = source[start:end]
    assert function.strip().endswith("}")
    out = runner / "src/bin/stock_gate.rs"
    out.parent.mkdir(exist_ok=True)
    out.write_text(PRELUDE + function + EPILOGUE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desktop", type=Path)
    parser.add_argument("runner", type=Path)
    args = parser.parse_args()
    prepare(args.desktop, args.runner)
