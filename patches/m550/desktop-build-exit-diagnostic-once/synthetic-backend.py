#!/usr/bin/env python3
"""Synthetic child for native diagnostics tests; performs no network calls."""
import json
import sys

def arg(name):
    return sys.argv[sys.argv.index(name)+1]

profile=arg("--config")
token=arg("--token").encode()
if profile == "invalid-origin":
    print(json.dumps({"type":"http_ready","origin":"http://127.0.0.1:7/invalid"}),flush=True)
    sys.exit(7)
if profile != "died-before-ready":
    print(json.dumps({"type":"http_ready","origin":"http://127.0.0.1:7"}),flush=True)
if profile != "empty":
    # These records arrive only on stderr; the mutex order between two
    # independent readers is deliberately not part of the synthetic oracle.
    for i in range(65):
        if i == 8:
            buf=b"token " + token + b" logged invalid byte: " + bytes([0xff]) + b"\r\n"
        elif i == 60:
            buf=b"\r\n"
        else:
            buf=f"fixture {i:02d} ".encode() + (b"x" * (97000 if profile != "tiny" else 2)) + b"\n"
        sys.stderr.buffer.write(buf)
    sys.stderr.buffer.flush()
sys.exit(7)
