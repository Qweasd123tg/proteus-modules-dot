"""Desired behavior check; exit 1 on the current unfixed Desktop."""
import json,sys
from pathlib import Path
results=json.loads(Path(sys.argv[1]).read_text());failures=[]
for case in ['empty','whitespace','newline']:
 before=results[case]['before_launch']['argv'];after=results[case]['after_launch']['argv']
 if after!=before+['--tag','new']:failures.append(f'{case}: existing argv changed: {before!r} -> {after!r}')
if results['env_append']['before_launch']['PREFIX']!=results['env_append']['after_launch']['PREFIX']:
 failures.append('env_append: adding EXTRA changed existing PREFIX')
for f in failures: print('FAIL',f)
assert not failures, f'{len(failures)} unchanged-field preservation invariants failed'
