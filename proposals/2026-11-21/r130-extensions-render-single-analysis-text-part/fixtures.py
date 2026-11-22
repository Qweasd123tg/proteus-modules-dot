#!/usr/bin/env python3
"""Uninstrumented Analysis release NDJSON on a read-only synthetic loopback."""
from base64 import b64encode
import http.server
import json
import os
from pathlib import Path
import subprocess as sp
import sys
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/analysis")
SESSION = "/synthetic-analysis/session-🧪"


def message(role, payloads):
    return {"id": "fixture", "role": role, "phase": None,
            "parts": [{"part_id": f"fixture-{i}", "provenance": "user" if role == "User" else "model", "scope": "conversation",
                       "payload": payload} for i, payload in enumerate(payloads)],
            "name": None, "tool_call_id": None, "metadata": {"z": True, "a": None}}


def ordinary(count, role="User"):
    result = []
    for i in range(count):
        size = 2048 + i*512
        pattern = f"Synthetic message {i} for Analysis only. Ж 🧪 e\u0301\r\n"
        full, rest = divmod(size, len(pattern.encode()))
        text = pattern*full + "x"*rest
        assert len(text.encode()) == size
        raw = "\u2003\t" + text + "\r\n\u3000"
        result.append((message(role, [{"Text": {"text": raw}}]), raw.strip()))
    return result


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def controls():
    blank = message("User", [{"Text": {"text": "\u2003\t\r\n\u3000"}}])
    nonstring = message("User", [{"Text": {"text": 42}}])
    missing = message("User", [{"Text": {}}])
    reasoning = message("User", [{"Reasoning": {"text": "fixture reasoning", "signature": None}}])
    empty = message("User", [])
    nonarray = {"parts": {"Text": {"text": "not a row"}}, "role": "User"}
    no_payload = {"parts": [True], "role": "User"}
    malformed_body = message("User", [{"Text": ["not object"]}])
    multitags = {"Text": {"text": "do not use singleton"}, "Image": {"image": "fixture"}}
    lower = {"text": {"text": "do not use singleton"}}
    mixed = [
        {"Text": {"text": " \n A\r\n🧪 e\u0301\tB \u2003 "}},
        {"ReasoningSummary": {"text": "fixture filtered interpretation"}},
        {"Text": {"text": "\t C \r\n"}},
    ]
    return [
        (blank, pretty(blank)), (nonstring, pretty(nonstring)), (missing, pretty(missing)),
        (reasoning, pretty(reasoning)), (empty, pretty(empty)), (nonarray, pretty(nonarray)),
        (no_payload, "null"), (malformed_body, pretty(malformed_body)),
        (message("User", [multitags]), pretty(multitags)),
        (message("User", [lower]), pretty(lower)),
        (message("User", mixed), "A\r\n🧪 e\u0301\tB\nC"),
        (message("User", mixed[:2]), "A\r\n🧪 e\u0301\tB"),
        (message("User", [{"ToolCall": {"call": {"name": "fixture", "args": {"b": True, "a": [1, None]}}}}]),
         'Вызов fixture: {"b": true, "a": [1, null]}'),
        (message("User", [{"FileRef": {"path": "synthetic.txt", "content": "not a file read 🧪"}}]),
         "Файл synthetic.txt\nnot a file read 🧪"),
        (message("User", [{"ToolResult": {"result": {"call_id": "fixture", "output": "body \r\n\u2003"}}}]),
         "Результат fixture:\nbody"),
        (message("User", [{"Image": {"image": "synthetic"}}]), "[изображение]"),
    ]


def snapshot(request, answer, failure=False):
    data = {"kind": "model", "exchange_id": "fixture-call", "origin": "direct",
            "request": {"model": {"provider": "fixture", "model": "fixed"},
                        "instructions": [{"kind": "Developer", "priority": 17, "text": "Static fixture"}],
                        "messages": [msg for msg, _ in request], "tools": [{"name": "fixture"}]}}
    result = [msg for msg, _ in answer]
    if failure:
        data["failure"] = {"kind": "fixture-error", "message": "synthetic partial answer",
                           "completed_messages": result}
    else:
        data["response"] = {"messages": result, "finish_reason": "Stop", "end_turn": True,
                            "usage": {"input_tokens": 80, "output_tokens": 10}}
    step = {"sequence": 1, "execution_id": "fixture-exec", "thread_id": None,
            "started_at_ms": 1000, "finished_at_ms": 1520, "data": data}
    return {"session_id": "fixture", "revision": 4,
            "turns": [{"turn_id": "fixture-turn", "number": 1, "status": "success",
                       "prompt_preview": "Synthetic task"}],
            "selected": {"turn_id": "fixture-turn", "task": {"text": "Synthetic task"},
                         "steps": [step], "output": {"text": "Synthetic outcome"}}}


def render(view="main", surface="page"):
    return dict(type="render", surface=surface, view=view, context="fixture", session_dir=SESSION)


def close(view="main"):
    return dict(type="close", context="fixture", view=view)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def run(exe, src, record, events, routes):
    manifest = json.loads((src / PKG / "extension.json").read_text())
    reads, writes, errors = [], [], []
    assert all(e["type"] in {"render", "close", "event"} for e in events)

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            try:
                route = urlsplit(self.path)
                assert route.path == routes[len(reads)]
                assert self.headers.get("Authorization") == "Bearer fixture"
                assert parse_qs(route.query, keep_blank_values=True) == {"session_dir": [SESSION]}
                reads.append(("GET", route.path, SESSION, 200))
                if route.path == "/sessions":
                    payload = [{"session_dir": SESSION, "preview": "Synthetic session", "message_count": 2}]
                else:
                    assert route.path == "/analysis" and record is not None
                    payload = record
                raw = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except Exception as exc:
                errors.append(repr(exc))
                self.send_error(500)

        def deny(self):
            writes.append(self.command)
            self.send_error(405)

        do_POST = do_DELETE = do_PUT = do_PATCH = deny

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        thread.start()
        hello = {"type": "hello", "protocol": 4, "features": manifest["required_features"],
                 "workspace": "/synthetic-analysis", "server":
                 {"origin": f"http://127.0.0.1:{server.server_port}", "token": "fixture"}}
        try:
            raw = b"".join((json.dumps(v, ensure_ascii=False) + "\n").encode() for v in (hello, *events))
            proc = sp.run([exe], cwd=src/PKG, env=os.environ, input=raw, capture_output=True,
                          check=True, timeout=30)
        finally:
            server.shutdown()
            thread.join()
    assert not (errors or writes or proc.stderr), (errors, writes, proc.stderr)
    assert reads == [("GET", route, SESSION, 200) for route in routes], reads
    frames = [json.loads(line) for line in proc.stdout.splitlines()]
    assert all(frame["type"] == "view" and frame["session_dir"] == SESSION for frame in frames)
    return proc.stdout, reads, frames


def code(nodes, suffix, expected, opened):
    folded, = [node for node in nodes if node.get("id") == f"1:{suffix}"]
    block, = folded["children"]
    height = min(360, max(48, 16+18*sum(max(1, (len(line)+109)//110) for line in expected.splitlines())))
    assert folded["type"] == "disclosure" and folded["open"] is opened
    assert block == {"type": "code", "id": f"analysis-1:{suffix}", "text": expected,
                     "language": "text", "height": height, "wrap": True}, suffix
    return folded["label"]


def replay(exe, src):
    for name, request, answer in (("one", ordinary(1), ordinary(1, "Assistant")),
                                  ("dozen", ordinary(12), ordinary(3, "Assistant")),
                                  ("edge-parts", controls(), ordinary(2, "Assistant"))):
        record = snapshot(request, answer, failure=name == "edge-parts")
        events = [render(), render(), render("sibling"), close("sibling")]
        routes = ["/analysis", "/sessions"]
        views = ["main", "main", "sibling"]
        if name == "dozen":
            events += [dict(type="event", event="run_settled", context="fixture", session_dir=SESSION)]
            routes.append("/analysis")
            views.append("main")
        raw, reads, frames = run(exe, src, record, [*events, close()], routes)
        assert [f["view"] for f in frames] == views
        assert all(f["root"] == frames[0]["root"] for f in frames)
        nodes = list(walk(frames[0]["root"]))
        for index, (_, body) in enumerate(request):
            title = code(nodes, f"message-{index}", body, False)
            assert title == "Пользователь · " + " ".join(body.split())[:90].rstrip(), title
        assert code(nodes, "answer", "\n\n".join(body for _, body in answer), True) == "Записанный ответ"
        assert code(nodes, "instructions", "[Developer · приоритет 17]\nStatic fixture", False) == "Инструкции · 1"
        raw_node, = [node for node in nodes if node.get("id") == "analysis-1:raw"]
        assert raw_node["language"] == "json" and json.loads(raw_node["text"]) == record["selected"]["steps"][0]
        yield name, raw, reads
    raw, reads, frames = run(exe, src, None, [render("preview", "preview"), close("preview")], [])
    assert [f["view"] for f in frames] == ["preview"]
    yield "preview", raw, reads


if __name__ == "__main__":
    for name, stdout, reads in replay(*map(Path, sys.argv[1:])):
        print(json.dumps([name, b64encode(stdout).decode("ascii"), reads], ensure_ascii=False))
