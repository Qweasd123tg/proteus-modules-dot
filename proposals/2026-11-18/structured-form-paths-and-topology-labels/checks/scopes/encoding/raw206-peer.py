#!/usr/bin/env python3
"""Replay the published #206 raw/peer test unchanged, supplying new UI scope functions."""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import subprocess,sys,tempfile
p=ArgumentParser();p.add_argument('combined',type=Path,help='Desktop tree with #206 raw-search and matching identity patch');p.add_argument('published_peer',type=Path,help='published #206 checks/raw/peer directory (check.py and review.rs.in)');p.add_argument('--rustc',default='rustc');a=p.parse_args()
source=(a.combined/'src/settings/schema.rs').read_text()
lo=source.index('fn push_scope_part(');hi=source.index('pub fn section_scope(',lo)
helpers=source[lo:hi];assert helpers.count('fn ')==2 and 'pub fn form_scope(' in helpers
runner=(a.published_peer/'check.py').read_bytes();oracle=(a.published_peer/'review.rs.in').read_bytes()
assert sha256(runner).hexdigest()=='ebf37dbba462b9b3a51fae052f29b48316afd753430fbef67497d87180ccaa8b'
assert sha256(oracle).hexdigest()=='175eae587ea1efa7c6da1da56f2a3ff9368b2c3f8fe09d959e281e111b764ed1'
with tempfile.TemporaryDirectory() as td:
 t=Path(td);(t/'check.py').write_bytes(runner)
 (t/'review.rs.in').write_bytes(oracle+b'\nmod settings {\n'+helpers.encode()+b'\n}\n')
 subprocess.run([sys.executable,str(t/'check.py'),str(a.combined.resolve()),'--rustc',a.rustc],check=True)
