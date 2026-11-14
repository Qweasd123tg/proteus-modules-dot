#!/usr/bin/env python3
"""No fake time: production Files/SDK poll=5 seconds, synthetic API only."""
import argparse, http.server, json, pathlib, threading, time
from wire_fixture import Fixture, API, Client, context, render, walk, SESSION
HERE=pathlib.Path(__file__).resolve().parent

def content(msg):
    return next(n['text'] for n in walk(msg['root']) if n.get('type')=='code')

def run(binary,announced):
    fixture=Fixture(); server=http.server.ThreadingHTTPServer(('127.0.0.1',0),API); server.fixture=fixture
    threading.Thread(target=server.serve_forever,daemon=True).start()
    c=Client(binary,f'http://127.0.0.1:{server.server_port}','files')
    try:
        c.send(context('window')); c.one(render('document','window','src/remote.rs'),'document')
        first=c.output[-1]; expected='external change fixture'
        event={'type':'event','context':'window','event':'navigation_changed','session_dir':SESSION,'document':'src/remote.rs'}
        if announced:
            c.one(event,'document')
        fixture.files['src/remote.rs']=expected
        began=time.monotonic(); polls=[]
        for _ in range(1 if announced else 2):
            polls.append(c.until(lambda m:m.get('type')=='view' and m.get('view')=='document')[-1])
        poll=polls[-1]; elapsed=time.monotonic()-began
        requests_after_poll=sum(r['path']=='/workspace/file' for r in fixture.requests)
        # A navigation event carries the missing active document, and should unblock freshness.
        c.one(event,'document'); recovered=c.output[-1]
        result={'initial_navigation_announced':announced,'initial_content':content(first),'after_poll_content':content(poll),'poll_cycles':len(polls),'poll_contents':[content(m) for m in polls],'poll_elapsed_seconds':round(elapsed,3),'file_api_requests_after_poll':requests_after_poll,'after_navigation_content':content(recovered),'after_navigation_file_api_requests':sum(r['path']=='/workspace/file' for r in fixture.requests),'native_gui':False}
        trace=c.close(); name='active-announced-control' if announced else 'active-missing-repro'
        (HERE/(name+'.json')).write_text(json.dumps({'result':result,'trace':trace,'api':fixture.requests},ensure_ascii=False,indent=2)+'\n')
        assert elapsed>=4.8,result
        assert result['after_navigation_content']==expected,result
        return result
    finally:
        if c.p.poll() is None:c.p.terminate();c.p.wait(timeout=3)
        server.shutdown();server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=pathlib.Path,default=HERE/'target/debug/files');p.add_argument('--require-fixed',action='store_true');args=p.parse_args()
    results=[run(args.binary,False),run(args.binary,True)]
    assert results[1]['after_poll_content']=='external change fixture'; assert results[1]['file_api_requests_after_poll']==2
    if args.require_fixed: assert results[0]['after_poll_content']=='external change fixture',results[0]
    else: assert results[0]['after_poll_content']=='remote fixture'; assert results[0]['file_api_requests_after_poll']==1
    print(json.dumps(results,ensure_ascii=False,indent=2))
