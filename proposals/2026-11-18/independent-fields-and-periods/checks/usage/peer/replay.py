from pathlib import Path
import argparse,tempfile,subprocess
p=argparse.ArgumentParser();p.add_argument('before',type=Path,help='baseline report.rs');p.add_argument('after',type=Path,help='patched report.rs');p.add_argument('value',type=Path,help='ValueExt source');p.add_argument('model',type=Path,help='source containing model_key');p.add_argument('--cargo',default='cargo');args=p.parse_args()
def func(p,name):
 s=p.read_text();a=s.index('pub fn '+name);b=s.index('\n}',a)+2;return s[a:b]
frame=Path(__file__).with_name('frame.rs.in').read_text()
for k,src in [('VALUE',args.value.read_text()),('MODEL',func(args.model,'model_key')),('BEFORE',func(args.before,"scoped")),('AFTER',func(args.after,"scoped"))]:frame=frame.replace('@'+k+'@',src)
with tempfile.TemporaryDirectory() as t:
 d=Path(t);(d/'src').mkdir();(d/'src'/'main.rs').write_text(frame);(d/'Cargo.toml').write_text('[package]\nname="turn_projection_check"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nserde_json="=1.0.151"\n')
 r=subprocess.run([args.cargo,'run','--offline','--quiet','--manifest-path',str(d/'Cargo.toml')]);raise SystemExit(r.returncode)
