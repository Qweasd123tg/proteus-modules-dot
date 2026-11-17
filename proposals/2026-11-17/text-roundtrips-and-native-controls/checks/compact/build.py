from pathlib import Path
import sys,subprocess
rustc,sdeps,serde,js=sys.argv[1:5]
r=Path('harness/probe.rs')
sig='#[cfg(test)]\nmod value_roundtrip_tests {'
final=Path('after/schema.rs').read_text()
reg=final[final.index(sig):]
for phase in ['before','after']:
    s=Path(phase+'/schema.rs').read_text();s=s[s.index('/// How a text control reads'):]
    if phase=='before':s+='\n'+reg
    Path('harness/current.rs').write_text(s)
    common=[rustc,'--edition','2024','-L','dependency='+sdeps,'--extern','serde='+serde,'--extern','serde_json='+js,str(r)]
    exe=phase+'/test'; subprocess.run(common+['--test','-o',exe],check=True)
    result=subprocess.run([exe],capture_output=True,text=True)
    Path('evidence/'+phase+'.log').write_text(result.stdout)
    assert result.returncode==(101 if phase=='before' else 0)
    subprocess.run(common+['-O','-o',phase+'/probe'],check=True)
