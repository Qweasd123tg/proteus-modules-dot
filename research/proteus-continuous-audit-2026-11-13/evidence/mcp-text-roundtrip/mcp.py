"""Synthetic fixture: records own input and optionally rejects missing --empty value."""
import json,os,sys
from pathlib import Path
mode,events=sys.argv[1:3]
argv=sys.argv[3:]
valid=True
if mode=='empty':
 i=argv.index('--empty');valid=(i+1<len(argv) and argv[i+1]=='')
with Path(events).open('a') as f:f.write(json.dumps({'argv':argv,'PREFIX':os.environ.get('PREFIX'),'valid':valid})+'\n')
if not valid:
 print('fixture --empty requires its explicit empty argument',file=sys.stderr);sys.exit(2)
for raw in sys.stdin:
 q=json.loads(raw);rid=q.get('id');method=q.get('method')
 if rid is None:continue
 if method=='initialize':result={'protocolVersion':q['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'text-roundtrip-fixture','version':'1'}}
 elif method=='tools/list':result={'tools':[{'name':'echo','inputSchema':{'type':'object'},'description':'Synthetic input recorder'}]}
 elif method=='tools/call':result={'content':[{'type':'text','text':'unused'}]}
 else:continue
 print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
