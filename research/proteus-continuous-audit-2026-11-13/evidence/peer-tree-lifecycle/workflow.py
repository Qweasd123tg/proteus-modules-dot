"""Model-free lifecycle diagnostic; all subprocesses and files are fixture-owned."""
import json, os, shlex, subprocess, sys, time, uuid
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from component_runtime import ProtocolError, run_component

def initialize(params):
    exports=[]
    for e in params['exports']:
        if (e['slot'],e['contract_version']) != ('workflow','v20'): raise ProtocolError('workflow expected')
        exports.append({k:e[k] for k in ('slot','module_id','contract_version','composition')}|{'module_features':[],'config_schema':None})
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}

def invoke(context, method, params):
    if method!='run': raise ProtocolError('run expected')
    task=params['task']; cwd=Path(task['cwd'])
    def log(name, **extra):
        with (cwd/'markers.jsonl').open('a') as f:
            f.write(json.dumps({'name':name,'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),'time':time.time(),**extra})+'\n')
    def tool(name,args):
        call={'id':str(uuid.uuid4()),'name':name,'args':args,'surface':'function','raw_arguments':None}
        result=context.host_call('host.tools.execute_batch',{'task':task,'calls':[call]})[0]
        log(name,result=result)
        return result
    log('workflow-start',prompt=task['text'])
    if task['text'].startswith('root-'):
        mode=task['text'][5:]
        tool('spawn_agent',{'task_name':'peer','agent_type':'helper','message':'child-'+mode})
        if mode=='shell_cancel':
            # Wait for the shell child to start so cancellation targets an active execution.
            deadline=time.monotonic()+8
            while time.monotonic()<deadline and not any(json.loads(x)['name']=='helper-started' for x in (cwd/'markers.jsonl').read_text().splitlines()): time.sleep(.02)
            time.sleep(.4)
            tool('interrupt_agent',{'target':'peer'})
        result=tool('wait_agent',{'timeout_ms':15000})
        text=result['output']
    else:
        mode=task['text'][6:]
        args=[sys.executable,str(Path(__file__).with_name('helper.py')),str(cwd),str(os.getpid()),str(os.getppid()),mode]
        if mode.startswith('shell_'):
            result=tool('exec_command',{'cmd':shlex.join(args),'tty':False,'yield_time_ms':10000,'with_escalated_permissions':True})
            text=json.dumps(result)
        else:
            # Inherits the component's ordinary group, with no fork or detach.
            subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            time.sleep(30)
            text='child finished'
    output={'text':text,'metadata':None}
    return {'status':'success','result':{'output':output,'new_messages':[{'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
