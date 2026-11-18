from pathlib import Path
import argparse, re, subprocess, tempfile
a=argparse.ArgumentParser();a.add_argument('base',type=Path);a.add_argument('candidate',type=Path);a.add_argument('serde',type=Path);a.add_argument('rustc');o=a.parse_args()
def method(text,name):
 m=re.search(r'(?m)^ *(?:pub(?:\([^)]*\))? )?fn '+name+r'\s*\(',text);at=text.index('{',m.end());d=1
 for j in range(at+1,len(text)):
  d+=int(text[j]=='{')-int(text[j]=='}')
  if not d:return text[m.start():j+1]
 raise ValueError(name)
here=Path(__file__).parent; lib=o.serde.resolve()
with tempfile.TemporaryDirectory() as path:
 d=Path(path)
 def run(code,name):
  f=d/(name+'.rs');f.write_text(code);subprocess.run([o.rustc,'--edition=2024','-Awarnings',f,'--extern','serde_json='+str(lib),'-L','dependency='+str(lib.parent),'-o',d/name],check=True);assert subprocess.run([d/name]).returncode==int(name=='old')
 def extract(t,p,ns):
  s=(t/p).read_text();return '\n'.join(method(s,n) for n in ns)
 t=(here/'tag/peer.rs.in').read_text()
 for n,v in [('old',o.base),('new',o.candidate)]:run(t.replace('SOURCE',extract(v,'src/ui/settings/tags.rs',['tag_label','added_value'])),n)
 f='src/settings/schema.rs'; ns=['format_value','parse_text']
 run((here/'number/peer.rs.in').read_text().replace('BEFORE',extract(o.base,f,ns)).replace('AFTER',extract(o.candidate,f,ns)),'number')
