"""Synthetic argument detail row collector; read only scoped pure bodies from prepared data."""
import argparse,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--rustc',default='rustc');p.add_argument('--rlib',type=Path,required=True);p.add_argument('--display',type=Path,required=True);p.add_argument('--details',type=Path,required=True);a=p.parse_args();here=Path(__file__).resolve().parent
def body(s,n):
 i=s.index(n);b=s.index('{',i);j=b+1;d=1
 while d:d+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[i:j]
display=a.display.read_text();ui=a.details.read_text()
s=(here/'review.rs.in').read_text().replace('/*FUNCS*/','\n'.join(body(display,k) for k in ['pub fn other_args(','fn subject_text(','fn limit(','fn arg_preview(','fn single_line('])).replace('/*DETAILS*/',body(ui,'fn argument_details('))
with tempfile.TemporaryDirectory() as td:
 t=Path(td);f=t/'ui.rs';f.write_text(s);e=t/'check';subprocess.run([a.rustc,'--edition=2024','-Awarnings',f,'--extern','serde_json='+str(a.rlib),'-L','dependency='+str(a.rlib.parent),'-o',e],check=True);subprocess.run([e],check=True)
