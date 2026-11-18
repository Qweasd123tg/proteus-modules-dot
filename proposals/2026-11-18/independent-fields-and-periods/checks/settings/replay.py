#!/usr/bin/env python3
"""Compile exact section grouping and row rendering, substituting a text recorder for GPUI."""
import argparse,subprocess,hashlib,re,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
REV="2307e9c67125bbe66f15ced51317a2dfcc437aa4"
def fn(s,n):
 m=re.search(r'(?m)^ *(?:pub(?:\([^)]*\))? )?fn '+n+r'\s*\(',s);op=s.index('{',m.end());d=1
 for i in range(op+1,len(s)):
  d+=(s[i]=='{')-(s[i]=='}')
  if d==0:return s[m.start():i+1]+'\n'
 raise Exception(n)
a=argparse.ArgumentParser();a.add_argument('--desktop',required=True,type=Path);a.add_argument('--rustc',default='rustc');a.add_argument('--serde-json',required=True,type=Path);a.add_argument('--patch',type=Path,default=HERE.parent/'advanced-section-header.patch');o=a.parse_args();patch=o.patch.resolve();lib=o.serde_json.resolve(strict=True)
def source(p):return subprocess.check_output(['git','-C',o.desktop,'show',REV+':'+p]).decode()
assert hashlib.sha256(patch.read_bytes()).hexdigest()=='8e12a36315affd690f11b16bd3d64e936cf01ea828a49d57ec58a4bc00902833'
g='src/ui/settings/group.rs';src=source(g);schema=source('src/settings/schema.rs');cat=source('src/settings/catalog.rs')
assert 'let rows = self.field_rows(' in source('src/ui/settings/params.rs') and 'let rows = self.field_rows(fields, |key| path.child(key), value, &scope, cx);' in src
sec=schema[schema.index('pub struct FieldSection'):schema.index('/// How a text control')].replace('proteus_contracts::domain::ConfigSection','ConfigSection')
with tempfile.TemporaryDirectory() as tmp:
 t=Path(tmp);f=t/g;f.parent.mkdir(parents=True);f.write_text(src)
 for phase in ['before','after']:
  if phase=='after':subprocess.run(['git','apply',patch],cwd=t,check=True);subprocess.run(['git','apply','--reverse','--check',patch],cwd=t,check=True)
  s=f.read_text();body=(HERE/'frame.rs.in').read_text().replace('//ADDS_CONTEXT',fn(s,'adds_context') if phase=='after' else '').replace('//SECTIONS',sec).replace('//EDITABLE',fn(cat,'editable_field')+fn(cat,'editable_fields')).replace('//METHODS',fn(s,'field_rows').replace('pub(super) fn','fn')+fn(s,'section_rows'));p=t/(phase+'.rs');p.write_text(body)
  exe=t/phase;subprocess.run([o.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(lib.parent),'--extern','serde_json='+str(lib),p,'-o',exe],check=True)
  r=subprocess.run([exe],capture_output=True,text=True);print(phase+':\n'+r.stdout.strip());assert r.returncode==(1 if phase=='before' else 0),r.stderr
