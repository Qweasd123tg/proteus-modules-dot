"""Deterministic exact-schema popup fixture inputs for a later admitted gate."""
from json import dumps
import sys


def tree(n, transition, structured=False):
    choices = [
        {
            "value": ({"id": f"model-{i:04d}", "opaque": ["α", {"note": "строка 🦀"}, None]}
                      if structured else f"model-{i:04d}"),
            "label": f"Модель {i:04d} λ",
            "selected": i == 1,
        }
        for i in range(n)
    ]
    return {"type":"stack","transition":transition,"children":[
        {"type":"picker","id":"models","title":"Model","action":"model","options":choices}
    ]}


def incoming(n, seq, transition, structured=False):
    return {
        "type": "view", "view": "popup@fixture", "sequence": seq,
        "session_dir": "/synthetic/chat", "keys": {"escape":"close", "enter":"submit"},
        "root": tree(n,transition,structured),
    }


def finite_cases():
    for count in (8, 512):
        yield {
            "case":f"open-close-reopen-{count}",
            "receive_initial":incoming(count,0,"models"),
            "receive_stale_after_action":incoming(count,1,"stale"),
            "receive_fresh_after_action":incoming(count,3,"summary"),
            "pending_action_sequence":2,
            "cycles_without_fresh_reply":3
        }
    yield {
        "case":"opaque-choices-and-replacement",
        "receive_initial":incoming(8,0,"models",True),
        "receive_fresh_after_action":incoming(8,3,"summary",True),
        "pending_action_sequence":2,
        "cycles_without_fresh_reply":1
    }


if __name__ == "__main__":
    for row in finite_cases():
        sys.stdout.write(dumps(row, ensure_ascii=False, separators=(",",":"))+"\n")
