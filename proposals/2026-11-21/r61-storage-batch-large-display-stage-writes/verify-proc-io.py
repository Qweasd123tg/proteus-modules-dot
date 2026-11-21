"""Sanity check the kernel's count fields using one owned ordinary local write."""
import os
from pathlib import Path
import tempfile

def io():
    return {k:int(v) for k,v in (line.split(':') for line in Path('/proc/self/io').read_text().splitlines())}
with tempfile.TemporaryFile(dir='.') as f:
    one=io()
    n=os.write(f.fileno(), b'local stage probe\n')
    two=io()
    assert (two['syscw']-one['syscw'],two['wchar']-one['wchar'])==(1,n)
print('one ordinary temporary file write: syscw delta 1 and exactly its byte count')
