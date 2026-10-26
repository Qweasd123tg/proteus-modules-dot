"""Bounded pipe capture reused from the reviewed authored Core-pair helper.
No Core or parser execution is performed merely by importing this module.
"""
import os
import selectors
import signal
import subprocess
import time


def capture(process, timeout=90, max_bytes=2 * 1024 * 1024):
    """Bound each pipe independently, including descendants holding a pipe open."""
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    for name in buffers:
        stream = getattr(process, name)
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    error = None
    try:
        while selector.get_map() or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"{timeout}-second probe timeout")
            for key, _ in selector.select(min(remaining, 0.1)):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                buffer = buffers[key.data]
                available = max_bytes - len(buffer)
                buffer.extend(data[:available])
                if len(data) > available:
                    raise RuntimeError(f"{key.data} exceeds {max_bytes}-byte capture limit")
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
    except BaseException as failure:
        error = repr(failure)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            error += "; controller reap exceeded 5 seconds"
        error += "; controller group kill attempted; component-owned descendant cleanup unproven"
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    decoded = []
    for name in ("stdout", "stderr"):
        try:
            decoded.append(bytes(buffers[name]).decode("utf-8"))
        except UnicodeDecodeError:
            error = (error + "; " if error else "") + f"{name} is not UTF-8"
            decoded.append(bytes(buffers[name]).decode("utf-8", errors="replace"))
    return decoded[0], decoded[1], error
