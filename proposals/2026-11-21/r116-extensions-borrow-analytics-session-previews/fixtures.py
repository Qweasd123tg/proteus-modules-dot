#!/usr/bin/env python3
"""SDK-consumer release wire with synthetic saved-session catalogues only."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

A, B = "/synthetic-session-a", "/synthetic-session-b"


def catalogue(n):
    rows = [
        {"session_dir": f"/synthetic-session-{i:02}", "message_count": 3*i + 1,
         "preview": (f"Discuss fixture {i:02}: planning a careful serialization change "
                     "and reviewing the existing saved-session semantics."
                     if i % 2 == 0 else
                     f"Условный проект {i:02}: согласуем очередность правок и сверяем готовые изменения.")}
        for i in range(n)
    ]
    rows[0]["session_dir"] = A
    rows[1]["session_dir"] = B
    return rows


def edge_rows():
    return [
        {"session_dir": A, "preview": "λ"*59 + "🧪\u200de\u0301", "message_count": -2.75},
        {"session_dir": A, "preview": "Different second label", "message_count": "15"},
        {"session_dir": B, "preview": "e"*59 + "e\u0301", "message_count": 14},
        {"session_dir": True, "preview": " \u2003\n", "message_count": True},
        {"session_dir": None, "preview": None},
        {"preview": ""},
        17,
        {"session_dir": ["synthetic-id"], "preview": False},
        {"session_dir": "/one", "preview": "☕", "message_count": 1},
        {"session_dir": "/short", "preview": "🧩"*59, "message_count": 4},
        {"session_dir": "/exact", "preview": "🧩"*60, "message_count": 4},
    ]


def render(view="page", session=A, surface="page"):
    return {"type": "render", "surface": surface, "view": view,
            "context": "fixture", "session_dir": session}


def close(view="page"):
    return {"type": "close", "context": "fixture", "view": view}


def chosen_saved():
    return {"type": "action", "view": "page", "context": "fixture", "session_dir": A,
            "sequence": 9, "action": "session", "value": B}


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def expected_picker(rows, selected):
    if not isinstance(rows, list):
        rows = []
    options = []
    for row in rows:
        if not isinstance(row, dict):
            row = {}
        preview = row.get("preview")
        if not isinstance(preview, str) or not preview:
            preview = "Новая сессия"
        count = row.get("message_count")
        count = int(count) if type(count) in (int, float) else 0
        value = row.get("session_dir")
        options.append({"label": f"{preview[:60]} · {count} сообщ.",
                        "value": value, "selected": type(value) is type(selected) and value == selected})
    title = next((x["label"] for x in options if x["selected"]), "Сохранённая сессия")
    return {"type": "select", "id": "session", "label": title, "action": "session", "options": options}


def replay(exe, src, env, package):
    pkg = Path("packages") / package
    target_path = "/" + package
    features = json.loads((src / pkg / "extension.json").read_text())["required_features"]

    def run(rows, messages):
        receipts, errors, writes = [], [], []

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
                    query = parse_qs(route.query, keep_blank_values=True)
                    assert self.headers.get("Authorization") == "Bearer fixture"
                    session, = query.pop("session_dir")
                    assert session in {A, B} and not query, (session, query)
                    receipts.append((route.path, session))
                    if route.path == "/sessions":
                        data = rows
                    else:
                        assert route.path == target_path, route.path
                        if package == "usage":
                            data = {"requests": [], "latest_turn_id": None}
                        else:
                            data = {"session_id": "synthetic", "revision": 1, "turns": [],
                                    "selected": None}
                    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception as error:
                    errors.append(error)
                    self.send_error(500)

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), API) as server:
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02},
                                      daemon=True)
            worker.start()
            try:
                hello = {"type": "hello", "protocol": 4, "features": features,
                         "workspace": "/synthetic", "server":
                         {"origin": f"http://127.0.0.1:{server.server_port}", "token": "fixture"}}
                buf = b"".join((json.dumps(msg, ensure_ascii=False) + "\n").encode()
                               for msg in [hello, *messages])
                result = sp.run([exe], cwd=src / pkg, env=env, input=buf,
                                capture_output=True, check=True, timeout=20)
            finally:
                server.shutdown()
                worker.join()
        assert not errors and not writes and not result.stderr, (errors, writes, result.stderr)
        frames = [json.loads(line) for line in result.stdout.splitlines()]
        assert frames and all(frame.get("type") == "view" for frame in frames)
        return result.stdout, tuple(receipts), frames

    def want(session):
        routes = ("/sessions", target_path) if package == "usage" else (target_path, "/sessions")
        return tuple((path, session) for path in routes)

    def check_pickers(frames, rows, selected):
        for frame, session in zip(frames, selected, strict=True):
            actual, = [node for node in walk(frame["root"]) if node.get("id") == "session"]
            assert actual == expected_picker(rows, session), (package, session, actual)

    cases = []
    for n in (20, 50):
        rows = catalogue(n)
        result = run(rows, [render(), render(), render("sibling"), close("sibling"),
                            close(), render(), close()])
        stdout, receipts, frames = result
        # Analysis clears its cache when the last view closes. Usage keeps it.
        expected = want(A) * (2 if package == "analysis" else 1)
        assert receipts == expected, (package, receipts)
        assert [f["view"] for f in frames] == ["page", "page", "sibling", "page"]
        check_pickers(frames, rows, [A]*4)
        cases.append((f"ordinary-{n}", stdout, receipts))

    rows = edge_rows()
    stdout, receipts, frames = run(rows, [render(), render(), chosen_saved(), render(), close()])
    assert receipts == want(A) + want(B)
    check_pickers(frames, rows, [A, A, B, B])
    cases.append(("edge", stdout, receipts))

    rows = {"unexpected": "not an array"}
    stdout, receipts, frames = run(rows, [render(), close()])
    assert receipts == want(A)
    check_pickers(frames, rows, [A])
    cases.append(("missing-list", stdout, receipts))

    stdout, receipts, frames = run([], [render(session=None), close(),
                                   render(view="preview", surface="preview"), close("preview")])
    assert not receipts and [f["view"] for f in frames] == ["page", "preview"]
    assert not any(node.get("id") == "session" for frame in frames for node in walk(frame["root"]))
    assert "Нет выбранной сессии" in json.dumps(frames[0], ensure_ascii=False)
    cases.append(("no-session-preview", stdout, receipts))
    return tuple(cases)
