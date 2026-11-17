"""Compile the exact production phase() entry from two files, stubbing only elapsed()."""
import pathlib,subprocess,sys,tempfile
if len(sys.argv) != 3:
    raise SystemExit("usage: python3 ticker-check.py BASE_DESKTOP_TREE PATCHED_DESKTOP_TREE")
base, patched = map(pathlib.Path, sys.argv[1:])
fixture=pathlib.Path(__file__).with_name('ticker-fixture.rs').read_text()
for name in ['base','after','early-f32','no-wrap']:
    path=(base if name=='base' else patched) / 'src/ui/motion/ticker.rs'
    text=path.read_text()
    entry=text[text.index('pub(in crate::ui) fn phase('):text.index('/// Redraws the view')].strip()
    local_tests=text[text.index('#[cfg(test)]'):] if '#[cfg(test)]' in text else ''
    if name=='early-f32':
        entry=entry.replace('(elapsed.as_secs_f64() / period.as_secs_f64()).fract() as f32','(elapsed.as_secs_f32() / period.as_secs_f32()).fract()')
    if name=='no-wrap':
        entry=entry.replace('if fraction == 1. { 0. } else { fraction }','fraction')
    f=fixture.replace('/*TICKER*/',entry+'\n'+local_tests)
    with tempfile.TemporaryDirectory() as tmp:
        src=pathlib.Path(tmp,'probe.rs');src.write_text(f);out=pathlib.Path(tmp,'probe')
        subprocess.run(['rustc','--edition=2024','--test','-D','warnings',str(src),'-o',str(out)],check=True)
        r=subprocess.run([str(out),'--test-threads=1','--nocapture'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        print(name,r.returncode);print(r.stdout)
        assert (r.returncode==0)==(name=='after')
