"""Bounded transport for one direct Node child; no descendant-settlement guarantee."""
import json
import os
import selectors
import subprocess
import time
from strict_json import loads

MAX_FRAME = 8 * 1024
MAX_REQUEST = 8 * 1024
MAX_STDOUT = 64 * 1024
MAX_STDERR = 16 * 1024


class Worker:
    def __init__(self, command, cwd, environment, deadline, stdout_sink=None, stderr_sink=None):
        self.stdout_sink = stdout_sink
        self.stderr_sink = stderr_sink
        self.deadline = deadline
        self.buffer = bytearray()
        self.stderr = bytearray()
        self.total_stdout = 0
        self.requests = 0
        self.stdout_eof = False
        self.closed = False
        self.nonblocking = set()
        self.selector = selectors.DefaultSelector()
        self.environment = dict(environment)
        try:
            self.child = subprocess.Popen(command, cwd=cwd, env=self.environment,
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, bufsize=0, close_fds=True)
        except BaseException as error:
            try:
                self.selector.close()
            except BaseException as close_error:
                raise RuntimeError(f"spawn failed: {error}; selector close: {close_error}") from error
            raise
        try:
            for stream, name in ((self.child.stdin,"stdin"),(self.child.stdout,"stdout"),(self.child.stderr,"stderr")):
                os.set_blocking(stream.fileno(), False)
                self.nonblocking.add(name)
            self.selector.register(self.child.stdout, selectors.EVENT_READ, "stdout")
            self.selector.register(self.child.stderr, selectors.EVENT_READ, "stderr")
        except BaseException as error:
            cleanup=self.stop(False)
            raise RuntimeError(f"worker setup failed: {error}; cleanup={cleanup}") from error

    def _events(self, deadline):
        remaining = min(deadline, self.deadline)-time.monotonic()
        if remaining <= 0:
            raise TimeoutError("wire response/total deadline exceeded")
        events = self.selector.select(remaining)
        if not events:
            raise TimeoutError("wire response/total deadline exceeded")
        writable = False
        for key, _ in events:
            if key.data == "stdin":
                writable = True
                continue
            remaining_cap = (MAX_STDERR-len(self.stderr)) if key.data == "stderr" else (MAX_STDOUT-self.total_stdout)
            data = os.read(key.fileobj.fileno(), min(8192, max(1, remaining_cap+1)))
            if not data:
                self.selector.unregister(key.fileobj)
                if key.data == "stdout":
                    self.stdout_eof = True
                continue
            if key.data == "stderr":
                if self.stderr_sink is not None:
                    self.stderr_sink(data)
                self.stderr.extend(data)
                if len(self.stderr) > MAX_STDERR:
                    raise ValueError("stderr byte cap exceeded")
            else:
                if self.stdout_sink is not None:
                    self.stdout_sink(data)
                self.total_stdout += len(data)
                if self.total_stdout > MAX_STDOUT or len(self.buffer)+len(data) > MAX_FRAME:
                    raise ValueError("stdout/frame byte cap exceeded")
                self.buffer.extend(data)
        return writable

    def stop(self, graceful):
        if self.closed:
            return self.cleanup
        self.closed = True
        report = {"scope": "direct_Popen_child_only", "reaped": False, "terminated": False,
                  "killed": False, "returncode": None, "error": None, "errors": []}
        def attempt(label, action):
            try:
                action()
                return True
            except BaseException as error:
                report["errors"].append(f"{label}: {type(error).__name__}: {error}")
                return False
        # Failure in one stage must not skip later bounded reap attempts.
        attempt("stdin_close", self.child.stdin.close)
        reaped = False
        try:
            reaped = self.child.poll() is not None
        except BaseException as error:
            report["errors"].append(f"poll: {type(error).__name__}: {error}")
        if graceful and not reaped:
            reaped = attempt("graceful_wait", lambda:self.child.wait(timeout=2))
        if not reaped:
            report["terminated"] = attempt("terminate", self.child.terminate)
            reaped = attempt("terminate_wait", lambda:self.child.wait(timeout=2))
        if not reaped:
            report["killed"] = attempt("kill", self.child.kill)
            reaped = attempt("kill_wait", lambda:self.child.wait(timeout=2))
        report["returncode"] = self.child.returncode
        report["reaped"] = reaped and self.child.returncode is not None
        # Already nonblocking pipes; bounded final drains, no communicate().
        for stream, label, cap in ((self.child.stdout,"stdout",MAX_FRAME),(self.child.stderr,"stderr",MAX_STDERR)):
            if label not in self.nonblocking:
                report["errors"].append(f"skip unconfirmed nonblocking {label} drain")
                continue
            def drain():
                drained = bytearray()
                remaining = max(0, (MAX_STDOUT-self.total_stdout) if label=="stdout" else (MAX_STDERR-len(self.stderr)))
                limit = min(cap, remaining)
                while len(drained) <= limit:
                    try:
                        chunk = os.read(stream.fileno(), min(8192,limit+1-len(drained)))
                    except BlockingIOError:
                        break
                    if not chunk:
                        break
                    drained.extend(chunk)
                if label=="stdout" and drained and self.stdout_sink is not None:
                    self.stdout_sink(bytes(drained))
                if label=="stderr" and drained and self.stderr_sink is not None:
                    self.stderr_sink(bytes(drained))
                if len(drained)>limit:
                    raise ValueError(f"cleanup {label} byte cap exceeded")
                if label=="stdout" and (drained or self.buffer):
                    raise ValueError("unexpected remaining stdout")
                if label=="stderr":
                    if len(self.stderr)+len(drained)>MAX_STDERR:
                        raise ValueError("stderr byte cap exceeded")
                    self.stderr.extend(drained)
            attempt(f"drain_{label}",drain)
        attempt("selector_close",self.selector.close)
        for stream, name in ((self.child.stdin,"stdin"),(self.child.stdout,"stdout"),(self.child.stderr,"stderr")):
            attempt(f"close_{name}",stream.close)
        report["error"] = "; ".join(report["errors"]) or None
        self.cleanup = report
        return report
