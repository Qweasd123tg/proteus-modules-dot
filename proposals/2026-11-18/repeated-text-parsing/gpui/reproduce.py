"""Native, no-window diagnostic. Caller supplies an unmodified pinned Desktop checkout."""
from pathlib import Path
import sys, tempfile, gzip, shutil, json, subprocess, os
src=Path(sys.argv[1]).resolve();here=Path(__file__).resolve().parent
offline=['--offline'] if '--offline' in sys.argv[2:] else []
with tempfile.TemporaryDirectory() as d:
    root=Path(d); corpus=root/'corpus.jsonl'; corpus.write_bytes(gzip.decompress((here/'corpus.jsonl.gz').read_bytes()))
    seen={}
    for row in corpus.read_text().splitlines():
        name,html=json.loads(row)
        if name!='independent-html': seen.setdefault(name,row)
    alloccases=root/'alloccases.jsonl';alloccases.write_text('\n'.join(seen.values())+'\n')
    for mode,config,action,arg in [('count','--cfg count_calls','parity',corpus),('normal','','times',corpus),('normal','--cfg alloc_probe','alloc',alloccases)]:
        wd=root/action;wd.mkdir()
        for f in ['Cargo.toml','Cargo.lock']:shutil.copyfile(here/f,wd/f)
        subprocess.run([sys.executable,here/'prepare.py',src,wd,mode],check=True)
        env=dict(os.environ,RUSTFLAGS=(config+' --check-cfg=cfg(count_calls) --check-cfg=cfg(alloc_probe)').strip(),CARGO_TARGET_DIR=str(wd/'target'))
        subprocess.run(['cargo','build','--release','--locked',*offline],cwd=wd,env=env,check=True)
        exe=wd/'target/release/html-dom-probe';subprocess.run([exe,action,arg],check=True)
        if action=='times' and sys.platform.startswith('linux'):
            hwm={}
            for name,row in seen.items():
                if len(json.loads(row)[1].encode())<4096:continue
                one=root/'single.jsonl';one.write_text(row+'\n');rows=[[],[]]
                for i in range(5):
                    for j in ((0,1) if i%2==0 else (1,0)):
                        rows[j].append(int(subprocess.check_output([exe,'once',one,str(j)],text=True).split()[1]))
                hwm[name]=rows
            print('VmHWM KiB:',json.dumps(hwm),flush=True)
