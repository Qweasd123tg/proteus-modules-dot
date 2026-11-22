#!/usr/bin/env python3
"""Synthetic, GET-only loopback replay for the actual release Context executable."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/context")
ONE = "/synthetic-context/" + "segment-" * 7 + "🧪"
TWO = "/synthetic-context/second-É"
THREE = "/synthetic-context/unhydrated"
SAME = {"used": 64000, "max": 128000, "trigger": 100000}
CHANGED = {**SAME, "used": 64001}


def scope(kind, session=ONE, **fields):
    return dict(type=kind, context="fixture-context-window", session_dir=session, **fields)


def render(view, surface="popup", session=ONE):
    return scope("render", session, view=view, surface=surface)


def close(view):
    return {"type": "close", "view": view}


def snapshot(session, state):
    return scope("session_snapshot", session, state=state, entries=[])


def state_update(session, state):
    return scope("session_update", session, update={"type": "state", "state": state})


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def report(tag):
    return {
        "history": {"messages": 12, "estimated_tokens": 64000},
        "tools": {"requested": 2, "finished": 2, "failed": 0, "names": ["fixture"]},
        "latest_usage": {"source": "provider", "phase": "request", "model_provider": "fixture",
                         "model_name": "model", "max_input_tokens": 128000,
                         "compaction_trigger_tokens": 100000, "actual": {"input_tokens": 64000,
                         "cached_input_tokens": 32000, "cache_creation_input_tokens": 0},
                         "categories": [{"name": "messages", "tokens": 60000},
                                        {"name": "tool_results", "tokens": 4000}]},
        "diagnostics": [tag],
    }


def replay(exe, src, env):
    manifest = json.loads((src / PKG / "extension.json").read_text())
    assert manifest["command"] == ["bin/context"] and manifest["session_entries"] is False

    def run(messages, replies=()):
        reads, errors, writes = [], [], []
        assert all(m["type"] not in ("action", "command") for m in messages)

        class Api(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                try:
                    route = urlsplit(self.path)
                    got = parse_qs(route.query, keep_blank_values=True)
                    session, status, marker = replies[len(reads)]
                    assert route.path == "/context" and got == {"session_dir": [session]}, (route, got)
                    assert self.headers.get("Authorization") == "Bearer fixture"
                    reads.append(("GET", route.path, session, status))
                    payload = {"error": marker} if status != 200 else report(marker)
                    body = json.dumps(payload, ensure_ascii=False).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as error:
                    errors.append(repr(error))
                    self.send_error(500)

            def deny(self):
                writes.append(self.command)
                self.send_error(405)

            do_POST = do_PUT = do_DELETE = do_PATCH = deny

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Api) as server:
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True)
            worker.start()
            hello = {"type": "hello", "protocol": 4, "features": manifest["required_features"],
                     "workspace": "/synthetic-context-work", "server": {
                         "origin": f"http://127.0.0.1:{server.server_port}", "token": "fixture"}}
            try:
                data = b"".join((json.dumps(v, ensure_ascii=False) + "\n").encode() for v in (hello, *messages))
                result = sp.run([exe], cwd=src / PKG, env=env, input=data, capture_output=True,
                                check=True, timeout=25)
            finally:
                server.shutdown()
                worker.join()
        assert not (writes or errors or result.stderr), (writes, errors, result.stderr)
        assert reads == [("GET", "/context", session, status) for session, status, _ in replies], reads
        frames = [json.loads(line) for line in result.stdout.splitlines()]
        return result.stdout, tuple(reads), frames

    events = [snapshot(ONE, {"context": SAME}), render("main")]
    events += [state_update(ONE, {"context": SAME, "stream": {"chunk": i}}) for i in range(12)]
    events += [state_update(ONE, {"context": CHANGED}), state_update(ONE, {"context": SAME}),
               state_update(ONE, {"context": CHANGED}), render("sibling"),
               state_update(ONE, {"context": CHANGED, "stream": {"chunk": 99}}),
               close("sibling"), render("sibling"), close("sibling"), close("main"),
               snapshot(TWO, {"context": CHANGED}), render("main", session=TWO), close("main"),
               render("empty", session=None), close("empty")]
    original = "snapshot-a-cold"
    changed = "snapshot-b-retry"
    alias = "snapshot-sibling-refresh"
    reopened = "snapshot-reopened-refresh"
    separate = "snapshot-second-session"
    failed = "fixture refresh temporarily unavailable"
    answers = [(ONE, 200, original), (ONE, 503, failed), (ONE, 200, changed), (ONE, 200, alias),
               (ONE, 200, reopened), (TWO, 200, separate)]
    raw, reads, frames = run(events, answers)
    expected = [("main", ONE, original)] * 14
    expected[13] = ("main", ONE, original)  # 503 keeps old tree under warning; verified below
    expected += [("main", ONE, original), ("main", ONE, changed), ("sibling", ONE, alias),
                 ("main", ONE, alias), ("sibling", ONE, alias), ("sibling", ONE, reopened),
                 ("main", TWO, separate), ("empty", None, "Сессия не открыта.")]
    assert len(frames) == len(expected), [(m.get("view"), m.get("session_dir")) for m in frames]
    for frame, (view, session, marker) in zip(frames, expected, strict=True):
        assert (frame["type"], frame["view"], frame["session_dir"]) == ("view", view, session)
        assert marker in [n.get("text") for n in walk(frame["root"])], (view, marker, frame)
    assert failed in [n.get("text") for n in walk(frames[13]["root"])]
    assert frames[13]["root"]["type"] == "fill"
    assert frames[14]["root"] == frames[0]["root"], "previous key/reply was not retained after 503"
    assert all(f["root"] == frames[0]["root"] for f in frames[:13])
    cases = [("popup", raw, reads)]

    # A render before the first session state is genuinely None in Host. Present
    # state without context, and present null context, encode to the same "null".
    raw, reads, frames = run([render("unhydrated", session=THREE), snapshot(THREE, {}),
                              state_update(THREE, {"context": None}), close("unhydrated")],
                             [(THREE, 200, "snapshot-no-state"), (THREE, 200, "snapshot-null-context")])
    assert len(frames) == 3 and frames[2]["root"] == frames[1]["root"] != frames[0]["root"]
    assert "snapshot-no-state" in [n.get("text") for n in walk(frames[0]["root"])]
    assert "snapshot-null-context" in [n.get("text") for n in walk(frames[1]["root"])]
    cases.append(("state-shapes", raw, reads))

    raw, reads, frames = run([snapshot(ONE, {"context": SAME}), render("activity", "badge"),
                              close("activity"), render("preview", "preview"), close("preview")])
    badge, preview = frames
    assert badge["type"] == "badge" and badge["title"] == "Context: 50%"
    assert preview["type"] == "view" and "Пример/Модель · request" in [
        n.get("text") for n in walk(preview["root"])]
    cases.append(("controls", raw, reads))
    return tuple(cases)


if __name__ == "__main__":
    from base64 import b64encode
    import os
    import sys

    exe, src = map(Path, sys.argv[1:])
    for name, stdout, reads in replay(exe, src, os.environ):
        print(json.dumps([name, b64encode(stdout).decode("ascii"), reads], ensure_ascii=False))
