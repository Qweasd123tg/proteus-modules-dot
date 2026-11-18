#!/usr/bin/env python3
"""Test only presentation functions from a pinned local Desktop checkout. No GUI, user profile or network."""
import argparse,subprocess,hashlib,re,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REV='2307e9c67125bbe66f15ced51317a2dfcc437aa4'
def fn(s,n):
 m=re.search(r'(?m)^ *(?:pub(?:\([^)]*\))? )?fn '+n+r'\s*\(',s);op=s.index('{',m.end());d=1
 for i in range(op+1,len(s)):
  d+=(s[i]=='{')-(s[i]=='}')
  if d==0:return s[m.start():i+1]+'\n'
 raise Exception(n)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
a=argparse.ArgumentParser();a.add_argument('--desktop',required=True,type=Path);a.add_argument('--rustc',default='rustc');a.add_argument('--serde-json',required=True,type=Path);a.add_argument('--patch',type=Path,default=ROOT.parent/'number-exact-whole.patch');o=a.parse_args();patch=o.patch.resolve();lib=o.serde_json.resolve(strict=True)
def source(p):return subprocess.check_output(['git','-C',o.desktop,'show',REV+':'+p]).decode()
p='src/settings/schema.rs'; s=source(p)
ed=source('src/ui/settings/editors.rs')
assert 'ConfigValueSchema::Number {} => FieldKind::Text(TextFormat::Number)' in s
assert '.map(|value| format_value(format, value))' in ed
assert 'this.text_changed(&key, format, default.as_ref(), &text, cx);' in ed and 'Ok(value) => self.edit_field(path, value, default, cx)' in ed
assert hashlib.sha256(patch.read_bytes()).hexdigest()=='b80090117096e1bdc8870ec7b98d1fde67df8cd7b231d82c7e3f2e5e5eeafa50'
with tempfile.TemporaryDirectory() as td:
 t=Path(td);f=t/p;f.parent.mkdir(parents=True);f.write_text(s)
 for phase,digest in [('before','1a799115bf45e9854defbc3b0c4f4cc6645e4a2c'),('after','9dd7b99bfd2627e8d19feff1374a5e76b790feb2')]:
  if phase=='after':
   subprocess.run(['git','apply',str(patch)],cwd=t,check=True)
   subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=t,check=True)
  assert blob(f.read_bytes())==digest;s=f.read_text()
  src=t/(phase+'.rs');src.write_text((ROOT/'fixture.rs.in').read_text().replace('//SOURCE',s[s.index('#[derive(Clone, Copy, Debug, PartialEq, Eq)]'):s.index('impl TextFormat')]+fn(s,'format_value')+fn(s,'parse_text')))
  exe=t/phase;subprocess.run([o.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(lib.parent),'--extern','serde_json='+str(lib),src,'-o',exe],check=True)
  r=subprocess.run([exe],capture_output=True,text=True);print(phase+':\n'+r.stdout.strip());assert r.returncode==(1 if phase=='before' else 0),r.stderr
