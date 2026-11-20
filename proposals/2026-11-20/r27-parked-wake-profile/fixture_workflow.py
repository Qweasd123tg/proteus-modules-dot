"""Synthetic, model-free workflow: archive distinct rows, then compact to the current input and one reply."""
import sys
import uuid
sys.path.insert(0, sys.argv[1])
from component_runtime import ProtocolError, run_component

def init(params):
    e, = params["exports"]
    descriptor = {k: e[k] for k in ("slot", "module_id", "contract_version", "composition")}
    return dict(protocol_version="v3", component_id=params["component_id"],
                exports=[dict(descriptor, module_features=[], config_schema=None)])

def row(text):
    return dict(id=str(uuid.uuid4()), role="Assistant", name=None, phase=None, tool_call_id=None, metadata=None,
                parts=[dict(part_id=str(uuid.uuid4()), provenance="model", scope="conversation",
                            payload={"Text": {"text": text}})])

def invoke(context, method, params):
    if method != "run": raise ProtocolError("expected run")
    cmd = params["task"]["text"].split()
    replacement = None
    reports = []
    if len(cmd) == 3 and cmd[0] == "archive":
        n, width = map(int, cmd[1:])
        assert 1 <= n <= 20000 and 0 <= width <= 3000
        messages = [row(f"bench-{i:05d}:" + "s" * width) for i in range(n)]
    elif cmd == ["compact"]:
        history = params["history"]
        replacement = history[-1:]
        messages = [row("settled")]
        reports = [dict(changed=True,user_message_replacements=[],reason="synthetic",input_messages=len(history),
                        output_messages=len(replacement),summary_source="fixture",metadata=None)]
    else: raise ProtocolError("unexpected synthetic command")
    return dict(status="success", result=dict(output=dict(text="ok",metadata=None), new_messages=messages,
                                                history_replacement=replacement,compactions=reports))

run_component(init,invoke)
