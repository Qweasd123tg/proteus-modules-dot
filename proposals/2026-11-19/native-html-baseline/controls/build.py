"""Build uninstrumented arms in separate source/target directories. Use pinned Desktop and the host lock."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess
P=argparse.ArgumentParser(description=__doc__)
for s in ('desktop','patch','lock','out'):P.add_argument(s,type=Path)
P.add_argument('--offline',action='store_true')
args=P.parse_args()
expected='a5bd0504829a4f3716c81928ca54a8fa1d48a26145c17807434926bbe9f1d6e6'
assert hashlib.sha256(args.patch.read_bytes()).hexdigest()==expected
for arm in ('baseline','candidate'):
    out=(args.out/arm).resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'src').mkdir();shutil.copy(Path(__file__).with_name('control.rs'),out/'src/main.rs')
    d=args.desktop.resolve()/'vendor';base=out/'gpui-base';shutil.copytree(d/'gpui-base',base)
    src=base/'src/text/state.rs';b=src.read_bytes()
    assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()=='a590e391d4ffa62076ee66e91e5cf6bcda530817'
    if arm=='candidate':
        # Library and the real Desktop call site are separate pinned trees in this driver.
        libdiff=''.join(x for x in ('diff --git '+seg for seg in args.patch.read_text().split('diff --git ')[1:]) if x.startswith('diff --git a/vendor/gpui-base/'))
        subprocess.run(['patch','--batch','--silent','-p3'],input=libdiff.encode(),cwd=base,check=True)
    name='state-qual' if arm=='baseline' else 'state-qual-candidate'
    (out/'Cargo.lock').write_text(args.lock.read_text().replace('name = "state-qual"',f'name = "{name}"'))
    (out/'Cargo.toml').write_text(f'''[package]
name="{name}"
version="0.1.0"
edition="2024"
[dependencies]
gpui-base={{path="gpui-base",features=["gpui-fast","test-support"]}}
gpui={{package="gpui-fast",version="=0.1.12",default-features=false,features=["test-support"]}}
serde_json="1"
[patch.crates-io]
gpui-fast={{path={json.dumps(str(d/'gpui-fast'))}}}
gpui-fast-wgpu={{path={json.dumps(str(d/'gpui-fast-wgpu'))}}}
''')
    target=Path(os.environ.get('CONTROL_TARGET_'+arm.upper(),out/'target')).resolve()
    env=dict(os.environ,CARGO_TARGET_DIR=str(target))
    # A warmed, explicitly supplied target must be dedicated to this experiment.
    # Force exactly the product crate to rebuild from this arm's real source.
    if target.exists():
        subprocess.run(['cargo','clean','--release','--offline','-p','gpui-base'],cwd=out,env=env,check=True)
    cmd=['cargo','build','--release','--locked']
    if args.offline:cmd.append('--offline')
    result=subprocess.run(cmd,cwd=out,env=env,stderr=subprocess.PIPE,text=True)
    print(result.stderr,flush=True);result.check_returncode()
    assert 'Compiling gpui-base v0.8.1 ('+str(base)+')' in result.stderr, 'Wrong or cached product crate'
    shutil.copy(target/'release'/name,args.out/(arm+'-probe'))
    if arm=='candidate':
        driver=out/'src/main.rs'
        old=driver.read_text()
        assert old.count('TextViewState::html(')==2
        driver.write_text(old.replace('TextViewState::html(','TextViewState::html_for_replacements('))
        subprocess.run(cmd,cwd=out,env=env,check=True)
        shutil.copy(target/'release'/name,args.out/'opted-probe')
