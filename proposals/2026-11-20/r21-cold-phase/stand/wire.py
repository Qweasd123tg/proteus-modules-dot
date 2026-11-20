"""Instrumented byte-stream relay; JSONL logs bounded RPC timing, not payloads.

Request and response are observed on receipt of their final newline, before its
buffer is forwarded. Timings include queuing, worker execution, serialization,
and the relay/pipe cost. They are NOT worker-mutex times. Reader IDs are joined
with request IDs; small commits additionally validate their durable ACK.
"""
import json, os,re,subprocess,sys,threading,time
from pathlib import Path
binary,output=sys.argv[1:]
p=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
log=Path(output).open('a',buffering=1);lock=threading.Lock();pending={}
def put(fields):
    log.write(json.dumps(fields,separators=(',',':'))+'\n')
def extract(prefix,key):
    m=re.search(rb'"'+key+rb'"\s*:\s*"([^"]*)"',prefix)
    return m[1].decode() if m else None
def category(k):
    if k is None: return None
    if k.startswith('display-data-'): return 'content'
    if k.startswith('display-revision-'): return 'revision'
    if k=='display-view-v1-head': return 'head'
    if k=='display-view-v1-prefix': return 'prefix'
    return 'other'

def inspect(req,prefix,length,start,when):
    id_=extract(prefix,b'id')
    if id_ is None:return
    if req:
        if extract(prefix,b'method')!='execute':return
        op=extract(prefix,b'operation')
        sid=extract(prefix,b'session_id')
        kind=extract(prefix,b'kind') if op=='commit' else None
        op_id=extract(prefix,b'operation_id') if kind else None
        turn=extract(prefix,b'turn_id') if kind else None
        key=category(extract(prefix,b'key')) if op in ('read_cache','write_cache') else None
        snapshot=extract(prefix,b'snapshot_id') if op in ('read_display_records','read_records','release_snapshot') else None
        matched=dict(operation=op,session_id=sid,kind=kind,operation_id=op_id,turn_id=turn,key=key,snapshot=snapshot)
        with lock:
            pending[id_]=(when,matched)
            put(dict(t=when,start=start,event='request',id=id_,bytes=length,**matched))
    else:
        with lock:
            request=pending.pop(id_,None)
            if request is None: return
            sent,matched=request
            # Distinguish an actual cache miss from requests for leaves that exist.
            # JSON root fields are before the payload; a document with an embedded
            # field called 'document' must not turn an existing leaf into a miss.
            cached=None
            if matched['operation']=='read_cache':
                m=re.search(rb'"document"\s*:\s*(null|\{)',prefix)
                cached=(m[1]==b'{') if m else None
            put(dict(t=when,start=start,request_end=sent,event='response',id=id_,bytes=length,cached=cached,**matched))
            if matched['kind']:
                kind,op_id,turn,sid=(matched[k] for k in ('kind','operation_id','turn_id','session_id'))
                try:
                    result=json.loads(prefix)['result']
                    ack=result['ack']
                    verified=(ack['operation_id']==op_id and ack['record']['entry']['kind']==kind and ack['record']['record_id']==op_id and ack['record']['turn_id']==turn and ack['record']['session_id']==sid)
                except (KeyError,ValueError,TypeError):
                    verified=False
                put(dict(t=when,event='commit_ack',id=id_,operation_id=op_id,kind=kind,turn_id=turn,session_id=sid,verified=verified))
def pump(src,dst,req):
    buf=bytearray();length=0;start=None
    while data:=os.read(src,65536):
        cursor=0
        while cursor<len(data):
            if start is None:start=time.monotonic_ns()
            nl=data.find(b'\n',cursor);end=nl if nl>=0 else len(data)
            if len(buf)<16384:buf.extend(data[cursor:min(end,cursor+16384-len(buf))])
            length+=end-cursor
            if nl<0:break
            inspect(req,buf,length,start,time.monotonic_ns());buf.clear();length=0;start=None;cursor=nl+1
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
