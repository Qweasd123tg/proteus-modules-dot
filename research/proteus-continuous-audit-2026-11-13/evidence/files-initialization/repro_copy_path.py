#!/usr/bin/env python3
"""Real unchanged Files/SDK binary; only loopback synthetic API."""
import argparse, hashlib, http.server, json, pathlib, threading
from wire_fixture import Fixture, API, Client, context, render, action, walk, SESSION
HERE=pathlib.Path(__file__).resolve().parent

def copy_value(message):
    return next(n['value'] for n in walk(message['root']) if n.get('action')=='copy')

def run(binary):
    fixture=Fixture(); server=http.server.ThreadingHTTPServer(('127.0.0.1',0),API); server.fixture=fixture
    threading.Thread(target=server.serve_forever,daemon=True).start()
    c=Client(binary,f'http://127.0.0.1:{server.server_port}','files')
    try:
        c.send(context('window-a'))
        c.one(render('document-a','window-a','src/remote.rs'),'document-a')
        first=c.output[-1]; before_requests=list(fixture.requests)
        initial=copy_value(first)
        c.send(action('document-a',1,'copy',initial))
        before_copy=c.until(lambda m:m.get('type')=='clipboard')[-1]['text']
        # Barrier to consume the render caused by action.
        c.one(render('document-a','window-a','src/remote.rs'),'document-a',1)
        # Same session in another context: first opening its Files panel causes lazy cwd init.
        c.send(context('window-b'))
        c.one(render('panel-b','window-b'),'panel-b')
        c.one(render('document-a','window-a','src/remote.rs'),'document-a',1)
        after=c.output[-1]; final=copy_value(after)
        c.send(action('document-a',2,'copy',final))
        after_copy=c.until(lambda m:m.get('type')=='clipboard')[-1]['text']
        result={'initial_button_value':initial,'initial_clipboard':before_copy,'after_sibling_panel_button_value':final,'after_sibling_panel_clipboard':after_copy,'cwd_metadata_requests_before_panel':sum(r['path']=='/sessions/current' for r in before_requests),'cwd_metadata_requests_after_panel':sum(r['path']=='/sessions/current' for r in fixture.requests),'same_document_content_before_after':next(n['text'] for n in walk(first['root']) if n.get('type')=='code')==next(n['text'] for n in walk(after['root']) if n.get('type')=='code'),'native_gui':False}
        trace=c.close()
        (HERE/'copy-path.json').write_text(json.dumps({'result':result,'trace':trace,'api':fixture.requests},ensure_ascii=False,indent=2)+'\n')
        return result
    finally:
        if c.p.poll() is None:c.p.terminate();c.p.wait(timeout=3)
        server.shutdown();server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=pathlib.Path,default=HERE/'target/debug/files');p.add_argument('--require-fixed',action='store_true');args=p.parse_args()
    r=run(args.binary)
    assert r['same_document_content_before_after']; assert r['after_sibling_panel_clipboard']=='/fixture/project/src/remote.rs'
    assert r['cwd_metadata_requests_before_panel']==0 and r['cwd_metadata_requests_after_panel']==1
    if args.require_fixed: assert r['initial_clipboard']=='/fixture/project/src/remote.rs',r
    else: assert r['initial_clipboard']=='src/remote.rs',r
    print(json.dumps(r,ensure_ascii=False,indent=2))
