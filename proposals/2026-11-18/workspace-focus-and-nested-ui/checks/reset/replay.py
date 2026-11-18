#!/usr/bin/env python3
"""Compile the pinned reset path and outgoing module projection; all writes are in a tempdir."""
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
a=argparse.ArgumentParser();a.add_argument('--desktop',required=True,type=Path);a.add_argument('--rustc',default='rustc');a.add_argument('--serde-json',required=True,type=Path);a.add_argument('--patch',type=Path,default=ROOT.parent/'preserve-empty-parents.patch');o=a.parse_args();patch=o.patch.resolve();lib=o.serde_json.resolve(strict=True)
def source(p):return subprocess.check_output(['git','-C',o.desktop,'show',REV+':'+p]).decode()
uf=source('src/ui/settings/fields.rs');groups=source('src/ui/settings/group.rs');params=source('src/ui/settings/params.rs')
schema=source('src/settings/schema.rs');ed=source('src/ui/settings/editors.rs');tag=source('src/ui/settings/tags.rs')
assert 'ConfigValueSchema::Object { fields } if !fields.is_empty() => FieldKind::Group(fields)' in schema
assert 'ConfigValueSchema::String { .. } => FieldKind::Text(TextFormat::Line)' in schema
assert 'ConfigValueSchema::Array { items } => match items.as_ref()' in fn(tag,'is_tag_field') and '_ => false' in fn(tag,'is_tag_field')
assert 'this.text_changed(&key, format, default.as_ref(), &text, cx);' in ed
assert 'Ok(value) => self.edit_field(path, value, default, cx)' in ed and 'self.draft.edit_value(path, value, default, &self.baseline);' in uf
assert 'FieldKind::Group(fields) => return self.render_group(path, field, fields, cx)' in uf
assert 'let rows = self.field_rows(fields, |key| path.child(key), value, &scope, cx);' in groups
assert 'self.render_field(&path_of(&field.key), field, cx)' in groups and 'FieldPath::new(slot, module, key)' in params
assert 'let reset = spec.own().then' in uf and 'move |_, cx| handler.reset(cx)' in uf
assert 'this.reset_field(&path, cx)' in groups
assert 'kit::setting_reset(id, hint.to_owned(), reset, cx)' in source('src/ui/settings/widgets.rs')
assert 'reset(window, cx);' in source('src/ui/kit/setting_reset.rs')
assert hashlib.sha256(patch.read_bytes()).hexdigest()=='77bab28ab3f5b13ddf5029baf72ed16c6a559263b73f1c79c7d43876a7f3db12'
ds,es='src/settings/draft.rs','src/ui/settings/editors.rs'
with tempfile.TemporaryDirectory() as td:
 t=Path(td)
 for p in (ds,es):f=t/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(source(p))
 for phase in ['before','after']:
  if phase=='after':
   subprocess.run(['git','apply',str(patch)],cwd=t,check=True);subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=t,check=True)
  d=(t/ds).read_text();e=(t/es).read_text();struct=d[d.index('#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]'):d.index('/// Editable copy')]
  delta=d[d.index('        let empty = BTreeMap::new();',d.index('pub fn changes(')):d.index('        if self.hooks != baseline.hooks',d.index('pub fn changes('))]
  methods=''.join(fn(d,n) for n in ['value','set_value','edit_value','module_config']+(['reset_value'] if phase=='after' else []));util=''.join(fn(d,n) for n in ['is_empty_object','remove_nested','ensure_object'])
  body=(ROOT/'frame.rs.in').read_text().replace('//PATH',struct).replace('//DELTA',delta).replace('//METHODS',methods).replace('//UTIL',util).replace('//RESET_VIEW',fn(e,'reset_field')).replace('//FIELD_RESET',fn(uf,'reset')+fn(uf,'own'))
  src=t/(phase+'.rs');src.write_text(body)
  exe=t/phase;subprocess.run([o.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(lib.parent),'--extern','serde_json='+str(lib),src,'-o',exe],check=True)
  r=subprocess.run([exe],capture_output=True,text=True);print(phase+':\n'+r.stdout.strip());assert r.returncode==(1 if phase=='before' else 0),r.stderr
