#!/usr/bin/env python3
"""Unmodified Git+SDK against loopback synthetic API. No actual repository writes."""
import argparse, hashlib, http.server, json, pathlib, subprocess, threading, urllib.parse
HERE = pathlib.Path(__file__).resolve().parent
SESSION = '/fixture/session'
A = {'hash':'a'*40, 'short':'a'*7, 'summary':'Alpha change', 'body':'Important Alpha explanation.\n\nRefs: ALPHA-123', 'parents':['0'*40]}
B = {'hash':'b'*40, 'short':'b'*7, 'summary':'Beta change', 'body':'Important Beta explanation.\n\nRefs: BETA-456', 'parents':['0'*40]}
CUSTOM = 'Unfinished user draft\n\nKeep my own explanation.'
def full(c): return c['summary']+'\n\n'+c['body']

def walk(v):
    if isinstance(v,dict):
        yield v
        for x in v.values(): yield from walk(x)
    elif isinstance(v,list):
        for x in v: yield from walk(x)

class API(http.server.BaseHTTPRequestHandler):
    def reply(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def changes(self):
        return {'repository':True,'branch':self.server.branch,'refs_revision':self.server.head['short'],
                'head':{k:self.server.head[k] for k in ['hash','short','summary']}, 'upstream':None,
                'ahead':0,'behind':0,
                'entries':[{'path':'fixture.txt','status':'modified','staged':True,'unstaged':False,'revision':'r1'}]}
    def do_GET(self):
        url=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(url.query)
        rec={'method':'GET','path':url.path,'query':q}; self.server.requests.append(rec)
        if url.path=='/workspace/changes':
            self.server.changes_reads += 1
            if self.server.scenario=='same-branch-head-change' and self.server.changes_reads>=2:
                self.server.head=B.copy()
            data=self.changes()
        elif url.path=='/workspace/branches': data={'branches':[{'name':'main'},{'name':'beta'}]}
        elif url.path=='/workspace/log': data={'entries':[self.server.head.copy()],'more':False}
        elif url.path=='/workspace/commit':
            self.server.detail_reads+=1
            if self.server.fail_details:
                self.server.fail_details=False; rec['status']=503
                self.reply(503,{'error':'synthetic temporary commit details unavailable'}); return
            requested=q.get('hash',[''])[0]
            data=(A if requested in [A['short'],A['hash']] else B).copy()
            data['files']=[]
        else:
            self.server.unexpected.append(rec); self.reply(404,{'error':'unexpected'}); return
        rec['status']=200; self.reply(200,data)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        path=urllib.parse.urlparse(self.path).path
        rec={'method':'POST','path':path,'body':body,'branch':self.server.branch,'head_before':self.server.head.copy()}
        self.server.requests.append(rec)
        if path=='/workspace/checkout':
            self.server.branch=body['branch']; self.server.head=B.copy(); data=self.changes()
        elif path=='/workspace/commit':
            if self.server.scenario=='failed-commit-control':
                rec['status']=503; self.reply(503,{'error':'synthetic commit failed'}); return
            # Only model the response. Never spawn git or touch a repository.
            rec['status']=200
            data={'commit':self.server.head.copy(),'changes':self.changes()}
        else:
            self.server.unexpected.append(rec); self.reply(405,{'error':'unexpected mutation'}); return
        rec['status']=200; self.reply(200,data)
    def log_message(self,*args): pass

def sequence(scenario):
    acts=[]
    if scenario in ['typed-draft-control','normal-checkout-control']: acts += [('message',CUSTOM)]
    if scenario!='normal-checkout-control': acts += [('amend',None)]
    if scenario in ['failed-details','same-branch-head-change']: acts += [('refresh',None)]
    if scenario in ['checkout-after-amend','rearm-after-checkout-control','normal-checkout-control']:
        acts += [('checkout','beta')]
    if scenario=='rearm-after-checkout-control': acts += [('amend',None),('amend',None)]
    acts += [('commit',None)]
    return [{'type':'action','view':'panel','sequence':n,'action':a,'value':v} for n,(a,v) in enumerate(acts,1)]

def run(binary,scenario):
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),API) as api:
        api.scenario=scenario; api.requests=[]; api.unexpected=[]; api.head=A.copy(); api.branch='main'
        api.detail_reads=0; api.changes_reads=0; api.fail_details=scenario in ['failed-details','typed-draft-control']
        threading.Thread(target=api.serve_forever,daemon=True).start()
        messages=[{'type':'hello','protocol':4,'features':[],
                   'server':{'origin':f'http://127.0.0.1:{api.server_port}','token':'synthetic'}},
                  {'type':'context','context':'window','workspace':'/fixture/workspace','session_dir':SESSION},
                  {'type':'render','context':'window','session_dir':SESSION,'surface':'panel','view':'panel'}]+sequence(scenario)
        proc=subprocess.run([str(binary)],input=''.join(json.dumps(m)+'\n' for m in messages),capture_output=True,text=True,timeout=15)
        api.shutdown()
        assert proc.returncode==0 and not proc.stderr,(proc.returncode,proc.stderr)
        assert not api.unexpected,api.unexpected
        output=[json.loads(l) for l in proc.stdout.splitlines()]
        trace=[]
        for out in output:
            if out.get('type')=='view' and out.get('view')=='panel':
                nodes=list(walk(out['root']))
                inp=next(n for n in nodes if n.get('type')=='input' and n.get('id')=='message')
                amend=next(n for n in nodes if n.get('action')=='amend')
                commit=next(n for n in nodes if n.get('action')=='commit' and n.get('type')!='input')
                danger=[n for n in nodes if n.get('tone')=='danger']
                trace.append({'sequence':out.get('sequence'),'draft':inp['value'],'amend':amend['checked'],
                              'commit':commit,'danger':danger})
        posts=[r for r in api.requests if r['method']=='POST' and r['path']=='/workspace/commit']
        assert len(posts)==1,posts
        commit=posts[0]
        expected=full(A)
        if scenario=='failed-details': expected=A['summary']
        if scenario in ['typed-draft-control','normal-checkout-control']: expected=CUSTOM
        if scenario=='rearm-after-checkout-control': expected=full(B)
        assert commit['body']['message']==expected,(scenario,commit)
        assert commit['body']['amend']==(scenario!='normal-checkout-control')
        if scenario in ['checkout-after-amend','same-branch-head-change','rearm-after-checkout-control','normal-checkout-control']:
            assert commit['head_before']['hash']==B['hash']
        precommit=trace[-2]
        assert not precommit['danger'],precommit
        assert not precommit['commit'].get('disabled',False),precommit
        if scenario=='failed-commit-control': assert trace[-1]['draft']==full(A) and trace[-1]['amend']
        else: assert trace[-1]['draft']=='' and not trace[-1]['amend']
        record={'scenario':scenario,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
                'input':messages,'output':output,'trace':trace,'http':api.requests,
                'stderr':proc.stderr,'returncode':proc.returncode,'native_gui_run':False,'real_git_mutation':False}
        (HERE/f'{scenario}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        return {'scenario':scenario,'message_sent':commit['body']['message'],'amend_sent':commit['body']['amend'],
                'target_head':commit['head_before']['short'],'target_branch':commit['branch'],
                'details_reads':api.detail_reads,'draft_after':trace[-1]['draft'],'warnings_before_commit':precommit['danger']}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--binary',type=pathlib.Path,default=HERE/'target/debug/git'); p.add_argument('--require-fixed',action='store_true'); args=p.parse_args()
    results=[run(args.binary.resolve(),s) for s in ['healthy-amend-control','failed-details','typed-draft-control',
             'failed-commit-control','checkout-after-amend','same-branch-head-change','rearm-after-checkout-control','normal-checkout-control']]
    print(json.dumps(results,ensure_ascii=False,indent=2))
    if args.require_fixed:
        failed=next(r for r in results if r['scenario']=='failed-details')
        assert failed['message_sent']==full(A),'amend must not silently submit a partial message when full message loading failed'
if __name__=='__main__': main()
