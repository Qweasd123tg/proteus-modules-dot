"""Pinned production runtime/workflow/native adapter against loopback only."""
import sys,pathlib,json,tempfile,threading,hashlib,shutil
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
E=pathlib.Path(__file__).resolve().parent
from runtime import App,BIN,WF,REF,CORE
REASON='The candidate lacks the required completion acknowledgement. Append exactly REVIEW_ACK to your next final answer.'
def run(workflow,mode,repeat):
    name=workflow.split('.')[1]+'-'+mode+'-'+str(repeat); d=E/name;d.mkdir(exist_ok=True)
    root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-review-continuation-'));cwd=root/'workspace';cwd.mkdir()
    records=[]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            system=json.dumps(body.get('system',[]))
            corrected='REVIEW_ACK' in system
            reply='FINAL REVIEW_ACK' if corrected else 'BASELINE CANDIDATE'
            records.append({'ordinal':len(records)+1,'has_review_reason':corrected,'has_profile_instruction':'PROFILE_ONLY_MARKER' in system,'request':body,'response_text':reply})
            response={'id':'fixture-'+str(len(records)),'type':'message','role':'assistant','model':'claude-sonnet-4-20250514','content':[{'type':'text','text':reply}],'stop_reason':'end_turn','usage':{'input_tokens':40,'output_tokens':5}}
            raw=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    http=ThreadingHTTPServer(('127.0.0.1',0),Provider);threading.Thread(target=http.serve_forever,daemon=True).start()
    config={'active_provider':'fixture','providers':{'fixture':{'provider':'anthropic','model':'claude-sonnet-4-20250514','stream':False}},'instructions':[{'kind':'Developer','text':'PROFILE_ONLY_MARKER: This is an isolated local test.','priority':128}],'module_config':{'model':{'anthropic':{'implementation':'anthropic','base_url':f'http://127.0.0.1:{http.server_address[1]}','api_key':'fixture-not-a-secret','stream':False}}},'modules':{'workflow':workflow,'context':'simple','policy':'allow_all','hooks':['review_fixture']},'tools':{'enabled':[]},'agent_control':{'surface':'none','max_depth':0},'runtime':{'workflow_timeout_ms':30000},'components':{'workflow':{'command':str(WF),'exports':{'workflow':{workflow:{}}}},'reference':{'command':str(REF),'exports':{'context':{'simple':{}},'policy':{'allow_all':{}},'model':{'anthropic':{}}}},'review':{'command':'python3','args':['-B',str(E/'review_hook.py'),str(d/'hook.jsonl'),mode],'exports':{'hook':{'review_fixture':{}}}}}}
    if mode=='injected_control':
        config['modules']['hooks'].append('hook.instructions')
        config['components']['reference']['exports']['hook']={'hook.instructions':{}}
        config['module_config']['hook']={'hook.instructions':{'text':REASON,'placement':'append'}}
    cp=root/'profile.json';cp.write_text(json.dumps(config));(d/'profile.json').write_text(json.dumps(config,indent=2))
    summary={'name':name,'workflow':workflow,'mode':mode,'root':str(root),'turns':[]}
    app=App(root,cp,cwd)
    try:
        for stage in ['fresh','warm']:
            start=len(records);r=app.call({'type':'send','id':stage,'text':'Produce a concise completion response. Do not inspect files or use tools.'})
            summary['turns'].append({'stage':stage,'result':r,'provider_requests':len(records)-start})
    finally:app.close();app.save(d,'warm-')
    journals=list(root.rglob('journal.jsonl'));assert len(journals)==1
    app=App(root,cp,cwd,journals[0].parent)
    try:
        start=len(records);r=app.call({'type':'send','id':'cold','text':'Produce a concise completion response after reopening. Do not inspect files or use tools.'})
        summary['turns'].append({'stage':'cold','result':r,'provider_requests':len(records)-start})
    finally:
        app.close();app.save(d,'cold-');http.shutdown();http.server_close()
        (d/'wire.json').write_text(json.dumps(records,indent=2));(d/'journal.jsonl').write_bytes(journals[0].read_bytes());(d/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True);return summary
if __name__=='__main__':
    cases=[]
    for mode in ['review','accept','injected_control']:
        for wf in ['coding.single_loop','coding.plan_execute_review','coding.codex_loop']:
            for repeat in range(3 if mode=='review' else 1):cases.append(run(wf,mode,repeat))
    (E/'summary.json').write_text(json.dumps(cases,indent=2))
    (E/'provenance.json').write_text(json.dumps({'core':'89997df995df7c39b713e16aba216ecb19c8f497','modules':'3270dc0f894eaf4d0360306052b806099b8f5351','binaries':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [BIN,WF,REF]}},indent=2))
