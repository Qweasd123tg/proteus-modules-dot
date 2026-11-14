"""Benign single-instance MCP fixture. Exclusive fixture-directory lock only."""
import fcntl,json,os,sys,time
from pathlib import Path
mode,base=sys.argv[1:];base=Path(base)
def log(event):
 with (base/'mcp-events.jsonl').open('a') as f:f.write(json.dumps({'event':event,'pid':os.getpid(),'time_ns':time.time_ns()})+'\n')
log('started')
lock=(base/'fixture.lock').open('a+')
if mode=='exclusive':
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  log('exclusive_conflict');print('fixture: exclusive resource busy',file=sys.stderr,flush=True);raise SystemExit(17)
log('ready')
for line in sys.stdin:
 req=json.loads(line);rid=req.get('id');method=req.get('method')
 if rid is None:continue
 if method=='initialize':value={'protocolVersion':req['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'exclusive-fixture','version':'1'}}
 elif method=='tools/list':value={'tools':[{'name':'echo','description':'Benign fixture','inputSchema':{'type':'object','properties':{}}}]}
 elif method=='tools/call':
  log('tool_called');value={'content':[{'type':'text','text':'fixture-ok'}]}
 else:continue
 print(json.dumps({'jsonrpc':'2.0','id':rid,'result':value}),flush=True)
