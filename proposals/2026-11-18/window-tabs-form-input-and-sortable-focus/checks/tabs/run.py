#!/usr/bin/env python3
"""Build the pinned native strip functions against a deterministic UI-frame adapter.
python3 run.py DESKTOP_ROOT [RUSTC]; no crate downloads, addons, or application."""
from pathlib import Path
import sys,subprocess,tempfile
here=Path(__file__).resolve().parent;src=Path(sys.argv[1])/'src/ui';rustc=sys.argv[2] if len(sys.argv)>2 else 'rustc'
a=(src/'tabs/arrange.rs').read_text();bar=(src/'tabs/bar.rs').read_text()
isolated='struct TabArrangement' in a
assert '.when_some(frame.dragging' in bar and 'self.move_tab' not in a
if isolated:
    for term in ['arrange::frame(&self.tab_arrangement','arrange::hover(\n                                    &arrangement','&this.tab_arrangement','arrange::record(&arrangement','this.move_tab(&dragged.id, dropped.id, before, window, cx)']:assert term in bar,term
    assert 'tab_arrangement: Default::default()' in (src/'workspace.rs').read_text()
    assert 'pub(super) use arrange::TabArrangement;' in (src/'tabs/mod.rs').read_text()
header=(here/'header.rs.in').read_text()
a=a.replace('use gpui_kit::*;', 'use crate::kit::*;')  # only module-lookup change
tail=(here/'oracle.rs.in').read_text().replace('PARAM,','' if not isolated else 'self,')
if not isolated:tail=tail.replace('type Store=arrange::TabArrangement;','#[derive(Default,Clone)] pub(super) struct Store;')
with tempfile.TemporaryDirectory() as d:
    d=Path(d);(d/'arrange.rs').write_text(a);(d/'run.rs').write_text(header.replace("SUBJECT",str(d/"arrange.rs"))+tail)
    subprocess.run([rustc,'--edition=2024',str(d/'run.rs'),'-o',str(d/'test')],check=True);sys.exit(subprocess.run([str(d/'test')]).returncode)
