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
a=argparse.ArgumentParser();a.add_argument('--desktop',required=True,type=Path);a.add_argument('--rustc',default='rustc');a.add_argument('--serde-json',required=True,type=Path);a.add_argument('--patch',type=Path,default=ROOT.parent/'tag-literal-value.patch');o=a.parse_args();patch=o.patch.resolve();lib=o.serde_json.resolve(strict=True)
def source(p):return subprocess.check_output(['git','-C',o.desktop,'show',REV+':'+p]).decode()
fields=source('src/ui/settings/fields.rs');e=source('src/ui/settings/tags/editor.rs');ed=source('src/ui/settings/editors.rs')
assert 'let control = if tagged {\n            self.string_tags(&spec, cx)' in fields
assert 'let label = tag_label(&spec.values[index]);' in e and 'faded(label.clone())' in e
assert 'added_value(&add.field, &input.read(cx).value())' in e and 'Edit::Add(Value::String(value.clone()))' in e
assert 'this.add_string_tag(&key, &field, window, cx)' in ed
p='src/ui/settings/tags.rs';s=source(p);assert 'let Some(value) = added_value(field, &text)' in s
assert hashlib.sha256(patch.read_bytes()).hexdigest()=='5a3d0b62317df32a8255e64669cd17bb5f906604612529a4bee525763dcdd85b'
with tempfile.TemporaryDirectory() as td:
 t=Path(td);f=t/p;f.parent.mkdir(parents=True);f.write_text(s)
 for phase,digest in [('before','3e1fab04d2771d9129ba2df139682bfdeda3b401'),('after','7f83047796aee07783fe66c1e38fd16c867e2acd')]:
  if phase=='after':
   subprocess.run(['git','apply',str(patch)],cwd=t,check=True)
   subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=t,check=True)
  assert blob(f.read_bytes())==digest;s=f.read_text()
  src=t/(phase+'.rs');src.write_text((ROOT/'fixture.rs.in').read_text().replace('//SOURCE',''.join(fn(s,n) for n in ['is_tag_field','tag_label','edited','added_value'])))
  exe=t/phase;subprocess.run([o.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(lib.parent),'--extern','serde_json='+str(lib),src,'-o',exe],check=True)
  r=subprocess.run([exe],capture_output=True,text=True);print(phase+':\n'+r.stdout.strip());assert r.returncode==(1 if phase=='before' else 0),r.stderr
