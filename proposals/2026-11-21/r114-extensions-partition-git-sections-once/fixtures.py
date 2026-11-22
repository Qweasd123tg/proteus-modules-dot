#!/usr/bin/env python3
"""Actual Git release NDJSON, synthetic session and loopback GET only."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/git")
SESSION = "/synthetic-session"


def snapshot(n, repository=True, staged=False, truncated=False):
    states = [
        ("modified", "modified", "modified"), ("deleted", None, "deleted"),
        ("untracked", None, "untracked"), ("conflict", "conflict", "conflict"),
        ("added", "added", None), ("renamed", "renamed", None),
        ("opaque", False, []), (17, {}, {"marker": True}),
    ]
    entries = []
    for i in range(n):
        status, in_index, work = ("modified", "modified", None) if staged else states[i % len(states)]
        value = {"path": f"src/fixture-{i:02}-данные.txt", "status": status,
                 "staged": in_index, "unstaged": work, "added": i + 1, "deleted": i % 3}
        if i % len(states) == 5 and not staged:
            value["original"] = f"old/fixture-{i:02}.txt"
        if i % len(states) == 7 and not staged:
            del value["staged"]
        entries.append(value)
    return {"repository": repository, "branch": "fixture-main", "refs_revision": "same-refs",
            "ahead": 0, "behind": 0, "added": n * 3, "deleted": n,
            "truncated": truncated, "entries": entries}


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def value_nodes(root, action=None, kind=None):
    return [x for x in walk(root) if (action is None or x.get("action") == action)
            and (kind is None or x.get("type") == kind)]


def ndjson(value):
    return (json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def render(view="first"):
    return {"type": "render", "surface": "panel", "view": view, "context": "fixture",
            "session_dir": SESSION}


def close(view):
    return {"type": "close", "context": "fixture", "view": view}


def run(exe, src, env, changes, messages, branch_error=False):
    reads, errors, writes = [], [], []
    assert all(m["type"] != "action" for m in messages)
    next_change = iter(changes)

    class Server(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            writes.append(self.command)
            self.send_error(405)

        do_PUT = do_DELETE = do_PATCH = do_POST

        def do_GET(self):
            try:
                assert self.headers.get("Authorization") == "Bearer fixture"
                route = urlsplit(self.path)
                query = parse_qs(route.query, keep_blank_values=True)
                assert query == {"session_dir": [SESSION]}, query
                reads.append(route.path)
                if route.path == "/workspace/changes":
                    status, reply = 200, next(next_change)
                elif route.path == "/workspace/branches":
                    status, reply = ((503, {"error": "synthetic branch catalogue unavailable"})
                                     if branch_error else (200, {"branches": [{"name": "fixture-main"}]}))
                else:
                    raise AssertionError(route.path)
                body = json.dumps(reply, separators=(",", ":"), ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                errors.append(e)
                self.send_error(500)

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Server) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            features = json.loads((src / PKG / "extension.json").read_text())["required_features"]
            hello = {"type": "hello", "protocol": 4, "features": features,
                     "workspace": "/synthetic", "server":
                     {"origin": f"http://127.0.0.1:{server.server_port}", "token": "fixture"}}
            proc = sp.run([exe], cwd=src / PKG, env=env,
                          input=b"".join(ndjson(value) for value in [hello, *messages]),
                          capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not errors and not writes and not proc.stderr, (errors, writes, proc.stderr)
    assert not list(next_change), reads
    frames = [json.loads(line) for line in proc.stdout.splitlines()]
    assert frames and all(f.get("type") == "view" and f.get("session_dir") == SESSION for f in frames)
    return proc.stdout, tuple(reads), frames


def changes_root(root):
    tabs, = value_nodes(root, kind="tabs")
    return tabs["tabs"][0]


def check_panel(root, n, *, stage_action, commit_hint, commit_disabled):
    changes = changes_root(root)
    assert changes["label"] == "Changes" and changes["count"] == n, (changes["label"], changes["count"])
    stage, = value_nodes(changes, stage_action, "button")
    commit, = value_nodes(changes, "commit", "button")
    assert stage["disabled"] == (n == 0), stage
    assert commit["disabled"] == commit_disabled and commit["hint"] == commit_hint, commit
    return stage


def replay(exe, src, env):
    first = snapshot(32)
    first["entries"][1]["path"] = first["entries"][0]["path"]
    a, ar, frames = run(exe, src, env, [first, snapshot(64, staged=True, truncated=True)], [
        render(), render(), render("second"), close("second"),
        {"type": "event", "event": "run_settled", "context": "fixture", "session_dir": SESSION},
        render("second"), render(), close("second"), close("first"),
    ])
    assert ar == ("/workspace/changes", "/workspace/branches", "/workspace/changes"), ar
    assert len(frames) == 6, [(f["view"], changes_root(f["root"])["count"]) for f in frames]
    assert [f["view"] for f in frames] == ["first", "first", "second", "first", "second", "first"]
    assert frames[0]["root"] == frames[1]["root"] == frames[2]["root"]
    assert frames[3]["root"] == frames[4]["root"] == frames[5]["root"]
    for f in frames[:3]:
        root = f["root"]
        panel = check_panel(root, 32, stage_action="stage_all",
                            commit_hint="Сначала разрешите конфликты", commit_disabled=True)
        assert value_nodes(panel, "unstage_all")[0]["disabled"] is False
        headers = [x for x in walk(root) if x.get("kind") == "header"]
        assert [(x["id"], x["count"], x["checked"]) for x in headers] == [
            ("section:conflicts", 4, "mixed"),
            ("section:tracked", 20, "mixed"),
            ("section:new", 8, "mixed"),
        ]
        assert sum(x.get("id") == "file:" + first["entries"][0]["path"] for x in walk(root)) == 2
        assert any("← fixture-05.txt" in str(x.get("detail", "")) for x in walk(root))
    for f in frames[3:]:
        root = f["root"]
        panel = check_panel(root, 64, stage_action="unstage_all",
                            commit_hint="Нет сообщения коммита", commit_disabled=True)
        assert value_nodes(panel, "stage_all")[0]["disabled"] is True
        assert any(x.get("text") == "Список изменений обрезан" for x in walk(root))
        headers = [x for x in walk(root) if x.get("kind") == "header"]
        assert [(x["id"], x["count"], x["checked"]) for x in headers] == [("section:tracked", 64, True)]

    e, er, ef = run(exe, src, env, [snapshot(0, truncated=True)], [render(), close("first")])
    assert er == ("/workspace/changes", "/workspace/branches") and len(ef) == 1
    check_panel(ef[0]["root"], 0, stage_action="stage_all",
                commit_hint="Нет изменений для коммита", commit_disabled=True)
    assert "Список изменений обрезан" not in json.dumps(ef, ensure_ascii=False)

    b, br, bf = run(exe, src, env, [snapshot(32, repository="true")], [render(), close("first")])
    assert br == ("/workspace/changes",) and len(bf) == 1
    assert "Нет git-репозитория" in json.dumps(bf, ensure_ascii=False)

    c, cr, cf = run(exe, src, env, [snapshot(32)], [render(), close("first")], branch_error=True)
    assert cr == ("/workspace/changes", "/workspace/branches") and len(cf) == 1
    assert "synthetic branch catalogue unavailable" in json.dumps(cf, ensure_ascii=False)
    return (a, e, b, c), (ar, er, br, cr)
