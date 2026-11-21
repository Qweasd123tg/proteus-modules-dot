"""Finite local Git draft playback for a later admitted exact process gate."""
import http.server
import importlib.util
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import urlsplit

SESSION = "/draft-fixture"
READ_ROUTES = ["/".join(("", "workspace", name)) for name in ("changes","branches","log")]


def replay(executable, source, env):
    spec = importlib.util.spec_from_file_location("wire_fixture", source/"tests/wire.py")
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    changes = fixtures.changes()
    features = json.loads((source/"packages/git/extension.json").read_text())["required_features"]
    # The actual user-facing operation is draft typing only, never submit.
    drafts = ["  ", "Headline ◎\n\n" + ("Синтетический черновик λ\n" * 192), "Short λ", ""]
    routes = []
    errors = []

    class Api(fixtures.Api):
        def log_message(self,*_):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path not in READ_ROUTES:
                errors.append(("unexpected read",path))
                self.send_error(404)
                return
            routes.append(path)
            super().do_GET()

        def do_POST(self):
            errors.append(("unexpected write",urlsplit(self.path).path))
            self.send_error(405)

    fixtures.changes=lambda:changes
    fixtures.READS.clear()
    with http.server.ThreadingHTTPServer(("127.0.0.1",0),Api) as server:
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.025},daemon=True)
        thread.start()
        try:
            trace=[
                {"type":"hello","protocol":4,"features":features,"workspace":"/draft-worktree",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                {"type":"render","surface":"panel","view":"draft","context":"loop","session_dir":SESSION},
            ]
            trace.extend({"type":"action","view":"draft","action":"message","value":value,"sequence":i}
                         for i,value in enumerate(drafts,1))
            trace.extend([{"type":"close","view":"draft"},{"type":"close_context","context":"loop"}])
            result=sp.run([executable],env=env,cwd=source/"packages/git",check=True,timeout=20,capture_output=True,
                          input=b"".join(json.dumps(row,ensure_ascii=False).encode()+b"\n" for row in trace))
        finally:
            server.shutdown()
            thread.join()
    assert not result.stderr and not errors,(result.stderr,errors)
    assert routes==READ_ROUTES,routes
    assert fixtures.READS==[(path,SESSION) for path in READ_ROUTES],fixtures.READS
    frames=[json.loads(line) for line in result.stdout.splitlines()]
    assert len(frames)==1+len(drafts),frames
    for i,(frame,draft) in enumerate(zip(frames,["",*drafts],strict=True)):
        assert frame["type"]=="view" and frame["view"]=="draft" and frame["sequence"]==i
        control,=[node for node in fixtures.walk(frame["root"])
                  if node.get("type")=="input" and node.get("id")=="message"]
        assert control["value"]==draft,(i,control)
    return result.stdout,routes
