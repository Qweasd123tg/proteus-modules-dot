#!/usr/bin/env python3
"""Positive controls: active document response changes and transient failure recover."""
import argparse,http.server,json,pathlib,threading,time,urllib.parse
from wire_fixture import Fixture,API,Client,context,render,walk,SESSION
HERE=pathlib.Path(__file__).resolve().parent
class DocumentFixture(Fixture):
    def __init__(self):super().__init__();self.kind='text';self.fail=False
    def reply(self,method,url,body):
        u=urllib.parse.urlparse(url)
        if u.path=='/workspace/file':
            self.requests.append({'method':method,'path':u.path,'query':urllib.parse.parse_qs(u.query),'kind':self.kind,'failure':self.fail})
            if self.fail:self.fail=False;return 503,{'error':'temporary document read failure'}
            return 200,{'kind':self.kind,'text':'current content' if self.kind=='text' else None}
        return super().reply(method,url,body)
def rendered(msg):
    return [{'type':n['type'],'text':n['text'],'tone':n.get('tone')} for n in walk(msg['root']) if n.get('type') in ['code','text'] and 'text' in n]
def run(binary):
    fixture=DocumentFixture();server=http.server.ThreadingHTTPServer(('127.0.0.1',0),API);server.fixture=fixture;threading.Thread(target=server.serve_forever,daemon=True).start();c=Client(binary,f'http://127.0.0.1:{server.server_port}','files')
    try:
        c.send(context('window'));c.one(render('document','window','src/remote.rs'),'document');c.one({'type':'event','event':'navigation_changed','context':'window','session_dir':SESSION,'document':'src/remote.rs'},'document');results=[]
        for kind,fail in [('binary',False),('too_large',False),('text',False),('text',True),('text',False)]:
            fixture.kind=kind;fixture.fail=fail;began=time.monotonic();msg=c.until(lambda m:m.get('type')=='view' and m.get('view')=='document')[-1];results.append({'fixture_kind':kind,'fixture_failure':fail,'rendered':rendered(msg),'elapsed_seconds':round(time.monotonic()-began,3)})
        assert any(n['text']=='Двоичный файл' for n in results[0]['rendered']);assert any('512' in n['text'] for n in results[1]['rendered']);assert any(n['type']=='code' for n in results[2]['rendered']);assert any(n['tone']=='danger' for n in results[3]['rendered']);assert any(n['type']=='code' for n in results[4]['rendered'])
        trace=c.close();data={'result':results,'trace':trace,'api':fixture.requests,'native_gui':False};(HERE/'document-controls.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(json.dumps(results,ensure_ascii=False,indent=2))
    finally:
        if c.p.poll() is None:c.p.terminate();c.p.wait(timeout=3)
        server.shutdown();server.server_close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=pathlib.Path,default=HERE/'target/debug/files');a=p.parse_args();run(a.binary)
