from pathlib import Path
import argparse,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('desktop',type=Path);p.add_argument('--base-details',type=Path,required=True);p.add_argument('--rlib',type=Path,required=True);p.add_argument('--rustc',default='rustc');a=p.parse_args()
def body(s,n):
 i=s.index(n);b=s.index('{',i);j=b+1;d=1
 while d:d+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[i:j]
d=(a.desktop/'src/tool_display/mod.rs').read_text();ui=(a.desktop/'src/ui/chat/tool_row.rs').read_text()
s=Path(__file__).with_name('candidate.rs.in').read_text().replace('/*FUNCS*/','\n'.join(body(d,x) for x in ['pub fn other_args(','fn subject_text(','fn limit(','fn arg_preview(','fn single_line('])).replace('/*DETAILS*/',body(ui,'fn argument_details(')).replace('/*HELPER*/',body(d,'pub fn path_list_preview(')).replace('for n in 0..=24','for n in 0usize..=24')
baseui=a.base_details.read_text()
s=s.replace('/*LEGACY*/',body(baseui,'fn argument_details(').replace('fn argument_details(','fn legacy_details(',1))
assert '"read_many_files" => "paths"' in d and 'let label = name.to_owned();' in d and 'SUBJECT_LIMIT: usize = 300;' in d and 'ARG_LIMIT: usize = 160;' in d and 'MAX_ARGS: usize = 6;' in d
with tempfile.TemporaryDirectory() as t:
 t=Path(t);src=t/'probe.rs';out=t/'probe';src.write_text(s);subprocess.run([a.rustc,'--edition=2024','-Copt-level=2','-Awarnings',src,'--extern','serde_json='+str(a.rlib),'-L','dependency='+str(a.rlib.parent),'-o',out],check=True);subprocess.run([out],check=True)
