"""Benign persistent MCP fixture. Reads only synthetic base.py in launch cwd."""
import json,os,sys
from pathlib import Path
initial_cwd=os.getcwd();calls=0
for line in sys.stdin:
    req=json.loads(line);method=req.get('method');rid=req.get('id')
    if rid is None:continue
    if method=='initialize':res={'protocolVersion':'2025-06-18','capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'local-files-fixture','version':'1.0'}}
    elif method=='tools/list':res={'tools':[{'name':'read_base','description':'Read the synthetic base.py in the configured workspace.','inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':{'readOnlyHint':True}}]}
    elif method=='tools/call':
        calls+=1;data={'pid':os.getpid(),'initial_cwd':initial_cwd,'calls':calls}
        try:data['current_cwd']=os.getcwd()
        except OSError as e:data['cwd_error']=str(e)
        try:data['content']=Path('base.py').read_text();failed=False
        except OSError as e:data['read_error']=str(e);failed=True
        res={'content':[{'type':'text','text':json.dumps(data)}],'structuredContent':data,'isError':failed}
    else:
        print(json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'unsupported'}}),flush=True);continue
    print(json.dumps({'jsonrpc':'2.0','id':rid,'result':res}),flush=True)
