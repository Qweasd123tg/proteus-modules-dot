"""Independent native transition model. Reads ONLY the prepared settings editor & mode control files."""
import argparse,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('desktop',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args()
ed=(a.desktop/'src/ui/settings/editors.rs').read_text();pm=(a.desktop/'src/ui/settings/params.rs').read_text()
def body(src,n,indent):
 i=src.index('fn '+n+'(');return src[i:src.index('\n'+' '*indent+'}',i)+2+indent]
for bit in ['if !json && self.editors.form_error(&slot, &module)', '"JSON…"','Отбросить ввод с ошибками и открыть JSON','move |(), cx|','ParameterMode::DiscardInvalidFormAndOpenJson','this.switch_mode(&slot, &module, target, cx)', '.disabled(json && self.json_error(&slot, &module))']:assert bit in pm
s=Path(__file__).with_name('model.rs.in').read_text();parts={'FORM':body(ed,'form_error',4),'FORGET':body(ed,'forget_form',4),'SWITCH':body(ed,'switch_mode',4),'JSON':body(ed,'json_error',4),'KEY':body(ed,'module_key',0)}
for k,b in parts.items():s=s.replace('/*'+k+'*/',b)
with tempfile.TemporaryDirectory() as temp:
 file=Path(temp)/'main.rs';bin=file.with_suffix('');file.write_text(s);subprocess.run([a.rustc,'--edition=2024',file,'-o',bin],check=True);subprocess.run([bin],check=True)
