"""Synthetic, real List and writer invocations on an instrumented pinned worker."""
from pathlib import Path
import argparse, contextlib, json, os, random, re, selectors, signal, statistics, subprocess, sys, tempfile, time, uuid
p=argparse.ArgumentParser();p.add_argument('binary',type=Path);p.add_argument('--candidate',type=Path);p.add_argument('--n',type=int,default=16);p.add_argument('--repeat',type=int,default=7);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture-dir',type=Path,required=True)
args=p.parse_args(); binary=args.binary.resolve(); n=args.n
def u(i): return str(uuid.UUID(int=i))
def alarm(*unused): raise TimeoutError('profile response timeout')
signal.signal(signal.SIGALRM,alarm)
class Client:
    def __init__(self,b,skip=False,overlap=False):
        self.seq=0; self.b=b; env=dict(os.environ)
        for key,value in [('R40_SKIP',skip),('R40_OVERLAP',overlap)]:
            if value: env[key]='1'
            else: env.pop(key,None)
        self.diag=tempfile.NamedTemporaryFile()
        self.p=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.diag,env=env)
        self.logfile=open(self.diag.name,'rb')
        self.raw({'jsonrpc':'2.0','id':'h:1:0','method':'initialize','params':{'protocol_version':'v3','component_id':'catalog-profile','exports':[{'slot':'session_storage','module_id':b,'contract_version':'v2','composition':'select_one','module_config':{},'host_features':[]}]}})
        ident,_=self.recv();assert ident=='h:1:0'
    def raw(self,obj):
        self.p.stdin.write(json.dumps(obj).encode()+b'\n');self.p.stdin.flush()
    def send(self,op,**params):
        self.seq+=1; ident=f'h:1:{self.seq}';self.raw({'jsonrpc':'2.0','id':ident,'method':'execute','params':{'export':{'slot':'session_storage','module_id':self.b},'lineage':{'root_invocation_id':ident,'parent_invocation_id':None,'depth':0},'params':dict(operation=op,**params)}});return ident
    def recv(self):
        signal.alarm(45)
        try: line=self.p.stdout.readline(); ans=json.loads(line)
        finally: signal.alarm(0)
        assert 'result' in ans,ans;return ans['id'],ans['result']
    def call(self,op,**params):
        id=self.send(op,**params);ident,ans=self.recv();assert id==ident;return ans
    def log(self):
        signal.alarm(45)
        try: line=self.logfile.readline().decode().strip(); assert line.startswith('R40 '),line; return line
        finally: signal.alarm(0)
    def __enter__(self):return self
    def __exit__(self,*exc):
        self.p.stdin.close()
        try:self.p.wait(2)
        except subprocess.TimeoutExpired:self.p.kill();self.p.wait()
        self.p.stdout.close();self.logfile.close();self.diag.close()
def setup(c,root,ws,i,events):
    d=c.call('create',config_root=str(root),workspace_path=str(ws),session_id=u(i+1),parent_session_id=None)['descriptor']
    s=d['session'];got=c.call('acquire_writer',session=s); lease=got['lease'];rev=got['revision']
    for j in range(events):
        def id(k):return u((i+1)*100000+(j+1)*100+k)
        def msg(k):return dict(id=id(k),role='User',phase=None,parts=[dict(part_id=id(k+10),provenance='user',scope='conversation',payload={'Text':{'text':f'row {i}, event {j}, msg {k}: '+'x'*128}})],name=None,tool_call_id=None,metadata={})
        got=c.call('commit',commit=dict(lease=lease,operation_id=id(20),expected=rev,timestamp_ms=1000+j,attribution=dict(execution_id=None,thread_id=u(i+201),turn_id=None),entry=dict(kind='history_mutated',payload=dict(previous_revision=j,new_revision=j+1,mutation='append',messages=[msg(k) for k in range(3)],compaction=None,tool_results=[]))))
        rev=got['ack']['revision']
    c.call('release_writer',lease=lease)
    return s,Path(d['local_path'])
def measure(c, cfg, ws, ids, n, b, stage, label, trial, file):
    t=time.perf_counter_ns()
    a=c.call('list',config_root=str(cfg),workspace_path=str(ws) if ws else None,audit=False)
    wire=time.perf_counter_ns()-t
    assert a['result']=='sessions'; rows=a['sessions']
    assert sorted(uuid.UUID(r['descriptor']['session']['session_id']).int for r in rows)==sorted(ids)
    assert all(r['message_count']==3 and r.get('preview') for r in rows)
    keys=[(r['descriptor']['updated_at_ms'],r['descriptor']['session']['key']) for r in rows]
    assert keys==sorted(keys,reverse=True)
    line=c.logfile.readline().decode().strip(); match=re.fullmatch(r'R42 (\d+) (\[.*?\]) (\[.*?\])',line);assert match,line
    service,counts,order=int(match[1]),json.loads(match[2]),json.loads(match[3])
    assert sorted(order)==sorted(ids); assert sum(counts)==len(order),(stage,counts)
    print(json.dumps(dict(backend=b,stage=stage,n=n,label=label,trial=trial,counts=counts,service_ns=service,wire_ns=wire,order=order)),file=file,flush=True)
    return counts
def run(root,b,file):
    global binary
    cfg=root/'cfg'; ws=root/'small'; other=root/'large'
    for d in [cfg,ws,other]:d.mkdir()
    locs=[]; sessions=[]; binaries=[('base',args.binary.resolve())]
    if args.candidate: binaries.append(('cand',args.candidate.resolve()))
    for n in [1024,1025]:
        binary=args.binary.resolve()
        with Client(b) as c:
            for i in range(len(locs),n):
                session,loc=setup(c,cfg,ws if i<8 else other,i,1);locs.append(loc);sessions.append(session)
            # Prime all sidecars using normal worker. No copies, symlinks or synthetic stamps.
            measure(c,cfg,None,range(1,n+1),n,b,'prepare','setup',0,file)
        assert all((d/'.storage-catalog-v1.json').is_file() for d in locs)
        for trial in range(args.repeat):
            for label,exe in binaries[::1 if trial%2==0 else -1]:
                binary=exe
                with Client(b) as c:
                    for k in range(3):
                        counts=measure(c,cfg,None,range(1,n+1),n,b,'full'+str(k+1),label,trial,file)
                        if k==0:assert counts==[0,n,0],counts
                    for k in range(3):
                        measure(c,cfg,ws,range(1,9),n,b,'small'+str(k+1),label,trial,file)
                        measure(c,cfg,None,range(1,n+1),n,b,'altfull'+str(k+1),label,trial,file)
                    # Real single-session reads: check a small and a large session, not elapsed time.
                    for i in [0,n-1]:
                        snap=c.call('open_snapshot',session=sessions[i])['snapshot']
                        assert snap['revision']['session_seq']==1,snap
                        conv=c.call('read_records',snapshot=snap,after_seq=0,limit=5)
                        assert len(conv['page']['records'])==1
                        c.call('release_snapshot',snapshot=snap)
        print('done',b,n,flush=True)
with args.output.open('w') as file:
    for b in ['jsonl','sqlite']:
        with tempfile.TemporaryDirectory(dir=args.fixture_dir) as tmp:run(Path(tmp).resolve(),b,file)
