"""Worktree branch identity and cleanup error fixture with real stdio peers."""
import json, os, sys, time, uuid, subprocess
from pathlib import Path
from component_runtime import ProtocolError, run_component
MARKERS=Path(sys.argv[1])
def initialize(params):
    exports=[]
    for e in params['exports']:
        if (e['slot'],e['module_id'],e['contract_version']) != ('workflow','worktree_probe','v20'):
            raise ProtocolError('unexpected workflow')
        exports.append({k:e[k] for k in ('slot','module_id','contract_version','composition')} | {'module_features':[],'config_schema':None})
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}
def assistant(text):
    return {'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}
def invoke(context,method,params):
    if method!='run':raise ProtocolError('unexpected method')
    task=params['task'];prompt=task['text'];cwd=Path(task['cwd'])
    def log(name,extra):
        with MARKERS.open('a') as f:
            f.write(json.dumps({'name':name,'prompt':prompt,'cwd':str(cwd),'pid':os.getppid(),'worker_pid':os.getpid(),'session':params['runtime']['conversation']['session_id'],'time':time.time(),'extra':extra})+'\n')
    def git(*args):
        result=subprocess.run(['git','-C',str(cwd),*args],text=True,capture_output=True)
        if result.returncode:raise RuntimeError(str(result))
        return result.stdout
    def tool(args,call_id):
        call={'id':call_id,'name':'task','args':args,'surface':'function','raw_arguments':None}
        return context.host_call('host.tools.execute_batch',{'task':task,'calls':[call]})[0]
    if prompt.startswith('root-'):
        result=tool({'agent_type':'coder','prompt':prompt.replace('root-','child-',1)},'call_0')
        log('task_result',result)
        task_id=(result.get('metadata') or {}).get('child_thread_id')
        followup=tool({'agent_type':'coder','prompt':'resume-read','task_id':task_id},'call_1')
        log('resume_result',followup);text=json.dumps({'first':result,'resume':followup})
    elif prompt=='resume-read':
        log('resume_reached',{'branch':git('branch','--show-current'),'content':(cwd/'base.py').read_text()})
        text='Read-only resume reached original peer with completed implementation.'
    else:
        original=git('branch','--show-current').strip()
        if 'switched' in prompt:git('switch','-c','feature/implementation')
        if 'renamed' in prompt:git('branch','-m','feature/implementation')
        target=cwd/'base.py';target.write_text('def work():\n    return "unique child result"\n')
        git('add',str(target));git('commit','-qm','implement requested function')
        log('child_written',{'target':str(target),'content':target.read_text(),'original_branch':original,'current_branch':git('branch','--show-current').strip(),'status':git('status','--porcelain'),'head':git('rev-parse','HEAD')})
        text='Implemented requested function and committed the change.'
    output={'text':text,'metadata':None}
    context.host_call('host.events.emit',{'event':{'TurnFinished':{'output':output}}})
    return {'status':'success','result':{'output':output,'new_messages':[assistant(text)],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
