#!/usr/bin/env python3
"""Actual Analysis release NDJSON with synthetic history and loopback GET only."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/analysis")
SESSION = "/synthetic-session"


def ordinary(single):
    sizes = [4096] if single else [3072, 4096, 4608]
    kinds = ["System", "Developer", "Project"]
    entries = []
    for i, size in enumerate(sizes):
        pattern = f"Synthetic block {i} repeats ordinary display text, without execution. Ж🦀\r\n"
        count = size // len(pattern.encode())
        body = pattern * count + "x" * (size - count*len(pattern.encode()))
        assert len(body.encode()) == size
        entries.append({"kind": kinds[i], "priority": i, "text": body})
    return entries


def malformed():
    return [
        {"kind": {"user": {}}, "priority": False},
        {"kind": "system", "text": None},
        {"kind": "developer", "priority": 1, "text": ""},
        {"kind": "context", "priority": 2, "text": True},
        {"kind": None, "priority": 3, "text": -2.75},
        {"kind": "system", "priority": 4, "text": {"b": [True, None], "a": "Ж"}},
        {"kind": "developer", "priority": 5, "text": '[true,null]\r\n🦀 '},
        {"kind": "context", "priority": {"note": 1}, "text": [1, False]},
        42,
    ]


def message(role, text):
    return {"id": role, "role": role, "parts": [{"payload": {"Text": {"text": text}}}]}


def snapshot(blocks, tool=False):
    if tool:
        data = {"kind": "tool", "call": {"id": "tool-1", "name": "fixture", "args": {}},
                "result": {"ok": True, "output": "result\r\n🦀"}}
    else:
        data = {
            "kind": "model", "exchange_id": "model-1", "origin": "direct",
            "request": {"model": {"provider": "fixture", "model": "fixed"}, "instructions": blocks,
                        "messages": [message("User", "Synthetic test input")],
                        "tools": [{"name": "fixture"}]},
            "response": {"messages": [message("Assistant", "Synthetic test output")],
                         "finish_reason": "Stop", "end_turn": True,
                         "usage": {"input_tokens": 80, "output_tokens": 10}},
        }
    step = {"sequence": 1, "execution_id": "fixture-run", "thread_id": None,
            "started_at_ms": 1000, "finished_at_ms": 1520, "data": data}
    return {"session_id": "fixture", "revision": 4,
            "turns": [{"turn_id": "turn-one", "number": 1, "status": "success",
                       "prompt_preview": "Synthetic task"}],
            "selected": {"turn_id": "turn-one", "task": {"text": "Synthetic task " + "Я"*620},
                         "steps": [step], "output": {"text": "Synthetic outcome"}}}


def plain(value):
    if isinstance(value, str):
        return value
    if value is None:
        return "None"
    if type(value) is bool:
        return "True" if value else "False"
    return json.dumps(value, ensure_ascii=False)


def expected(blocks):
    text = []
    for block in blocks if isinstance(blocks, list) else []:
        block = block if isinstance(block, dict) else {}
        kind = block.get("kind")
        tag = next(iter(kind)) if isinstance(kind, dict) and len(kind) == 1 else plain(kind)
        body = plain(block.get("text", ""))
        text.append(f'[{tag} · приоритет {plain(block.get("priority"))}]\n{body}')
    return len(text), "\n\n".join(text) or "—"


def render(view="main", surface="page"):
    return {"type": "render", "surface": surface, "view": view, "context": "fixture",
            "session_dir": SESSION}


def close(view="main"):
    return {"type": "close", "context": "fixture", "view": view}


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def replay(exe, src, env):
    features = json.loads((src / PKG / "extension.json").read_text())["required_features"]

    def run(record, messages):
        receipts, errors, writes = [], [], []
        assert all(msg["type"] != "action" for msg in messages)

        class API(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                writes.append(self.command)
                self.send_error(405)

            do_DELETE = do_PUT = do_PATCH = do_POST

            def do_GET(self):
                try:
                    route = urlsplit(self.path)
                    assert self.headers.get("Authorization") == "Bearer fixture"
                    assert parse_qs(route.query, keep_blank_values=True) == {"session_dir": [SESSION]}
                    receipts.append(route.path)
                    if route.path == "/sessions":
                        value = [{"session_dir": SESSION, "preview": "Synthetic session", "message_count": 2}]
                    else:
                        assert route.path == "/analysis", route.path
                        value = record
                    raw = json.dumps(value, ensure_ascii=False).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception as error:
                    errors.append(error)
                    self.send_error(500)

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), API) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02},
                                      daemon=True)
            thread.start()
            try:
                hello = {"type": "hello", "protocol": 4, "features": features,
                         "workspace": "/synthetic", "server":
                         {"origin": f"http://127.0.0.1:{server.server_port}", "token": "fixture"}}
                data = b"".join((json.dumps(msg, ensure_ascii=False) + "\n").encode()
                               for msg in [hello, *messages])
                proc = sp.run([exe], cwd=src / PKG, env=env, input=data,
                              capture_output=True, check=True, timeout=20)
            finally:
                server.shutdown()
                thread.join()
        assert not (errors or writes or proc.stderr), (errors, writes, proc.stderr)
        frames = [json.loads(line) for line in proc.stdout.splitlines()]
        assert all(frame["type"] == "view" and frame["session_dir"] == SESSION for frame in frames)
        return proc.stdout, tuple(receipts), frames

    cases = []
    for name, blocks in (
        ("one", ordinary(True)), ("three", ordinary(False)),
        ("malformed", malformed()), ("empty-list", {"not": "a vector"}),
    ):
        record = snapshot(blocks)
        events = [render(), render(), render("sibling"), close("sibling")]
        if name == "three":
            events += [{"type": "event", "event": "run_settled", "context": "fixture",
                        "session_dir": SESSION}]
        events += [close()]
        raw, reads, frames = run(record, events)
        extra = name == "three"
        assert reads == (("/analysis", "/sessions", "/analysis") if extra else ("/analysis", "/sessions"))
        assert [f["view"] for f in frames] == ["main", "main", "sibling"] + ["main"]*extra
        assert all(f["root"] == frames[0]["root"] for f in frames)
        count, body = expected(blocks)
        nodes = list(walk(frames[0]["root"]))
        disclosure, = [node for node in nodes if node.get("id") == "1:instructions"]
        height = min(360, max(48, 16+18*sum(max(1, (len(line)+109)//110) for line in body.splitlines())))
        assert disclosure == {"type": "disclosure", "id": "1:instructions",
                              "label": f"Инструкции · {count}", "open": False,
                              "children": [{"type":"code","id":"analysis-1:instructions",
                                            "text":body,"language":"text","height":height,"wrap":True}]}
        full, = [node for node in nodes if node.get("id") == "analysis-1:raw"]
        assert full["language"] == "json" and json.loads(full["text"]) == record["selected"]["steps"][0]
        task, = [node for node in nodes if node.get("id") == "analysis-turn:turn-one:task"]
        assert task["text"] == record["selected"]["task"]["text"]
        cases.append((name, raw, reads))

    raw, reads, frames = run(snapshot([], True), [
        render(), close(), render("preview", "preview"), close("preview")
    ])
    assert reads == ("/analysis", "/sessions")
    assert [f["view"] for f in frames] == ["main", "preview"]
    assert not any(n.get("id") == "1:instructions" for f in frames for n in walk(f["root"]))
    assert any(n.get("id") == "analysis-1:output" for n in walk(frames[0]["root"]))
    cases.append(("tool-preview", raw, reads))
    return tuple(cases)
