"""Runs reviewed, isolated Rust menu builder; directory existence is a synthetic predicate."""
import argparse,hashlib
from pathlib import Path
import subprocess,tempfile
CLI=argparse.ArgumentParser(description=__doc__)
CLI.add_argument('baseline',type=Path);CLI.add_argument('candidate',type=Path);CLI.add_argument('--rustc',default='rustc')
args=CLI.parse_args();here=Path(__file__).resolve().parent
for label,tree in [('before',args.baseline),('after',args.candidate)]:
    src=(tree/'src/ui/chrome/projects.rs').read_bytes()
    blob=hashlib.sha1(b'blob '+str(len(src)).encode()+b'\x00'+src).hexdigest()
    if blob not in {'before':{'4a1b598956ca73e412896e660ac352e2e976eac9'},'after':{'88577e2624b6d382b2f0474085203fa695525e13'}}[label]:
        raise SystemExit(f'Unexpected {label} blob: {blob}')
    text=src.decode()
    original='.disabled(!path.is_dir())'
    assert text.count(original)==1
    with tempfile.TemporaryDirectory() as tmp:
        dst=Path(tmp)
        # include! expands within the source's intended namespace; convert only
        # module documentation and the one filesystem predicate into the model.
        isolated=text.replace('//!','//').replace(original,'.disabled(!cx.available(&path))')
        (dst/'reviewed_source.rs').write_text(isolated)
        (dst/'main.rs').write_bytes((here/'menu_probe.rs.in').read_bytes())
        for test in ([False,True] if label=='after' else [False]):
            cmd=[args.rustc,'--edition','2024','main.rs','-o','probe']
            if label=='after':cmd+=['--cfg','candidate']
            if test:cmd+=['--test']
            subprocess.run(cmd,cwd=dst,check=True)
            print(label,'unit' if test else 'matrix',flush=True)
            subprocess.run([str(dst/'probe')],cwd=dst,check=True)
