"""Bounded stdio RPC/seed fixture adapted from the synthetic R44 List harness."""
import json,os,signal,subprocess,uuid
from pathlib import Path
def u(i):return str(uuid.UUID(int=i))
def timeout(*_): raise TimeoutError("timeout")
signal.signal(signal.SIGALRM,timeout)
class Client:
    def __init__(self,binary,backend,host_features=()):
        self.backend=backend; self.seq=-1; env=dict(os.environ);
        self.p=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.rpc('initialize',{'protocol_version':'v3','component_id':'history-size-profile','exports':[{'slot':'session_storage','module_id':backend,'contract_version':'v2','composition':'select_one','module_config':{},'host_features':list(host_features)}]})
    def send(self,method,params):
        self.seq+=1; ident=f'h:1:{self.seq}'; self.p.stdin.write(json.dumps(dict(jsonrpc='2.0',id=ident,method=method,params=params),separators=(',',':')).encode()+b'\n');self.p.stdin.flush()
        return ident
    def recv(self):
        signal.alarm(120)
        try:
            raw=self.p.stdout.readline();assert raw,('unexpected EOF',self.p.poll(),self.p.stderr.read(4096)); res=json.loads(raw)
        finally:signal.alarm(0)
        assert 'result' in res,res
        self.last_raw=raw
        return res['id'],res['result']
    def rpc(self,method,params):
        ident=self.send(method,params);observed,result=self.recv();assert ident==observed;return result
    def call(self,op,**params):
        return self.rpc('execute',{'export':{'slot':'session_storage','module_id':self.backend},'lineage':{'root_invocation_id':f'h:1:{self.seq+1}','parent_invocation_id':None,'depth':0},'params':dict(operation=op,**params)})
    def __enter__(self):return self
    def __exit__(self,*_):
        self.p.stdin.close()
        try: self.p.wait(8)
        except subprocess.TimeoutExpired: self.p.kill();self.p.wait()
        self.reports=[]
        for line in self.p.stderr.read().decode().splitlines():
            assert line.startswith(('R45 ', 'R61 ')),line
            self.reports.append(list(map(int,line.split()[1:])))
        for pipe in (self.p.stdout,self.p.stderr):pipe.close()
        assert self.p.returncode==0,self.p.returncode
def setup(c,cfg,ws,i,k=8,size=512):
    d=c.call('create',config_root=str(cfg),workspace_path=str(ws),session_id=u(i+1),parent_session_id=None)['descriptor']
    s=d['session'];v=c.call('acquire_writer',session=s);lease=v['lease'];rev=v['revision'];body='q'*size
    for j in range(k):
        rev = append(c,lease,rev,i,j,body)
    c.call('release_writer',lease=lease)
    return Path(d['local_path'])

def append(c,lease,rev,i,j,body):
    def id(x):return u(1_000_000_000*(i+1)+10*j+x)
    m=dict(id=id(1),role='User',phase=None,parts=[dict(part_id=id(2),provenance='user',scope='conversation',payload={'Text':{'text':body}})],name=None,tool_call_id=None,metadata={})
    entry=dict(kind='history_mutated',payload=dict(previous_revision=j,new_revision=j+1,mutation='append',messages=[m],compaction=None,tool_results=[]))
    v=c.call('commit',commit=dict(lease=lease,operation_id=id(3),expected=rev,timestamp_ms=1000+j,attribution=dict(execution_id=None,thread_id=u(i+201),turn_id=None),entry=entry))
    return v['ack']['revision']
