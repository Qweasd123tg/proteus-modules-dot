#!/usr/bin/env python3
"""Real Files+SDK process with real 5s timer; synthetic loopback API only.
The selected/visible/hidden documents come from the real proteus-tabs probe.
"""
import argparse, http.server, json, pathlib, threading, time
from wire_fixture import Fixture, API, Client, context, render, walk, SESSION
HERE=pathlib.Path(__file__).resolve().parent
VIEWS={'a-left':'left.rs','b-right':'right.rs','c-hidden':'hidden.rs'}

def content(msg):
    return next(n['text'] for n in walk(msg['root']) if n.get('type')=='code')
def state(messages):
    return {VIEWS[m['view']]:content(m) for m in messages if m.get('type')=='view' and m.get('view') in VIEWS}

def run(binary):
    layouts=json.loads((HERE/'tabs-layout.json').read_text())
    fixture=Fixture(); fixture.files={p:'OLD '+p for p in VIEWS.values()}
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),API); server.fixture=fixture
    threading.Thread(target=server.serve_forever,daemon=True).start()
    c=Client(binary,f'http://127.0.0.1:{server.server_port}','files')
    def read_all(): return state(c.until(lambda m:m.get('type')=='view' and m.get('view')=='c-hidden'))
    def event(document, kind='navigation_changed'):
        c.send({'type':'event','context':'window','event':kind,'session_dir':SESSION,'document':document})
        return read_all()
    def counts():
        return {p:sum(r['path']=='/workspace/file' and r['query'].get('path')==[p] for r in fixture.requests) for p in VIEWS.values()}
    try:
        c.send(context('window'))
        for view,path in VIEWS.items(): c.one(render(view,'window',path),view)
        # Explicit correctly initialized navigation: not the old startup bug.
        first=event(layouts['two_documents']['active_document'])
        fixture.files={p:'NEW '+p for p in VIEWS.values()}
        start=time.monotonic(); polls=[read_all(),read_all()]; elapsed=time.monotonic()-start
        counts_after_two=counts()
        focused_right=event(layouts['right_focused']['active_document'])
        # Chat now focused, right.rs still visible according to TabLayout::visible().
        before_chat=event(layouts['chat_and_document']['active_document'])
        fixture.files['right.rs']='NEWER right.rs'
        start=time.monotonic(); chat_poll=read_all(); chat_elapsed=time.monotonic()-start
        counts_after_chat=counts()
        # Existing invalidation still works. This is a useful control, not a fix.
        settled=event(None,'run_settled')
        result={'initial':first,'two_documents_visible':layouts['two_documents']['visible'],
                'explicit_active_document':layouts['two_documents']['active_document'],
                'two_poll_seconds':round(elapsed,3),'polls':polls,
                'file_reads_after_two_polls':counts_after_two,
                'after_focusing_right':focused_right,
                'chat_and_document_visible':layouts['chat_and_document']['visible'],
                'chat_active_document':layouts['chat_and_document']['active_document'],
                'before_chat_poll':before_chat,'after_chat_poll':chat_poll,
                'chat_poll_seconds':round(chat_elapsed,3),
                'file_reads_after_chat_poll':counts_after_chat,
                'after_run_settled':settled,
                'native_gui_run':False,'real_tabs_crate':True,'real_files_and_sdk':True}
        trace=c.close()
        (HERE/'split-refresh.json').write_text(json.dumps({'result':result,'trace':trace,'api':fixture.requests},ensure_ascii=False,indent=2)+'\n')
        assert elapsed>=9.8 and chat_elapsed>=4.8,result
        assert polls[-1]['left.rs']=='NEW left.rs',result
        assert focused_right['right.rs']=='NEW right.rs',result
        assert polls[-1]['hidden.rs']=='OLD hidden.rs',result
        assert settled['right.rs']=='NEWER right.rs',result
        return result
    finally:
        if c.p.poll() is None:c.p.terminate();c.p.wait(timeout=3)
        server.shutdown();server.server_close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binary',type=pathlib.Path,default=pathlib.Path('/workspace/shared/trace-files-sdk-deep-evidence/target/debug/files'));parser.add_argument('--require-fixed',action='store_true');args=parser.parse_args()
    result=run(args.binary)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    if args.require_fixed:
        assert result['polls'][-1]['right.rs']=='NEW right.rs', 'Visible nonfocused split document must refresh on polls'
        assert result['after_chat_poll']['right.rs']=='NEWER right.rs', 'Visible split document must refresh while chat focused'
    else:
        assert result['polls'][-1]['right.rs']=='OLD right.rs',result
        assert result['after_chat_poll']['right.rs']=='NEW right.rs',result
        assert result['file_reads_after_two_polls']=={'left.rs':3,'right.rs':1,'hidden.rs':1},result
