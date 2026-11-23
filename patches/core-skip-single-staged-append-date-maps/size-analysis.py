#!/usr/bin/env python3
"""Source-derived single-append provider envelope size; no worker execution."""
from pathlib import Path
import argparse,json,re,uuid

def compact(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()

def fixture_messages(n,text):
    for i in range(n):
        uid=lambda x:str(uuid.UUID(int=x))
        role="user" if i%2==0 else "assistant"
        yield {
            "id":uid(i*2+1),"role":role,"phase":None,"parts":[{
                "part_id":uid(i*2+2),"provenance":"user" if i%2==0 else "model",
                "scope":"conversation","payload":{"Text":{"text":f"Fixture row {i}\n"+text*4}},
            }],"name":None,"tool_call_id":None,"metadata":None,
        }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rust-receipt',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    source=a.source/'crates/proteus-core/examples/session_index_fixture.rs'
    body=re.search(r'"([^"\n]+)"\.repeat\(repeats\)',source.read_text()).group(1)
    rust=dict((int(n),(int(r),int(c))) for n,r,c in re.findall(
        r'single-(\d+): typed-record-bytes=(\d+), canonical-messages-bytes=(\d+)',a.rust_receipt.read_text()))
    out={"scope":"source-derived serialization size compatibility; not a running Modules worker",
         "limits":{"projected_resume_state":32*1024*1024,"display_record":65*1024*1024,"canonical_payload":64*1024*1024,"stage_budget":512*1024*1024},"cases":[]}
    for n in (5000,50000):
        assert n in rust
        msg=2+sum(len(compact(m)) for m in fixture_messages(n,body))+n-1
        assert rust[n][1]==msg,(n,rust[n][1],msg)
        state={"conversation":{"messages":[],"revision":{"session_seq":1,"history_revision":1},
                               "model_context":[]},
               "usage":{"session_id":str(uuid.UUID(int=1)),"revision":0,"latest_turn_id":None,"requests":[]},
               "last_history_turn":None,"interrupted_turns":[]}
        overhead=len(compact(state))-2
        total=overhead+msg
        assert total<=out["limits"]["projected_resume_state"]
        assert rust[n][0]<=out["limits"]["display_record"]
        out["cases"].append({"messages":n,"typed_display_record_bytes":rust[n][0],
            "canonical_messages_array_bytes":msg,"complete_resume_state_other_bytes":overhead,
            "complete_resume_state_bytes":total,"projected_resume_state_headroom_bytes":
            out["limits"]["projected_resume_state"]-total})
    text=json.dumps(out,indent=2)+"\n"
    if a.out:a.out.write_text(text)
    print(text,end='')
if __name__=='__main__':main()
