"""Deterministic workflow fixture. The production facade, peer, lifecycle and Git run unchanged."""
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
    if prompt.startswith('root-'):
        log('root_started',{'task':task})
        call={'id':'call_0','name':'task','args':{'agent_type':'coder','prompt':prompt.replace('root-','child-',1)},'surface':'function','raw_arguments':None}
        result=context.host_call('host.tools.execute_batch',{'task':task,'calls':[call]})[0]
        log('task_result',result);text=result['output']
    else:
        if 'exclude-' in prompt:
            log('child_noop',{'task':task});text='Inspected the checkout; no files changed.'
        else:
            target=cwd/('service/base.py' if prompt=='child-index-sparse' else 'base.py');before=target.read_text() if target.exists() else None
            initial_flags=git('ls-files','-v')
            target.parent.mkdir(parents=True,exist_ok=True)
            if prompt=='child-index-assume':git('update-index','--assume-unchanged','base.py')
            if prompt=='child-index-skip':git('update-index','--skip-worktree','base.py')
            target.write_text('RESULT = "new child implementation"\n')
            if prompt == 'child-staged':git('add','base.py')
            if 'committed' in prompt:git('add','base.py');git('commit','-qm','child result')
            log('child_written',{'target':str(target),'before':before,'initial_flags':initial_flags,'content':target.read_text(),'status':git('status','--porcelain'),'status_all':git('status','--porcelain','--untracked-files=all'),'index_flags':git('ls-files','-v'),'task':task})
            text='Updated '+str(target.relative_to(cwd))+' in the delegated working directory.'
    output={'text':text,'metadata':None}
    context.host_call('host.events.emit',{'event':{'TurnFinished':{'output':output}}})
    return {'status':'success','result':{'output':output,'new_messages':[assistant(text)],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
