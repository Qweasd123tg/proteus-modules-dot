#!/usr/bin/env python3
"""Actual TPS stdio; idle Badge/Popup, synthetic GET-only usage and no actions."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/tps")
ONE = "/synthetic-tps/segment-a-🧪"
TWO = "/synthetic-tps/session-b"
A = {"provider": "fixture-provider", "name": "standard-model"}
B = {"provider": "другой-провайдер", "name": A["name"]}
C = {"provider": B["provider"], "name": "другая-модель"}
NA = {"provider": B["provider"], "name": 17}
NB = {"provider": ["not", "typed"], "name": C["name"]}
EMPTY = {"provider": "", "name": ""}
FAIL = "fixture usage temporarily unavailable"


def scoped(kind, session=ONE, **fields):
    return dict(type=kind, context="tps-fixture-window", session_dir=session, **fields)


def state(model, extra=0):
    return {"config": {"model": {**model, "label": f"ignored-{extra}", "detail": {"phase": extra}}},
            "execution": {"active": None}, "activity": {"running_runs": 0}, "other": [extra]}


def snapshot(model=A, session=ONE, extra=0):
    return scoped("session_snapshot", session, state=state(model, extra), entries=[])


def update(model, extra=0):
    return scoped("session_update", update={"type": "state", "state": state(model, extra)})


def render(view, surface=None, session=ONE):
    return scoped("render", session, view=view, surface=surface or view)


def close(view):
    return {"type": "close", "view": view}


def sample(model, output, end=3000):
    return {"origin": "direct", "status": "completed", "started_at_ms": end-2000,
            "finished_at_ms": end, "model": model, "usage": {"output_tokens": output, "reasoning_output_tokens": 999}}


def dto(config, output):
    return sample({"provider": config["provider"], "model": config["name"]}, output)


def label(config):
    return f'{config["provider"]}/{config["name"]}'


def replay(exe, src, env):
    manifest = json.loads((src/PKG/"extension.json").read_text())
    assert manifest["command"] == ["bin/tps"] and manifest["session_entries"] is False

    def run(events, answers):
        reads, errors, writes = [], [], []
        assert all(msg["type"] not in ("action", "command") for msg in events)

        class Api(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                try:
                    session, status, document = answers[len(reads)]
                    url = urlsplit(self.path)
                    assert url.path == "/usage" and parse_qs(url.query, keep_blank_values=True) == {"session_dir": [session]}
                    assert self.headers.get("Authorization") == "Bearer fixture"
                    reads.append(("GET", url.path, session, status))
                    payload = {"requests": document} if status == 200 else {"error": document}
                    wire = json.dumps(payload, ensure_ascii=False).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(wire)))
                    self.end_headers()
                    self.wfile.write(wire)
                except Exception as exc:
                    errors.append(repr(exc))
                    self.send_error(500)

            def deny(self):
                writes.append(self.command)
                self.send_error(405)

            do_POST = do_DELETE = do_PUT = do_PATCH = deny

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Api) as server:
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True)
            worker.start()
            hello = {"type": "hello", "protocol": 4, "features": manifest["required_features"],
                     "workspace": "/synthetic-tps-work", "server": {
                         "origin": f"http://127.0.0.1:{server.server_port}", "token": "fixture"}}
            try:
                raw = b"".join((json.dumps(v, ensure_ascii=False) + "\n").encode() for v in (hello, *events))
                proc = sp.run([exe], cwd=src/PKG, env=env, input=raw, capture_output=True,
                              check=True, timeout=25)
            finally:
                server.shutdown()
                worker.join()
        assert not (errors or writes or proc.stderr), (errors, writes, proc.stderr)
        assert reads == [("GET", "/usage", sess, status) for sess, status, _ in answers], reads
        frames = [json.loads(line) for line in proc.stdout.splitlines()]
        return proc.stdout, tuple(reads), frames

    events = [snapshot(A), render("badge"), render("popup")]
    events += [update(A, i) for i in range(1,13)]
    events += [update(B), update(C), update(NA), update(NB), update(EMPTY), update(A), update(A, 99),
               scoped("event", event="run_settled"), close("popup"), close("badge"),
               snapshot(A, TWO), render("badge", session=TWO), render("popup", session=TWO),
               close("popup"), close("badge")]
    default_latest = {"provider": "unfiltered", "name": "latest"}
    answers = [
        (ONE, 200, [dto(A, 22), dto(A, 120), sample({"provider": "wrong", "model": A["name"]},180,4000)]),
        (ONE, 200, [dto(B, 72), dto(A, 300)]),
        (ONE, 200, [dto(C, 30), dto(B, 300)]),
        (ONE, 200, [dto(C, 20), dto(default_latest, 88)]),
        # A malformed API row model still uses the original empty string
        # fallbacks. Some(("", "")) is not None and excludes newer nonempty models.
        (ONE, 200, [sample({"provider": 17},44), sample({"model": "newer","provider": "fixture"},166,4000)]),
        (ONE, 503, FAIL),
        (ONE, 200, [dto(A, 60)]),
        (TWO, 200, [dto(A, 80)]),
    ]
    raw, reads, frames = run(events, answers)
    pairs = [(ONE, "60,0 TPS", label(A))]*13
    pairs += [(ONE,"36,0 TPS",label(B)),(ONE,"15,0 TPS",label(C)),
              (ONE,"44,0 TPS",label(default_latest)),(ONE,"44,0 TPS",label(default_latest)),
              (ONE,"22,0 TPS","/"),(ONE,"— TPS",FAIL),(ONE,"— TPS",FAIL),
              (ONE,"30,0 TPS",label(A)),(TWO,"40,0 TPS",label(A))]
    assert len(frames) == 2*len(pairs), [m.get("view") for m in frames]
    for index, (sess, rate, marker) in enumerate(pairs):
        badge, popup = frames[index*2:index*2+2]
        assert (badge["type"],badge["view"],badge["session_dir"]) == ("badge","badge",sess)
        assert (popup["type"],popup["view"],popup["session_dir"]) == ("view","popup",sess)
        assert badge["face"]["text"] == rate, badge
        assert marker in json.dumps(badge,ensure_ascii=False) and marker in json.dumps(popup,ensure_ascii=False)
        if rate != "— TPS":
            assert rate in json.dumps(popup,ensure_ascii=False)
    cases = [("idle-updates",raw,reads)]

    raw, reads, frames = run([render("no-session","popup",None), close("no-session"),
                              render("preview","preview",None), close("preview")], ())
    absent, preview = frames
    assert absent["session_dir"] is None and "Нет активной сессии." in json.dumps(absent,ensure_ascii=False)
    assert preview["session_dir"] is None and "48,0 TPS" in json.dumps(preview,ensure_ascii=False)
    cases.append(("controls",raw,reads))
    return tuple(cases)


if __name__ == "__main__":
    from base64 import b64encode
    import os
    import sys

    exe, src = map(Path, sys.argv[1:])
    for name, stdout, reads in replay(exe, src, os.environ):
        print(json.dumps([name, b64encode(stdout).decode("ascii"), reads], ensure_ascii=False))
