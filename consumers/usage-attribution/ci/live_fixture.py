#!/usr/bin/env python3
"""Fixed authored fixtures only; inherited_pipe alone forks one same-group child."""
import os
import signal
import sys
import time

case, ready = sys.argv[1], int(sys.argv[2])
assert case in ('success', 'nonzero', 'timeout', 'output_cap', 'inherited_pipe', 'injected_wait_failure')
signal.signal(signal.SIGALRM, lambda *_: os._exit(71))
signal.setitimer(signal.ITIMER_REAL, 8)
if case == 'inherited_pipe':
    child = os.fork()
    if child == 0:
        os.close(ready)
        signal.setitimer(signal.ITIMER_REAL, 8)
        time.sleep(30)
        os._exit(72)
os.write(ready, b'ready\n')
os.close(ready)
if case == 'success':
    os.write(1, b'fixture-ok\n')
elif case == 'nonzero':
    os.write(2, b'fixture-nonzero\n')
    sys.exit(23)
elif case == 'inherited_pipe':
    os._exit(0)
else:
    if case == 'output_cap':
        os.write(1, b'x' * 16384)
    time.sleep(30)
