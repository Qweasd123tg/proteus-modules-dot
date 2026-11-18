"""Independent source-slice test, no project dependencies. Usage: python3 replay.py BEFORE/..../reorder.rs candidate.patch [rustc]."""
from pathlib import Path
import hashlib, tempfile, subprocess, sys
src, patch = Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve()
assert hashlib.sha256(patch.read_bytes()).hexdigest()=='ed51bc679d73e0da6715a0e1b66a99fe8326436aee8bac656b203e743e9c1848'
def blob(data): return hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
assert blob(src.read_bytes())=='7193ede57c29ca7e9ecd2e2795476e3c8fda18f0'
def body(s,a,b): return s[s.index(a):s.index(b,s.index(a))]
template=Path(__file__).with_name('gate.rs.in').read_text()
logs=[]
with tempfile.TemporaryDirectory() as tmp:
    d=Path(tmp); f=d/'src/ui/reorder.rs';f.parent.mkdir(parents=True);f.write_bytes(src.read_bytes())
    subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(patch)],cwd=d,check=True,stdout=subprocess.DEVNULL)
    for ver,ref in [('before',src),('after',f)]:
        s=ref.read_text()
        # Same Vec<Row> produces the ID sequence and exactly one child per row in the same order; no iterator filter/drop-until.
        assert 'let ids: Vec<_> = self.rows.iter().map(|row| row.id.clone()).collect();' in s
        child=body(s, 'let children = self\n            .rows', '        let hover = state.clone();')
        assert child.startswith('let children = self\n            .rows\n            .into_iter()\n            .enumerate()\n            .map(') and child.rstrip().endswith('})\n            .collect();')
        assert '.entry(row.id.clone())' in child and '.or_insert_with(|| cx.focus_handle().tab_stop(true))' in child
        assert '.child(Arrange {\n                ids,\n                children,' in s
        assert 'type RequestLayoutState = Vec<LayoutId>;' in s and '(window.request_layout(style, children.clone(), cx), children)' in s
        lay=body(s,'let children: Vec<_> = self\n            .children','        let mut style')
        raw=body(s,'let raw: Vec<_> = self\n            .ids','        let now')
        segment=body(s,'state.exclusions.clear();','            let order')
        segment=segment.replace('state.exclusions.clear();','')
        marker='state.focus.retain('
        assert segment.count(marker)==1
        # Instrument ONLY the original retained-map statement. Hash and Eq on fixture IDs are counted, not timings.
        segment=segment.replace(marker,'start_count(); '+marker)
        pos=segment.index(';',segment.index(marker))+1
        segment=segment[:pos]+' let count=end_count();'+segment[pos:]
        r=template.replace('@@layout@@',lay).replace('@@raw@@',raw).replace('@@keep@@',segment)
        (d/'gate.rs').write_text(r)
        subprocess.run([sys.argv[3] if len(sys.argv)>3 else 'rustc','--edition=2024','-O',str(d/'gate.rs'),'-o',str(d/'gate')],check=True)
        print(ver,subprocess.check_output([str(d/'gate'),ver],text=True).strip(),flush=True)
