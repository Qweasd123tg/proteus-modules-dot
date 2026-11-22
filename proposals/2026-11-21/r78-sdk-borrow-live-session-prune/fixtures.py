"""Synthetic complete ConfigSummary and two live routes for real Mode/Model stdio."""
import json
import subprocess as sp

A, B = "/settings-fixture/a", "/settings-fixture/b"
WORKSPACE = "/settings-fixture"
DENIED = "fixture setting denied"
FOREIGN = "fixture foreign result must stay invisible"


def encode(value):
    return json.dumps(value,ensure_ascii=False,separators=(",",":")).encode()


def selection(name, selected, options):
    return {"id":name,"name":name,"category":None,"control":{
        "type":"select","value":selected,
        "options":[{"value":key,"name":label,"description":None} for key,label in options]}}


def config(n, tools, state):
    accepted, other = state=="accepted", state=="other"
    session = B if other else A
    model = "accepted-model-λ" if accepted else ("other-model" if other else "initial-model")
    effort = "effort:low" if accepted else "effort:high"
    mode = "plan" if accepted else "normal"
    plan_label = "Принят план λ" if accepted else "Read fixture"
    low_label = "Принято low λ" if accepted else "Low"
    profile = "Accepted profile λ" if accepted else ("Other profile" if other else "Initial profile")
    models = [{"provider":f"provider-{i%7}","name":model if i==0 else f"model-{i:04}",
               "label":f"Модель {i} λ","description":None if i%2 else f"Description {i:04}",
               "hidden":False,"reasoning_efforts":["low","high"],
               "default_reasoning_effort":"high"} for i in range(n)]
    settings = [
        selection("mode",mode,[("normal","Normal"),("plan",plan_label)]),
        selection("behavior_mode","review" if accepted else "_default",
                  [("_default","Profile"),("review","Review")]),
        selection("model",model,[(m["name"],m["label"]) for m in models]),
        selection("reasoning_effort",effort,[("_default","Default"),("effort:low",low_label),("effort:high","High")]),
        selection("style","short",[("short","Short"),("long","Long")]),
        {"id":"fixture.opaque","name":"Opaque","category":None,
         "control":{"type":"future","z":[None,2**64-1,-0.0,{"z":"порядок λ","a":False}],"a":True}},
    ]
    return {
        "display_text":"Synthetic configuration","module_epoch":13,"model_catalog_error":None,
        "activity":None,"config_path":None,"config_files":[],"cwd":WORKSPACE,"session_dir":session,
        "profile":profile,"model":{"provider":"provider-0","name":model,"label":"Current fixture"},
        "model_options":models,"session_settings":settings,
        "reasoning":{"enabled":True,"effort":"low" if accepted else "high",
                     "effort_options":["low","high"],"summary":False,"budget_tokens":None},
        "permission_mode":mode,"modules":[],"tools_enabled":[],
        "registered_tools":[{"supports_parallel_tool_calls":True,"name":f"tool-{i:04}",
                             "source":"fixture","safety":"read_only","description":f"Описание {i} λ"}
                            for i in range(tools)],
        "components":[],
    }


def snapshot(context, session, state):
    return {"type":"session_snapshot","context":context,"session_dir":session,
            "state":{"config":config(8,4,state)}}


def context(name, session):
    return {"type":"context","context":name,"session_dir":session,"workspace":WORKSPACE}


def render(view, name, session, surface="badge"):
    return {"type":"render","context":name,"session_dir":session,"view":view,"surface":surface}


def action(view, name, value, sequence):
    return {"type":"action","view":view,"action":name,"value":value,"sequence":sequence}


def close(view):
    return {"type":"close","view":view}


def reply(name, session, id_, **fields):
    return {"type":"command_result","context":name,"session_dir":session,"id":id_,**fields}


def probe_fixture():
    return {"small":config(8,4,"accepted"),"large":config(512,256,"accepted")}


def ordinary(exe, package, needed, env, folder):
    choice = "mode" if package == "mode" else "effort"
    change = "plan" if package == "mode" else 0
    undo = "normal" if package == "mode" else 1
    accepted = config(512,256,"accepted")
    # A bad late reply binds the live B route even though it names A's session.
    # If the existing guard fails, B immediately renders the conspicuous error or A config.
    trace = [
        {"type":"hello","protocol":4,"features":needed,"workspace":WORKSPACE},
        snapshot("old",A,"initial"),render("a-live","old",A),
        render("choose-a","old",A,"popup"),
        action("choose-a",choice,"not-an-option",1),action("choose-a",choice,change,2),
        close("choose-a"),
        snapshot("other",B,"other"),render("b-live","other",B),
        context("new",A),{"type":"rehost","view":"a-live","context":"new"},
        {"type":"close_context","context":"old"},
        reply("old",A,"setting-1",config=accepted,error=None),
        render("a-accepted","new",A),close("a-accepted"),
        render("choose-again","new",A,"popup"),action("choose-again",choice,undo,3),
        close("choose-again"),
        reply("new",A,"setting-2",config=None,error=DENIED),
        render("a-denied","new",A),close("a-denied"),
        reply("new",A,"already-completed",error=None),
        render("a-cleared","new",A),close("a-cleared"),
        reply("other",A,"setting-1",config=accepted,error=FOREIGN),
        render("b-isolated","other",B),close("b-isolated"),
        render("a-still","new",A),close("a-still"),
        context("duplicate",A),{"type":"rehost","view":"a-live","context":"duplicate"},
        {"type":"close_context","context":"new"},
        render("a-after-first-close","duplicate",A),close("a-after-first-close"),
        close("a-live"),{"type":"close_context","context":"duplicate"},
        # No snapshot yet: must not render the previously retained accepted config.
        context("again",A),render("a-new-instance","again",A),
        snapshot("again",A,"initial"),close("a-new-instance"),
        {"type":"close_context","context":"again"},
        close("b-live"),{"type":"close_context","context":"other"},
    ]
    result=sp.run([exe],cwd=folder,env=env,timeout=20,check=True,capture_output=True,
                  input=b"".join(encode(msg)+b"\n" for msg in trace))
    assert not result.stderr,result.stderr
    assert result.stdout.endswith(b"\n")
    frames=[json.loads(row) for row in result.stdout.splitlines()]
    assert {row["type"] for row in frames}<={"badge","view","set_session","close_popup"},frames
    calls=[f for f in frames if f["type"]=="set_session"]
    id_="mode" if package=="mode" else "reasoning_effort"
    choices=["plan","normal"] if package=="mode" else ["effort:low","effort:high"]
    assert calls==[
        {"type":"set_session","context":context_,"view":view,"id":f"setting-{i}",
         "session_dir":A,"setting":{"id":id_,"value":value}}
        for i,(context_,view,value) in enumerate(zip(["old","new"],["choose-a","choose-again"],choices,strict=True),1)
    ],calls
    popups=[f for f in frames if f["type"]=="close_popup"]
    assert popups==([{"type":"close_popup","context":"old"},{"type":"close_popup","context":"new"}]
                    if package=="mode" else []),popups

    def badge(view,session):
        f,=[r for r in frames if r.get("view")==view and r["type"]=="badge"]
        assert f["session_dir"]==session, f
        return f

    marker = "Принят план λ" if package=="mode" else "accepted-model-λ · Принято low λ"
    for view in ("a-accepted","a-denied","a-cleared","a-still","a-after-first-close"):
        f=badge(view,A)
        assert marker.encode() in encode(f),f
        assert (DENIED in f.get("lines",[]))==(view=="a-denied"),f
    # Rehost and accept both re-render the retained badge already on A.
    live_a=[r for r in frames if r.get("view")=="a-live" and r["type"]=="badge"]
    assert len(live_a)>=5 and any(marker.encode() in encode(r) for r in live_a),live_a
    # Only explicit B renders: no unsolicited render for any A reply, no error/rollback.
    live_b=badge("b-live",B)
    isolated=badge("b-isolated",B)
    assert {k:v for k,v in live_b.items() if k!="view"}=={k:v for k,v in isolated.items() if k!="view"},isolated
    assert marker.encode() not in encode(isolated) and FOREIGN.encode() not in result.stdout,result.stdout
    assert not any(DENIED in f.get("lines",[]) for f in frames if f.get("session_dir")==B)
    reopened=badge("a-new-instance",A) # Only the render after its fresh snapshot.
    assert marker.encode() not in encode(reopened) and DENIED not in reopened.get("lines",[]),reopened
    initial_label="Normal" if package=="mode" else "initial-model · High"
    assert initial_label.encode() in encode(reopened),reopened
    return result.stdout
