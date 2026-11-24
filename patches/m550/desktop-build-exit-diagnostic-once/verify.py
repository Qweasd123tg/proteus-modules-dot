#!/usr/bin/env python3
"""Verify exact M414 source and optionally rerun the actual Linux child fixture."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,signal,subprocess,sys,tempfile,time,tomllib
sys.dont_write_bytecode=True
from lift import lift
P=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def outcome(log):
    assert 'test result: ok. 4 passed; 0 failed;' in log,log
    assert 'startup_still_rejects_a_non_origin_ready_record ... ok' in log,log
    assert 'local_origin_parser_rejects_non_origin_and_remote_urls ... ok' in log,log
    m=re.findall(r'M411_DIAG (\S+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)',log)
    assert len(m)==3 and {x[0] for x in m}=={'empty','tiny','large'}
    keys=('requests','gross_bytes','net_bytes','peak_bytes','largest_request','report_bytes','report_digest')
    tests=re.findall(r'M411_STARTUP (\d+) (\d+)',log)
    assert len(tests)==1
    return {'tests':4,'pre_ready_failure':list(map(int,tests[0])),
      'reports':{k:dict(zip(keys,map(int,vals),strict=True))for k,*vals in m}}
def same(s,c):
    assert s['pre_ready_failure']==c['pre_ready_failure']
    assert s['reports']['empty']==c['reports']['empty']
    for label in ('tiny','large'):
        a=s['reports'][label];b=c['reports'][label]
        for prop in ('net_bytes','report_bytes','report_digest'):
            assert a[prop]==b[prop],(label,prop)
        for prop in ('requests','gross_bytes','peak_bytes'):
            assert a[prop]>b[prop],(label,prop)
def verify(root):
    r=read(P/'receipt.json');c=read(P/'composition.json')
    for line in (P/'SHA256SUMS').read_text().splitlines():
        h,n=line.split(None,1);assert sha((P/n).read_bytes())==h,n
    assert c['desktop_byte_identical_to_m411'] and c['both_orders_and_reverse_exact']
    assert c['reader_and_backend_drop_bytes_unchanged']
    lock=(P/'Cargo.lock').read_bytes();assert sha(lock)==c['native_lock_sha256']
    z=base64.b64decode((P/'source-00.gz.b64').read_bytes().strip(),validate=True)
    assert sha(z)==c['source_capsule_sha256']
    packed={n:v.encode()for n,v in json.loads(gzip.decompress(z)).items()}
    assert {n:oid(v)for n,v in packed.items()}=={n:h for n,h in c['baseline_blobs'].items()if n!='Cargo.lock'}
    d=root/'source'
    for n,b in packed.items():
        f=d/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
    patch=(P/'source.patch').read_bytes();assert sha(patch)==c['patch_sha256']
    apply=lambda *args:subprocess.run(['git','apply','--whitespace=error',*args,'-'],cwd=d,input=patch,check=True)
    apply('--check');apply()
    n='src/backend.rs';after=(d/n).read_bytes()
    assert oid(after)==c['candidate_blobs'][n]
    apply('-R');assert all((d/n).read_bytes()==v for n,v in packed.items())
    assert packed[n].split(b'impl Drop for Backend {',1)[1]==after.split(b'impl Drop for Backend {',1)[1]
    for mode in ('default','preserve_order'):
        same(r['runs']['stock'][mode],r['runs']['candidate'][mode])
    f=r['disk_guard']['floors_bytes']
    assert f=={'workspace':100*1024*1024,'tmp':200*1024*1024}
    for run in r['disk_guard']['runs']:
        assert run['exit']==0
        assert all(run[field][which]>=limit for field in ('before','min','last')for which,limit in f.items())
    for arm,body in (('stock',packed[n]),('candidate',after)):
        lift(body,packed['crates/client-common/src/lib.rs'].decode(),root/arm,P)
    print('Source, apply/reverse, recorded guards and A/B digests pass.',flush=True)
    return r,c
def build(root,vendor,target,r,c):
    if sys.platform!='linux':
        raise SystemExit('Native child fixture requires Linux.')
    lock=tomllib.loads((P/'Cargo.lock').read_text())['package']
    for spec in lock:
        if 'checksum' not in spec:continue
        package=spec['name']+'-'+spec['version']
        meta=read(vendor/package/'.cargo-checksum.json')
        assert meta['package']==spec['checksum']==c['native_registry_pins'][package],package
        for name,h in meta['files'].items():assert sha((vendor/package/name).read_bytes())==h,(package,name)
    assert subprocess.check_output(['rustc','--version'],text=True).strip()==r['rustc']
    target=target.resolve()
    cargo=['cargo','--offline','--config','source.crates-io.replace-with="verified"',
           '--config',f'source.verified.directory="{vendor}"']
    limits=r['disk_guard']['floors_bytes']
    def floor_ok():
        stats={k:os.statvfs(path)for k,path in [('workspace',Path.cwd()),('tmp','/tmp')]}
        if not all(stats[k].f_bavail*stats[k].f_frsize>=v for k,v in limits.items()):
            return False
        parent=target
        while not parent.exists():parent=parent.parent
        volume=os.statvfs(parent)
        return volume.f_bavail*volume.f_frsize>=limits['workspace']
    for mode in ('default','preserve_order'):
        for arm in ('stock','candidate'):
            if not floor_ok():raise SystemExit('Stopped before launch: disk reserve would be breached.')
            path=root/arm
            flags=['--features','preserve_order'] if mode=='preserve_order' else []
            env={**os.environ,'CARGO_HOME':str(root/'cargo-home'),'CARGO_TARGET_DIR':str(target),
                 'CARGO_INCREMENTAL':'0','PROTEUS_BIN':str(path/'synthetic-backend.py')}
            tmp=root/f'{arm}-{mode}.log'
            with tmp.open('w')as log:
                args=['test','--locked','--release','--lib','-j2',*flags,'--','--test-threads=1','--nocapture']
                p=subprocess.Popen(cargo+args,cwd=path,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                while p.poll() is None:
                    if not floor_ok():
                        try:os.killpg(p.pid,signal.SIGTERM)
                        except ProcessLookupError:pass
                        try:p.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(p.pid,signal.SIGKILL);p.wait()
                        raise SystemExit('Stopped the owned build: disk reserve would be breached.')
                    time.sleep(.2)
            if p.returncode:print(tmp.read_text())
            p.check_returncode()
            if not floor_ok():raise SystemExit('Disk reserve breached after the run.')
            a=outcome(tmp.read_text())
            assert a==r['runs'][arm][mode],(arm,mode,a)
            print(arm,mode,a['tests'],a['reports']['large'],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--vendor',type=Path,help='supply to also rerun the native subprocess fixture')
    p.add_argument('--target-dir',type=Path)
    args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='m414-diagnostic-')as tmp:
        root=Path(tmp);r,c=verify(root)
        if args.vendor is not None:build(root,args.vendor.resolve(),args.target_dir or root/'target',r,c)
