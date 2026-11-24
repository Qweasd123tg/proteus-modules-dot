from pathlib import Path
def between(s,a,b):
    assert s.count(a)==1,a
    start=s.index(a)
    return s[start:s.index(b,start)]
def lift(files,api,out,packet):
    out.mkdir(parents=True,exist_ok=True)
    text=api.decode()
    part=between(text,'/// Server-sent `output` events of one `/events` connection.','\n#[cfg(test)]\nmod connection_identity_tests')
    core=files['core-sse.rs']
    sep='pub(super) fn encode_sse_output('
    assert core.count(sep)==1
    exact=core[core.index(sep):].replace(sep,'pub(crate) fn encode_sse_output(',1)
    (out/'lib.rs').write_text('use std::io::{BufRead,BufReader};\nuse anyhow::{anyhow,Result};\nuse bytes::Bytes;\nuse proteus_contracts::app_protocol::{AppServerEvent,StdioOutput};\n'+part+exact+'\n#[cfg(test)] mod exercise;\n#[cfg(test)] mod meter;\n')
    for n in ('exercise.rs','meter.rs'):
        (out/n).write_bytes((packet/n).read_bytes())
