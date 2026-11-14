"""Synthetic workflow; exercises unchanged task facade + resident peers + MCP."""
import json,os,sys,time,uuid,subprocess
from pathlib import Path
from component_runtime import ProtocolError,run_component
MARKERS=Path(sys.argv[1])
def initialize(params):
    exports=[]
    for e in params['exports']:
        if (e['slot'],e['module_id'],e['contract_version'])!=('workflow','git_trace','v20'):raise ProtocolError('unexpected workflow')
        exports.append({k:e[k] for k in ('slot','module_id','contract_version','composition')}|{'module_features':[],'config_schema':None})
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}
def assistant(text):
    return {'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}
def invoke(context,method,params):
    if method!='run':raise ProtocolError('unexpected method')
    task=params['task'];prompt=task['text'];cwd=Path(task['cwd']);parts=prompt.split(':');mode=parts[1];n=int(parts[2])
    def log(name,extra):
        with MARKERS.open('a') as f:f.write(json.dumps({'name':name,'prompt':prompt,'cwd':str(cwd),'peer_pid':os.getppid(),'worker_pid':os.getpid(),'session':params['runtime']['conversation']['session_id'],'time':time.time(),'extra':extra})+'\n')
    def tool(cid,name,args):return context.host_call('host.tools.execute_batch',{'task':task,'calls':[{'id':cid,'name':name,'args':args,'surface':'function','raw_arguments':None}]})[0]
    if parts[0]=='root':
        cid=('call/'+str(0) if n==0 else 'call:'+str(0)) if mode in ['reuse-same','reuse-noidle','reuse-shared'] else ('call_'+str(n) if mode.startswith('reuse-') or (mode=='hook' and n==2) else 'call_0')
        result=tool(cid,'task',{'agent_type':'coder','prompt':'child:'+mode+':'+str(n)});log('task_result',result);text=result['output']
    elif mode.startswith('reuse-'):
        # MCP protocol intentionally does not carry invocation cwd. The server
        # legitimately serves relative files from its host-configured launch cwd.
        result=tool('mcp_'+str(n),'local_files__read_base',{});log('mcp_result',result)
        log('absolute_file_control',{'content':(cwd/'base.py').read_text()})
        text=result['output']
    elif mode.startswith('env-'):
        target=cwd/'base.py';before=target.read_text();target.write_text('RESULT = "synthetic child edit"\n')
        if mode.endswith('-commit'):
            for args in [('add','base.py'),('commit','-qm','Synthetic delegated change')]:
                result=subprocess.run(['git','-C',str(cwd),*args],capture_output=True,text=True)
                if result.returncode:raise RuntimeError(str(result))
        log('child_written',{'before':before,'after':target.read_text(),'target':str(target)});text='Updated base.py.'
    else:
        log('child_noop',{});text='No-op task completed.'
    output={'text':text,'metadata':None};context.host_call('host.events.emit',{'event':{'TurnFinished':{'output':output}}})
    return {'status':'success','result':{'output':output,'new_messages':[assistant(text)],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
