"""Secondary, explicitly instrumented run: byte-stream relay, inspect first 16 KiB per frame.
Use two independent pipes, avoid buffering or decoding large history pages in the observer.
Timestamps of successful small committed replies are observed after the complete worker frame reached
the relay, immediately before its terminating bytes are forwarded to Core. Never log message bodies.
"""
import json, os,re,subprocess,sys,threading,time
from pathlib import Path
binary,output=sys.argv[1:]
p=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
log=Path(output).open('a',buffering=1);lock=threading.Lock();pending={}
def put(fields):
    with lock:log.write(json.dumps(fields,separators=(',',':'))+'\n')
def extract(prefix,key):
    m=re.search(rb'"'+key+rb'"\s*:\s*"([^"]*)"',prefix)
    return m[1].decode() if m else None
def inspect(req,prefix,length,when):
    id_=extract(prefix,b'id')
    if id_ is None:return
    if req:
        if extract(prefix,b'method')!='execute':return
        op=extract(prefix,b'operation')
        sid=extract(prefix,b'session_id')
        kind=extract(prefix,b'kind') if op=='commit' else None
        op_id=extract(prefix,b'operation_id') if kind else None
        turn=extract(prefix,b'turn_id') if kind else None
        if kind:
            pending[id_]=(kind,op_id,turn,sid)
        put(dict(t=when,event='request',id=id_,operation=op,session_id=sid,kind=kind,operation_id=op_id,turn_id=turn))
    elif id_ in pending:
        kind,op_id,turn,sid=pending.pop(id_)
        try:
            result=json.loads(prefix)['result']
            ack=result['ack']
            verified=(ack['operation_id']==op_id and ack['record']['entry']['kind']==kind and ack['record']['record_id']==op_id and ack['record']['turn_id']==turn and ack['record']['session_id']==sid)
        except (KeyError,ValueError,TypeError):
            verified=False
        put(dict(t=when,event='commit_ack',id=id_,operation_id=op_id,kind=kind,turn_id=turn,session_id=sid,verified=verified))
def pump(src,dst,req):
    buf=bytearray();length=0
    while data:=os.read(src,65536):
        cursor=0
        while cursor<len(data):
            nl=data.find(b'\n',cursor);end=nl if nl>=0 else len(data)
            if len(buf)<16384:buf.extend(data[cursor:min(end,cursor+16384-len(buf))])
            length+=end-cursor
            if nl<0:break
            inspect(req,buf,length,time.monotonic_ns());buf.clear();length=0;cursor=nl+1
        view=memoryview(data)
        while view:view=view[os.write(dst,view):]
def reader():
    try:pump(p.stdout.fileno(),1,False)
    except BrokenPipeError:pass
t=threading.Thread(target=reader);t.start()
try:pump(0,p.stdin.fileno(),True)
except BrokenPipeError:pass
finally:p.stdin.close()
p.wait();t.join();log.close()
