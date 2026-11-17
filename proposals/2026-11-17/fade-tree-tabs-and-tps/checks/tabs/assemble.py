"""Assemble a pure in-memory ordering/allocation probe from an exact UI source."""
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
here=Path(__file__).parent
def function(signature):
    start=src.index(signature)
    op=src.index('{',start)
    balance=1
    for i in range(op+1,len(src)):
        balance += (src[i]=='{')-(src[i]=='}')
        if not balance:
            return src[start:i+1]
    raise ValueError(signature)
parts=['pub(super) fn hover(', 'pub(super) fn drop_before(', 'fn others', 'fn clamp(']
Path(sys.argv[2]).write_text((here/'head.inc').read_text()+'\n'.join(map(function,parts))+(here/'tail.inc').read_text())
