"""Run existing R9 compiled synthetic fixture and capture markers on same monotonic clock."""
import argparse,tempfile,sys,os,time,subprocess,json,shutil,hashlib
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('outdir',type=Path)
ap.add_argument('rows',type=int)
ap.add_argument('bench',type=Path);ap.add_argument('reference',type=Path);ap.add_argument('worker',type=Path);ap.add_argument('core',type=Path)
ap.add_argument('--cpu',default='5')
args=ap.parse_args()
out=args.outdir.resolve(); out.mkdir(exist_ok=False)
proxy=out/'proxy.py'; shutil.copy2(Path(__file__).with_name('proxy.py'),proxy); proxy.chmod(0o755)
(out/'worker').symlink_to(args.worker.resolve(strict=True))
markers=[]
with tempfile.TemporaryDirectory(prefix='r10-synthetic-') as temp,(out/'core.log').open('w') as log:
    env={**os.environ,'TMPDIR':temp,'PROTEUS_TEST_REFERENCE_MODULE':str(args.reference.resolve()),'PROTEUS_TEST_SESSION_STORAGE_MODULE':str(proxy),'R9_CASES':str(args.rows)}
    env['R9_FRESH_STORAGE'] = '1'
    cmd=['taskset','-c',args.cpu,str(args.bench.resolve()),'--exact','app_server::http::tests::session_reads::r9_real_turn_fixed_active_history','--nocapture','--test-threads=1']
    with subprocess.Popen(cmd,cwd=args.core.resolve(),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT) as p:
        for b in p.stdout:
            t=time.monotonic_ns(); line=b.decode().rstrip();log.write(line+'\n')
            if any(s in line for s in ('CASE display','SETTLE_','COMMIT_PROJECTION','TURN display','MODEL_REQUEST_RESPONSE','test result:')):
                markers.append([t,line]);print(line,flush=True)
        rc=p.wait()
    (out/'markers.json').write_text(json.dumps(markers,indent=2)+'\n')
    assert rc==0 and any('test result: ok. 1 passed;' in m[1] for m in markers), 'Unsuccessful benchmark'
