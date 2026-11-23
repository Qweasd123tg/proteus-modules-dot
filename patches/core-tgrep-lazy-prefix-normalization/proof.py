#!/usr/bin/env python3
"""Exact Python predicate and inert search-loop differential. No process launch."""

import copy
import hashlib
import io
import itertools
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path("examples/modules/tgrep-search/backend.py")
RUNTIME = Path("examples/modules/component_runtime.py")
STOCK = "10000d7419f6b8c38f00cd04c92705ff70e13e5e"
CANDIDATE = "66c41d54b9f99f57cbfc70ea99d57e1ce6d0e2a8"
HELPER = "32cc106bf49c82d652dacb2b4ff32f0d1b1c02f0"


def git_blob(path):
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load(tier, expected):
    directory = ROOT / tier
    assert git_blob(directory / BACKEND) == expected
    assert git_blob(directory / RUNTIME) == HELPER
    path_before = list(sys.path)
    assert "component_runtime" not in sys.modules
    try:
        sys.path.insert(0, str((directory / RUNTIME).parent))
        module = runpy.run_path(str(directory / BACKEND), run_name="_r202_" + tier)
        assert Path(sys.modules["component_runtime"].__file__).resolve() == directory / RUNTIME
        return module["search"].__globals__
    finally:
        sys.modules.pop("component_runtime", None)
        sys.path[:] = path_before


def query(starts=(), ends=(), *, maximum=20, freshness="indexed", text="synthetic"):
    return {"starts_with": list(starts), "ends_with": list(ends), "max_results": maximum,
            "freshness": freshness, "query": text}


def event(path, line=1, message="synthetic result\r\n"):
    return json.dumps({"type": "match", "data": {"path": {"text": path},
                      "line_number": line, "lines": {"text": message}}}, ensure_ascii=False)


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Cancelled(Exception):
    pass


def inert_search(scope, lines, options, *, exit_code=0, cancel_at=None, timeout_at=None):
    argv_trace = []
    norm_trace = []
    scheduled = None
    cancelled = False
    callback = None

    class Context:
        def ensure_active(self):
            argv_trace.append(("ensure", cancelled))
            if cancelled:
                raise Cancelled("synthetic cancel")

        def on_cancel(self, fn):
            nonlocal callback
            argv_trace.append(("on_cancel",))
            callback = fn

    class Event:
        value = False

        def set(self):
            self.value = True

        def is_set(self):
            return self.value

    class Timer:
        def __init__(self, delay, fn):
            nonlocal scheduled
            assert scheduled is None
            scheduled = fn
            argv_trace.append(("timer", delay))

        def start(self):
            argv_trace.append(("timer_start",))

        def cancel(self):
            argv_trace.append(("timer_cancel",))

    class Pipe:
        index = 0

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal cancelled
            index = self.index
            if index == len(lines):
                argv_trace.append(("eof",))
                raise StopIteration
            self.index += 1
            argv_trace.append(("line", index))
            if index == cancel_at:
                cancelled = True
                callback()
            if index == timeout_at:
                scheduled()
            return lines[index]

        def close(self):
            argv_trace.append(("pipe_close",))

    class Process:
        def __init__(self, command, **kwargs):
            argv_trace.append(("spawn", tuple(command), tuple(sorted(kwargs))))
            assert kwargs["cwd"] == "synthetic-workspace"
            assert kwargs["stdin"] == "inert-null" and kwargs["stdout"] == "inert-pipe"
            assert kwargs["text"] and kwargs["encoding"] == "utf-8" and kwargs["errors"] == "replace"
            self.stdout = Pipe()
            self.status = None

        def poll(self):
            argv_trace.append(("poll", self.status))
            return self.status

        def kill(self):
            argv_trace.append(("kill",))
            self.status = -9

        def wait(self):
            if self.status is None:
                self.status = exit_code
            argv_trace.append(("wait", self.status))
            return self.status

    original = {name: scope[name] for name in ("subprocess", "tempfile", "threading", "normalize_prefix")}

    def normalize(s):
        norm_trace.append(s)
        return original["normalize_prefix"](s)

    def stderr(**kwargs):
        assert kwargs == {"mode": "w+t", "encoding": "utf-8"}
        return io.StringIO("  synthetic error detail  ")

    scope.update(subprocess=SimpleNamespace(Popen=Process, DEVNULL="inert-null", PIPE="inert-pipe"),
                 tempfile=SimpleNamespace(TemporaryFile=stderr),
                 threading=SimpleNamespace(Event=Event, Timer=Timer), normalize_prefix=normalize)
    try:
        before = copy.deepcopy(options)
        try:
            payload = scope["search"](scope["validate_args"](options), "synthetic-workspace",
                                      {"binary": "inert-engine", "index_path": "inert-index"}, Context())
            result = ("ok", payload)
        except Exception as error:
            result = ("error", type(error).__name__, str(error))
        assert options == before
        assert not scope["_active"]
        return result, argv_trace, norm_trace
    finally:
        scope.update(original)


def paired(stock, candidate, lines, options, **kwargs):
    old, new = (inert_search(tier, lines, options, **kwargs) for tier in (stock, candidate))
    assert wire(old[0]) == wire(new[0]) and old[1] == new[1], (lines, options, old, new)
    return old, new


def main():
    stock, candidate = load("stock", STOCK), load("candidate", CANDIDATE)
    prefix_lists = [[], [""], ["./"], ["././"], ["src/"], ["././src/", "./other/"],
                    ["x/../"], ["./ёж/"], ["src/", "src/"], ["SRC/"],
                    ["./" * 512 + "src/", "./other/"], ["././src/", "./unused/", "./ёж/"]]
    suffix_lists = [[], [""], [".rs"], [".py", ".md"], ["ёж"], [".RS"], ["/"], ["s", "src/"]]
    paths = ["", "./", "src/", "src/a.rs", "src/a.RS", "./src/a.rs", "other/a.py", "x/../a.rs",
             "x/a.rs", "ёж/ёж", "./ёж/ёж", "src/ёж", "SRC/a.rs", "unrelated"]
    pure = 0
    for starts, ends in itertools.product(prefix_lists, suffix_lists):
        args = query(starts, ends)
        prepared = []
        for path in paths + list(reversed(paths)):
            old = stock["matches_path"](path, args)
            new = candidate["matches_path"](path, args, prepared)
            assert old is new is candidate["matches_path"](path, args), (path, args)
            assert prepared == [stock["normalize_prefix"](p) for p in starts[:len(prepared)]]
            pure += 1

    cases = {
        "empty_query": ([], query(["./src/"], text=" \n"), {}),
        "zero_limit": ([], query(["./src/"], maximum=0), {}),
        "no_engine_matches": ([json.dumps({"type": "summary"})], query(["./src/"]), {}),
        "order_before_limit": ([event("./other/reject.rs", "ignored"), event("./src/wrong.py"),
                                event("./src/one.rs", 2), event("./src/two.rs", 3), "bad third line"],
                               query(["././src/"], [".rs"], maximum=2, freshness="current"), {}),
        "empty_prefix_literal": ([event("././src/a.rs")], query(["./"], [".rs"]), {}),
        "suffix_reject": ([event("./src/a.md")], query(["./src/"], [".rs"]), {}),
        "malformed_selected_row": ([event("./src/a.rs", "bad")], query(["./src/"], [".rs"]), {}),
        "malformed_path": ([event(17)], query(["./src/"], [".rs"]), {}),
        "malformed_json": (["{"], query(["./src/"]), {}),
        "no_limit_exit_1": ([event("./src/a.rs")], query(["./src/"]), {"exit_code": 1}),
        "engine_error": ([], query(["./src/"]), {"exit_code": 2}),
        "cancel_mid_stream": ([event("./src/a.rs"), event("./src/b.rs")], query(["./src/"]), {"cancel_at": 1}),
        "timeout_mid_stream": ([event("./src/a.rs"), event("./src/b.rs")], query(["./src/"]), {"timeout_at": 1}),
        "invalid_filters": ([], {**query(), "starts_with": [None]}, {}),
        "invalid_freshness": ([], query(freshness="wrong"), {}),
        "prefixes_kept_lazy": ([event(f"./src/{i}.rs") for i in range(12)],
                               query(["././src/", "./" * 512 + "unused/"]), {}),
        "prefixes_extend_lazily": ([event("./src/a.rs"), event("./lib/b.rs"), event("./src/c.rs")],
                                   query(["./src/", "././lib/", "./unused/"]), {}),
    }
    traced = {name: paired(stock, candidate, lines, opts, **flags)
              for name, (lines, opts, flags) in cases.items()}
    for k in ("empty_query", "zero_limit", "invalid_filters", "invalid_freshness"):
        assert not any(e[0] == "spawn" for e in traced[k][0][1]); assert not traced[k][1][2]
    assert not traced["no_engine_matches"][1][2]
    assert traced["prefixes_kept_lazy"][1][2] == ["././src/"]
    assert traced["prefixes_extend_lazily"][1][2] == ["./src/", "././lib/"]
    assert traced["empty_prefix_literal"][1][0][1][0][0]["path"] == "./src/a.rs"
    selected, limited = traced["order_before_limit"][1][0][1]
    assert limited and [r["path"] for r in selected] == ["src/one.rs", "src/two.rs"]
    assert [r["metadata"]["line"] for r in selected] == [2, 3]
    assert ("line", 4) not in traced["order_before_limit"][1][1]
    assert traced["cancel_mid_stream"][1][0] == ("error", "Cancelled", "synthetic cancel")
    assert traced["timeout_mid_stream"][1][0] == ("error", "RuntimeError", "tgrep query timed out")

    reject = event("./vendor/miss.rs")
    accept = event("./src/found.rs")
    repeated = [reject] * 50_000 + [accept] * 20 + ["not read beyond limit"]
    old, new = paired(stock, candidate, repeated, query(["././src/", "././lib/"], [".rs"]))
    assert len(old[2]) == 100_020 and new[2] == ["././src/", "././lib/"]
    again = paired(stock, candidate, [event("./fresh/yes.rs")], query(["./fresh/"]))
    assert again[1][2] == ["./fresh/"]
    assert again[1][0][1][0][0]["path"] == "fresh/yes.rs"
    results = {"status": "passed", "python": sys.version.split()[0], "scope": "exact example; no subprocess or timers started",
               "stock": STOCK, "candidate": CANDIDATE, "helper": HELPER,
               "literal_cases": pure, "inert_cases": len(cases) + 2,
               "large_filtered_stream": {"considered_rows": 50_020, "selected_rows": 20,
                   "stock_normalizations": len(old[2]), "candidate_normalizations": len(new[2]),
                   "result_sha256": hashlib.sha256(wire(new[0]).encode()).hexdigest()}}
    print(json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
