"""Local MCP fixture; only effect is writing its own synthetic lifecycle log."""
import json,sys
label,events=sys.argv[1:]
with open(events,'a') as f:f.write(label+':spawn\n')
for raw in sys.stdin:
 q=json.loads(raw);rid=q.get('id');method=q.get('method')
 if rid is None:continue
 if method=='initialize':result={'protocolVersion':q['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':label,'version':'1'}}
 elif method=='tools/list':result={'tools':[{'name':'echo','inputSchema':{'type':'object'},'description':'Fixture no side effects'}]}
 elif method=='tools/call':result={'content':[{'type':'text','text':label}]}
 else:continue
 print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
