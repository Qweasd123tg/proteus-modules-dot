"""Prepared data for later bounded Usage/Model option-builder parity, no execution."""
from json import dumps

SESSION = "/selector-fixture"


def turn_id(number):
    return f"{number:036d}"


def usage_snapshot(turns=512):
    return {
        "requests": [
            {
                "exchange_id": f"request-{n}",
                "turn_id": turn_id(n),
                "model": {"provider": "fixture", "model": "a" if n % 2 else "b"},
                "origin": "direct",
                "status": "completed",
                "started_at_ms": 1800000000000 + 1000 * n,
                "finished_at_ms": 1800000000100 + 1000 * n,
                "usage": {"input_tokens": 50, "output_tokens": 20, "cached_input_tokens": 0},
            }
            for n in range(1, turns + 1)
        ],
        "latest_turn_id": turn_id(turns),
    }


def session_summaries(count=128):
    return [
        {"session_dir": SESSION if n == 0 else f"/fixture-session-{n}",
         "preview": f"Фикстура {n} λ", "message_count": n}
        for n in range(count)
    ]


def option(value, label):
    return {"value": value, "name": label}


def select(id, current, choices):
    return {"id": id, "name": id,
            "control": {"type": "select", "value": current, "options": choices}}


def model_state(count=512):
    values = [f"model-{n:04d}" for n in range(count)]
    assert count >= 2
    return {
        "config": {
            "profile": "Fixture",
            "model": {"provider": "odd", "name": values[1]},
            "model_options": [
                {"provider": "odd" if n % 2 else "even", "name": name,
                 "default_reasoning_effort": "high"}
                for n, name in enumerate(values)
            ],
            "session_settings": [
                select("model", values[1], [option(v, f"Модель {n}") for n,v in enumerate(values)]),
                select("reasoning_effort", "effort:high", [
                    option("_default", "Default"), option("effort:low", "Low"),
                    option("effort:high", "High")
                ]),
            ],
        }
    }


def render(surface):
    return {"type": "render", "context": "fixture", "session_dir": SESSION,
            "surface": surface, "view": surface}


def trace_usage():
    return [
        {"type": "context", "context": "fixture", "session_dir": SESSION, "workspace": "/selector-project"},
        render("page"),
        {"type": "action", "view": "page", "sequence": 1, "action": "period", "value": turn_id(32)},
        {"type": "close", "view": "page"},
    ]


def trace_model():
    return [
        {"type": "session_snapshot", "context": "fixture", "session_dir": SESSION, "state": model_state()},
        render("popup"),
        {"type": "action", "view": "popup", "sequence": 1, "action": "models", "value": None},
        {"type": "action", "view": "popup", "sequence": 2, "action": "back", "value": None},
        {"type": "close", "view": "popup"},
    ]


def input_bytes(messages, features, origin=""):
    hello = {"type": "hello", "protocol": 4, "features": features, "workspace": "/selector-project",
             "server": {"origin": origin, "token": "fixture"}}
    return b"".join(dumps(value).encode()+b"\n" for value in [hello, *messages])


def nodes(value):
    if isinstance(value, dict):
        yield value
        for part in value.values():
            yield from nodes(part)
    if isinstance(value, list):
        for part in value:
            yield from nodes(part)


def assert_usage(frames, reads, turns=512, sessions=128):
    # Run with all stdin messages queued and no sleep so only the two initial reads occur.
    assert [(f["type"],f["view"],f["sequence"]) for f in frames] == [
        ("view","page",0),("view","page",1)]
    assert reads == [("/sessions",SESSION),("/usage",SESSION)]
    want = ["all","latest",*(turn_id(n) for n in range(turns,0,-1))]
    for i, frame in enumerate(frames):
        controls = {node["id"]:node for node in nodes(frame["root"]) if node.get("type")=="select"}
        periods = controls["period"]["options"]
        assert [row["value"] for row in periods] == want
        assert [row["label"] for row in periods[2:]] == [f"Ход {n}" for n in range(turns,0,-1)]
        assert [row["value"] for row in periods if row["selected"]] == [["all"],[turn_id(32)]][i]
        assert len(controls["session"]["options"]) == sessions
        assert [row["value"] for row in controls["session"]["options"] if row["selected"]] == [SESSION]
        assert controls["model"]["options"][0]["value"] is None


def assert_model(frames, count=512):
    assert [(f["type"],f["view"],f["sequence"]) for f in frames] == [
        ("view","popup",0),("view","popup",1),("view","popup",2)]
    assert [f["root"]["transition"] for f in frames] == ["summary","models","summary"]
    picker, = [node for node in nodes(frames[1]["root"]) if node.get("id")=="models"]
    assert picker["action"] == "model"
    assert [row["value"] for row in picker["options"]] == [f"model-{n:04d}" for n in range(count)]
    assert [row["label"] for row in picker["options"]] == [
        f"{'odd' if n % 2 else 'even'}/Модель {n}" for n in range(count)]
    assert [row["value"] for row in picker["options"] if row["selected"]] == ["model-0001"]
