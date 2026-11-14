#!/usr/bin/env python3
"""Secondary observation: a remote exact retarget loses Files' selected diff mode."""
import argparse, http.server, json, threading, urllib.parse
from repro_files_views import HERE, Fixture, API, Client, context, render, action, walk

class WithDiff(Fixture):
    def reply(self,method,url,body):
        u=urllib.parse.urlparse(url)
        if u.path=='/workspace/diff':
            q=urllib.parse.parse_qs(u.query); path=q.get('path',[''])[0]
            self.requests.append({'method':method,'path':u.path,'query':q,'body':body})
            return (200,{'patch':'diff fixture for '+path}) if path in self.files else (404,{'error':'Fixture file not found: '+path})
        return super().reply(method,url,body)

def mode(view):
    # segments serializes ghost buttons with an explicit selected value.
    segments=next(n for n in walk(view['root']) if n.get('type')=='button' and n.get('action')=='document-mode' and n.get('selected'))
    return segments['value']

def run(binary,shared):
    fixture=WithDiff(); server=http.server.ThreadingHTTPServer(('127.0.0.1',0),API);server.fixture=fixture
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start(); origin=f'http://127.0.0.1:{server.server_port}'
    a=Client(binary,origin,'rename-runtime');b=a if shared else Client(binary,origin,'remote-runtime')
    try:
        a.send(context('window-a'));a.one(render('panel','window-a'),'panel');a.one(render('local-doc','window-a','src/remote.rs'),'local-doc')
        b.send(context('window-b'));b.one(render('remote-doc','window-b','src/remote.rs'),'remote-doc')
        b.one(action('remote-doc',1,'document-mode',['src/remote.rs','diff']),'remote-doc',1)
        before=mode(b.output[-1]);assert before==['src/remote.rs','diff'],before
        # Drain any sibling views from the previous action.
        b.one(render('remote-doc','window-b','src/remote.rs'),'remote-doc',1)
        start=len(a.output)
        a.one(action('panel',1,'rename',{'value':'src','text':'lib'}),'panel',1)
        a.one(render('panel','window-a'),'panel',1)
        pairs=[(m['from'],m['to']) for m in a.output[start:] if m.get('type')=='retarget_document']
        assert ('src/remote.rs','lib/remote.rs') in pairs,pairs
        # This is the render sent by production Desktop retarget_arguments.
        b.one(render('remote-doc','window-b','lib/remote.rs'),'remote-doc',1)
        after=mode(b.output[-1])
        traces={'rename_runtime':a.close()}
        if b is not a:traces['remote_runtime']=b.close()
        result={'shared_runtime':shared,'retarget_pairs':pairs,'before':before,'after':after,'native_gui':False}
        (HERE/('mode-shared-control.json' if shared else 'mode-remote-repro.json')).write_text(json.dumps({'result':result,'traces':traces,'api':fixture.requests},ensure_ascii=False,indent=2)+'\n')
        return result
    finally:
        for c in {a,b}:
            if c.p.poll() is None:c.p.terminate();c.p.wait(timeout=3)
        server.shutdown();server.server_close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--require-fixed',action='store_true');args=parser.parse_args()
    binary=HERE/'target/debug/files'
    separate=run(binary,False);shared=run(binary,True)
    assert shared['after']==['lib/remote.rs','diff'],shared
    print(json.dumps([separate,shared],ensure_ascii=False,indent=2))
    if args.require_fixed:assert separate['after']==['lib/remote.rs','diff'],'cross-runtime retarget must preserve selected diff mode'
    else:assert separate['after']==['lib/remote.rs','file'],separate
