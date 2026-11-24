#!/usr/bin/env python3
"""Reproduce this private, offline staged renderer comparison using an exact Core checkout."""
import argparse, hashlib, json, os, shutil, subprocess, tarfile, tempfile, tomllib
from pathlib import Path
from lift import generate

HERE=Path(__file__).resolve().parent

def need(ok,where):
    if not ok:raise RuntimeError(where)

def sha(b):return hashlib.sha256(b).hexdigest()

def identify(path):
    b=path.read_bytes()
    return {"bytes":len(b),"sha256":sha(b),"git_blob":hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()}

def deps(meta,repo_lock,dirs,vendor):
    registry={(p['name'],p['version']):p['checksum'] for p in tomllib.loads(repo_lock)['package'] if 'checksum' in p}
    # Construct a proof-only directory source directly from official archives. Check every
    # extracted regular file by computing its manifest; never trust a pre-built vendor.
    vendor.mkdir()
    for pkg in tomllib.loads(meta['proof_lock'])['package']:
        if 'checksum' not in pkg:continue
        k=pkg['name'],pkg['version'];name='-'.join(k); archive=next((p/(name+'.crate') for p in dirs if (p/(name+'.crate')).is_file()),None)
        need(archive and registry.get(k)==pkg['checksum']==sha(archive.read_bytes()),f'official Core lock checksum: {name}')
        hashes={};root=vendor/name;root.mkdir()
        with tarfile.open(archive,'r:gz') as tar:
            for member in tar:
                rel=Path(member.name)
                need(not rel.is_absolute() and rel.parts[0]==name and '..' not in rel.parts,'archive path')
                if member.isdir():continue
                need(member.isfile() and len(rel.parts)>1,'archive file')
                x=Path(*rel.parts[1:]);need(x.as_posix() not in hashes and x.as_posix()!='.cargo-checksum.json','duplicate/reserved filename')
                data=tar.extractfile(member).read();dest=root/x;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);hashes[x.as_posix()]=sha(data)
        (root/'.cargo-checksum.json').write_text(json.dumps({'package':pkg['checksum'],'files':hashes},sort_keys=True))

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--source',type=Path,required=True);a.add_argument('--work',type=Path,required=True);a.add_argument('--toolchain-bin',type=Path,required=True);a.add_argument('--archives',type=Path,action='append',required=True);a.add_argument('--timing',action='store_true');a.add_argument('--cpu',type=int);x=a.parse_args()
    meta=json.loads((HERE/'SOURCE-PROVENANCE.json').read_text());orig=x.source.resolve(strict=True);x.work.mkdir(parents=True,exist_ok=True)
    for file,identity in meta['inputs'].items():need(identify(orig/file)==identity,'source blob '+file)
    for f in ('source.patch','lift.py','exercise.rs'):need(identify(HERE/f)==meta['verification_files'][f],'packet integrity '+f)
    b=x.toolchain_bin.resolve(strict=True)
    for binary,digest in meta['toolchain'].items():need(sha((b/binary).read_bytes())==digest,'toolchain '+binary)
    git=Path('/usr/bin/git');cfg=['--config','source.crates-io.replace-with="official-proof"']
    with tempfile.TemporaryDirectory(prefix='replay-',dir=x.work.resolve()) as tmp:
        root=Path(tmp);ch=root/'candidate';ch.mkdir()
        env={'PATH':str(b)+':/usr/bin:/bin','HOME':tmp,'TMPDIR':tmp,'LC_ALL':'C','RUSTC':str(b/'rustc'),'CARGO_HOME':str(root/'cargo-home'),'CARGO_TARGET_DIR':str(root/'target'),'R260_TMP':str(root/'spools'),'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_CEILING_DIRECTORIES':str(root)}
        def run(cmd,cwd=root,capture=False):
            return subprocess.run(cmd,env=env,cwd=cwd,check=True,text=True,stdout=subprocess.PIPE if capture else None,timeout=300).stdout
        for file in meta['inputs']:
            dest=ch/file;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(orig/file,dest)
        patch=HERE/'source.patch'
        for operation in [[],['-R'],[]]:
            for flag in [['--check'],[]]:run([git,'apply','--whitespace=error-all',*operation,*flag,patch],ch)
            for file,identity in meta['postimages'].items():need(identify(ch/file)==(meta['inputs'][file] if operation else identity),'apply/rollback '+file)
        out=run([git,'apply','--numstat',patch],ch,True);need({line.split('\t',2)[2] for line in out.splitlines()}==set(meta['postimages']),'only expected paths')
        run([b/'rustfmt','--check','--edition','2024','--config','skip_children=true',*[ch/p for p in meta['postimages']]])
        deps(meta,(orig/'Cargo.lock').read_text(),x.archives,root/'vendor')
        crate=root/'crate';crate.mkdir();generate(orig,ch,crate/'src')
        (crate/'Cargo.toml').write_text(meta['proof_manifest']);(crate/'Cargo.lock').write_text(meta['proof_lock']);(root/'spools').mkdir()
        cfg+=['--config','source.official-proof.directory='+json.dumps(str(root/'vendor'))]
        for mode in ('debug','release'):
            run([b/'cargo','build','--locked','--offline',*cfg,*(['--release'] if mode=='release' else [])],crate)
            exe=root/'target'/mode/'r260-owned-stage-proof'
            out=run([exe],capture=True);print(mode+'\n'+out,flush=True)
            need(out.splitlines()==meta['verification']['checks'],'assertions/receipt: '+mode)
        if x.timing:
            if x.cpu is not None:os.sched_setaffinity(0,{x.cpu})
            out=run([exe,'--timing'],capture=True);print(out,flush=True)
            cohorts={}
            for row in out.splitlines():
                word,name,data=row.split(' ',2);need(word=='TIMING','timing output');cohorts[name]=json.loads(data)
            need(set(cohorts)=={'small','mixed','50k'},'timing cohorts')
            for name,items in cohorts.items():
                need({v['instrument'] for v in items}=={'whole_wall','whole_cpu','visit_cpu'},'timing channels')
                for v in items:
                    need(v['pairs']==25 and v['ratio_median']<=1.10 and v['ratio_p90']<=1.25 and max(v['stock_first_median'],v['candidate_first_median'])<=1.15,f"timing HOLD: {name}/{v['instrument']}")
        print('PASS: exact source pins, patch/apply/reverse, rustfmt, official archived dependencies and both offline typed staged lifts'+(', timing gates' if x.timing else ''))
if __name__=='__main__':main()
