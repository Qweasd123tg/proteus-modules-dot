"""Run an isolated pinned GPUI TestPlatform draw A/B. No native display is required."""
import argparse,hashlib,os,re,shutil,subprocess,tempfile
from pathlib import Path
P='210cc9f274ffe40533b390a0d9e940f251a9fa22'
FILES=('vendor/gpui-base/src/text/state.rs','vendor/gpui-base/src/text/markdown_ext.rs')
EXPECTED=('a590e391d4ffa62076ee66e91e5cf6bcda530817','f04215c855dfb2a48cb0c9df2908a3ff4e3ff8be')
here=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('desktop',type=Path);p.add_argument('patch',type=Path);p.add_argument('lock',type=Path)
p.add_argument('--offline',action='store_true');p.add_argument('--target',type=Path,help='an isolated reusable debug target')
a=p.parse_args();d=a.desktop.resolve()
for name,sha in zip(FILES,EXPECTED):
    content=(d/name).read_bytes()
    assert hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()==sha
with tempfile.TemporaryDirectory() as temp:
    arm=Path(temp);target=a.target.resolve() if a.target else arm/'target';(arm/'src').mkdir()
    shutil.copytree(d/'vendor/gpui-base',arm/'gpui-base')
    shutil.copy(a.lock,arm/'Cargo.lock');shutil.copy(here/'observe.rs',arm/'src/main.rs')
    (arm/'Cargo.toml').write_text(f'''[package]
name="state-qual"
version="0.1.0"
edition="2024"
[dependencies]
gpui-base={{path="gpui-base",features=["gpui-fast","test-support"]}}
gpui={{package="gpui-fast",version="=0.1.12",default-features=false,features=["test-support"]}}
serde_json="1"
[patch.crates-io]
gpui-fast={{path="{d}/vendor/gpui-fast"}}
gpui-fast-wgpu={{path="{d}/vendor/gpui-fast-wgpu"}}
''')
    src=arm/'gpui-base/src/text/state.rs'
    answers=[]
    for mode in ('before','after'):
        if mode=='after':
            shutil.copyfile(d/FILES[0],src)
            diff=''.join(x for x in ('diff --git '+seg for seg in a.patch.read_text().split('diff --git ')[1:]) if x.startswith('diff --git a/vendor/gpui-base/'))
            subprocess.run(['patch','--batch','--silent','-p3'],input=diff.encode(),cwd=arm/'gpui-base',check=True)
            driver=arm/'src/main.rs'
            original=driver.read_text()
            assert original.count('TextViewState::html(')==1
            driver.write_text(original.replace('TextViewState::html(','TextViewState::html_for_replacements('))

        # Put a recognisable trace inside the respective worker branch to
        # reject accidental Cargo reuse of another same-name local dependency.
        s=src.read_text()
        if mode=='before':
            needle='let res = parse_content(self.format, self.content.clone(), &options);'
            insert='if options.mode == ParseMode::BaselineAck { eprintln!("LAYOUT-WORK baseline"); }\n'
        else:
            needle='self.content = WorkerBaseline::DeferredHtml(options);'
            insert='eprintln!("LAYOUT-WORK candidate");\n'
        assert s.count(needle)==1
        src.write_text(s.replace(needle,insert+needle))
        cmd=['cargo','build','--locked']
        if a.offline:cmd.append('--offline')
        subprocess.run(cmd,cwd=arm,env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_PROFILE_DEV_DEBUG='0'),check=True)
        proc=subprocess.run([target/'debug/state-qual'],capture_output=True,check=True)
        marker=b'LAYOUT-WORK '+(b'baseline' if mode=='before' else b'candidate')
        assert proc.stderr.count(marker)>0, f'wrong arm: {mode}'
        answers.append(proc.stdout)
    assert answers[0]==answers[1]
    print(answers[0].decode(),end='')
