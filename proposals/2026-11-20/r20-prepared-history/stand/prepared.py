"""Stage stock-generated disposable caches at precisely the same absolute session paths on each fresh run."""
import hashlib, json, os, selectors, shutil, signal, subprocess, tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode

def disk_name(key):
    return '.storage-cache-'+hashlib.sha256(key.encode()).hexdigest()+'.json'
HEAD=disk_name('display-view-v1-head')

@contextmanager
def case(path):
    """Private synthetic temporary tree, not an existing user/config directory."""
    path.mkdir(mode=0o700,parents=False,exist_ok=False)
    try: yield path
    finally: shutil.rmtree(path)

def setup(a,cfg,wire_log=None):
    import sys
    sys.path[:0]=[str(a.source/'examples/performance/history-scale'),str(a.source/'examples/performance/common')]
    from fixtures import profile
    config=cfg/'config.toml'
    executable=str(a.worker)
    args=''
    if wire_log:
        executable=str(Path(sys.executable).resolve())
        args='\nargs='+json.dumps([str(Path(__file__).with_name('wire.py')),str(a.worker),str(wire_log)])
    config.write_text(profile(a.reference,0).replace('[modules]\n','[modules]\nsession_storage="jsonl"\n')+'\n[components.store]\ncommand='+json.dumps(executable)+args+'\n[components.store.exports.session_storage.jsonl]\n[components.store.transport]\nmax_frame_bytes=134217728\n')
    return config

def inventory(dirs):
    m=hashlib.sha256(); stats=[]
    for i,d in enumerate(dirs):
        rows=[]
        for f in sorted(d.glob('.storage-cache-*.json')):
            with f.open('rb') as fd:h=hashlib.file_digest(fd,'sha256').hexdigest()
            rows.append((f.name,f.stat().st_size,h))
        m.update(json.dumps([i,rows],separators=(',',':')).encode())
        stats.append({'files':len(rows),'bytes':sum(k[1] for k in rows),'has_head':(d/HEAD).is_file()})
    return {'sha256':m.hexdigest(),'archives':stats}

def prime(a,out,root,manifest,dirs,active):
    from archives import check,corpus,require,save
    import time
    cwd=a.golden/'work'; config=setup(a,root/'config'); rows=manifest['rows']
    core=a.prime_core
    result={'natural':True,'case_path':str(root),'canonical_before':corpus(dirs),'pages':[],'core_sha256':a.prime_sha,'worker_sha256':a.worker_sha256}
    with (out/'preparer.log').open('w') as log:
        p=subprocess.Popen([core,'--config',config,'--cwd',cwd,'--resume-session',active,'server','http','--host','127.0.0.1','--port','0','--ready-stdout'],cwd=cwd,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout,selectors.EVENT_READ);require(sel.select(60),'prep ready timeout')
                frame=json.loads(p.stdout.readline());require(frame['type']=='http_ready','prep frame')
            origin=frame['origin'];require(origin.startswith('http://127.0.0.1:'),'not loopback')
            def api(route,body=None):
                req=Request(origin+route,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
                with urlopen(req,timeout=a.observe) as response:return json.load(response)
            for i,d in enumerate(dirs[:4]):
                started=time.monotonic_ns()
                page=api('/history/page?'+urlencode(dict(session_dir=str(d))))
                rev=check(page,100+i,rows-50,rows)
                built=time.monotonic_ns()
                first=api('/history/page?'+urlencode(dict(session_dir=str(d),before=50,revision=rev)))
                require(rev==check(first,100+i,0,rows),'primed wrong pinned page')
                result['pages'].append({'index':i,'revision':rev,'prepare_latest_ms':round((built-started)/1e6,3),'latest_size':len(page['messages']),'pinned_size':len(first['messages'])})
            from proc_sampler import Tree
            tree=Tree(p.pid)
            members=[(item['pid'],item['start_ticks']) for item in tree.sample()['processes']]
            result['preparation_processes']=[{'pid':pid,'start_ticks':tick} for pid,tick in members]
            require(len(members)>=3,'missing prep worker/reference identities')
            api('/shutdown',{})
        finally:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
            p.stdout.close()
            # Also reap any remaining processes in this exclusively owned process group.
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
    import time
    from proc_sampler import read_stat
    def live(pid,tick):
        try:
            s=read_stat(Path('/proc')/str(pid))
            return s['start_ticks']==tick and s['state']!='Z'
        except (FileNotFoundError,ProcessLookupError):return False
    for _ in range(100):
        if not any(live(pid,tick) for pid,tick in members):break
        time.sleep(.05)
    result['preparation_process_exited']=p.poll() is not None and not any(live(pid,tick) for pid,tick in members)
    require(result['preparation_process_exited'],'preparation process survived restart')
    result['canonical_after']=corpus(dirs)
    require(result['canonical_before']==result['canonical_after'],'prime mutated canonical archive')
    for i,(d,page) in enumerate(zip(dirs,result['pages'])):
        require((d/HEAD).is_file() and (d/disk_name('display-revision-'+page['revision'])).is_file(),'stock did not persist both natural headers')
    require(not any(list(d.glob('.storage-cache-*')) for d in dirs[4:]),'priming touched unselected')
    result['inventory']=inventory(dirs[:4])
    result['physical_identity']=physical(dirs[:4])
    result['catalog_present']=[(d/'.storage-catalog-v1.json').is_file() for d in dirs[:4]]
    require(all(result['catalog_present']),'worker failed to persist all selected catalogs')
    save(out/'preparation.json',result)
    return result

def physical(dirs):
    out=[]
    for d in dirs:
        files=[d/'session.json',d/'journal.jsonl',d/'.storage-catalog-v1.json',d/HEAD]+sorted(d.glob('blobs/**/*'))
        m=hashlib.sha256()
        for f in files:
            stat=f.stat()
            m.update(json.dumps([str(f.relative_to(d)),stat.st_dev,stat.st_ino,stat.st_ctime_ns,stat.st_size]).encode())
        out.append({'n':len(files),'stat_sha256':m.hexdigest()})
    return out
