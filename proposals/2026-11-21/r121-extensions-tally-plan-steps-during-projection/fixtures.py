#!/usr/bin/env python3
"""Release Plan wire with synthetic messages, no action frames, and loopback GET only."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/plan")
SESSION = "/plan-fixture"
ICONS = {"completed": "circle-check", "in_progress": "circle-dot", "pending": "minus"}


def ordinary(n):
    statuses = ("pending", "completed", "in_progress", "completed", "pending")
    return [{"step": f"Обычный шаг {i}: проверка 🧪", "status": statuses[i % len(statuses)]}
            for i in range(n)]


def row(text, status):
    return {"step": text, "status": status}


def entry(rows=None, *, effective=None, status="done", name="update_plan", label="tool-fixture"):
    return {"role": "assistant", "tool": {"name": name, "call_id": label, "status": status,
                "args": {"plan": rows}, "effective_args": effective}}


def scope(kind, **fields):
    return dict(type=kind, context="fixture", session_dir=SESSION, **fields)


def snapshot(entries, running=False):
    return scope("session_snapshot", state={"execution": {"active": {"run_id": "fixture"} if running else None}},
                 entries=entries)


def views(prefix, surfaces=("badge", "popup")):
    frames = []
    for surface in surfaces:
        view = f"{prefix}-{surface}"
        frames.extend((scope("render", view=view, surface=surface), {"type": "close", "view": view}))
    return frames


def badges_and_details(frames, prefix, projected):
    badge, detail = (next(f for f in frames if f["view"] == f"{prefix}-{surface}") for surface in ("badge", "popup"))
    assert badge["type"] == "badge" and detail["type"] == "view"
    if projected is None:
        assert badge["hidden"] is True and badge["title"] == "План"
        assert detail["root"]["children"] == []
        return
    done = sum(t["status"] == "completed" for t in projected)
    active = next((t["step"] for t in projected if t["status"] == "in_progress"),
                  next((t["step"] for t in projected if t["status"] == "pending"), None))
    assert badge["hidden"] is False and badge["title"] == f"План {done}/{len(projected)}"
    assert badge["lines"] == ([] if active is None else [active])
    expect_details(detail, projected)


def expect_details(frame, projected):
    assert frame["type"] == "view"
    kids = frame["root"]["children"]
    actual = [(r["children"][1]["text"], r["children"][0]["name"], r["children"][1]["tone"]) for r in kids]
    expected = [(t["step"], ICONS[t["status"]], "muted" if t["status"] == "completed" else "default") for t in projected]
    assert actual == expected, (actual, expected)


def replay(exe, src, env):
    manifest = json.loads((src / PKG / "extension.json").read_text())
    assert manifest["command"] == ["bin/plan"] and manifest["dependencies"]["tools"] == ["update_plan"]
    features = manifest["required_features"]

    def run(messages, replies=()):
        reads, errors, writes = [], [], []
        assert all(m["type"] != "action" for m in messages)

        class API(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                try:
                    url = urlsplit(self.path)
                    query = parse_qs(url.query, keep_blank_values=True)
                    assert self.headers.get("Authorization") == "Bearer fixture"
                    assert url.path == "/history/tool-state" and not url.fragment
                    assert query == {"session_dir": [SESSION], "name": ["update_plan"]}, query
                    status, response = replies[len(reads)]
                    reads.append((url.path, query["name"][0], query["session_dir"][0], status))
                    body = json.dumps(response, ensure_ascii=False).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as error:
                    errors.append(error)
                    self.send_error(500)

            def deny(self):
                writes.append(self.command)
                self.send_error(405)

            do_POST = do_DELETE = do_PUT = do_PATCH = deny

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), API) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            thread.start()
            try:
                hello = {"type": "hello", "protocol": 4, "features": features, "workspace": "/plan-fixture",
                         "server": {"origin": f"http://127.0.0.1:{server.server_port}", "token": "fixture"}}
                raw_in = b"".join((json.dumps(evt, ensure_ascii=False) + "\n").encode() for evt in (hello, *messages))
                proc = sp.run([exe], input=raw_in, cwd=src / PKG, env=env, capture_output=True, check=True, timeout=15)
            finally:
                server.shutdown()
                thread.join()
        assert not (proc.stderr or errors or writes), (proc.stderr, errors, writes)
        assert len(reads) == len(replies), reads
        frames = [json.loads(raw) for raw in proc.stdout.splitlines()]
        assert all(f["type"] in ("badge", "view") and f["session_dir"] == SESSION for f in frames), frames
        assert [f["view"] for f in frames] == [e["view"] for e in messages if e["type"] == "render"], frames
        return proc.stdout, tuple(reads), frames

    cases = []
    user = {"role": "user", "tool": None}
    earlier = entry([row("not visible", "pending")])
    mixed = [row("повтор", "completed"), {"status": "completed"}, row(42, "completed"), row("", "completed"),
             row("повтор", "pending"), row("первый активный", "in_progress"), row("later", "in_progress"),
             row("повтор", "completed"), row("case", "Completed"), row("empty status", ""),
             row("wrong status", 42), {"step": "missing status"}, None]
    selected = [row("повтор", "completed"), row("", "completed"), row("повтор", "pending"),
                row("первый активный", "in_progress"), row("later", "in_progress"),
                row("повтор", "completed"), row("case", "pending"), row("empty status", "pending")]
    full = [row("готово", "completed"), row("", "completed"), row(42, "completed")]
    current = [
        ("short", [user, entry(ordinary(6))], False, ordinary(6)),
        ("modest", [user, entry(ordinary(12))], True, ordinary(12)),
        ("mixed", [earlier, user, entry(mixed), entry([], status="failed"), entry([], status="denied"),
                   entry([], name="unrelated")], False, selected),
        ("encoded", [entry([row("overridden", "pending")], effective=json.dumps({"plan": mixed}))], False, selected),
        ("cleared", [earlier, entry(ordinary(6), effective="{broken")], True, None),
        ("boundary", [earlier, user], True, None),
        ("idle", [entry(full)], False, None),
        ("running", [entry(full)], True, full[:2]),
    ]
    messages = [scope("context", workspace="/plan-panel-fixture", window_visual=dict(revision=0, preferences={}))]
    for label, entries, running, expected in current:
        messages.extend([snapshot(entries, running), *views(label)])
    messages.extend(views("control", ("page", "preview")))
    out, reads, frames = run(messages)
    for label, _, _, expected in current:
        badges_and_details(frames, label, expected)
    page, preview = frames[-2:]
    assert page["root"]["children"][0]["control"]["label"] == "По наличию"
    expect_details(preview, [row("Изучить задачу", "completed"), row("Подготовить изменения", "in_progress"),
                             row("Проверить результат", "pending")])
    cases.append(("current", out, reads))

    messages = [scope("context", workspace="/plan-panel-fixture",
                      window_visual=dict(revision=1, preferences={"visibility":"always"})),
                snapshot([earlier, user]),
                *views("cold"), *views("warm"), snapshot([user]), *views("missing")]
    replies = [(200, {"revision":"cache-1","tool":entry(mixed, status="done")["tool"]}),
               (200, {"revision":"cache-2","tool":None})]
    out, reads, frames = run(messages, replies)
    for label, expected in (("cold", selected), ("warm", selected), ("missing", None)):
        badges_and_details(frames, label, expected)
    cases.append(("always", out, reads))

    messages = [scope("context", workspace="/plan-panel-fixture",
                      window_visual=dict(revision=1, preferences={"visibility":"always"})),
                snapshot([user]), *views("waiting"), *views("same-epoch")]
    out, reads, frames = run(messages, [(409, {"error": "synthetic not ready"})])
    for badge, popup in zip(frames[::2], frames[1::2], strict=True):
        assert badge["title"] == "План недоступен" and not badge["hidden"]
        assert "История чата ещё не готова" in badge["lines"][0]
        assert popup["root"]["children"][1]["action"] == "retry_plan"  # displayed, never invoked
    cases.append(("not-ready", out, reads))
    return tuple(cases)
