from pathlib import Path
import argparse,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('candidate',type=Path);p.add_argument('--serde-json',type=Path,required=True);p.add_argument('--rustc',default='rustc');a=p.parse_args()
lib=a.serde_json.resolve();here=Path(__file__).parent.resolve()
for config,tree in [('before',a.base),('after',a.candidate)]:
    base=tree/'src/ui/extensions/declarative';fields=(base/'fields.rs').read_text()
    branch=fields[fields.index('            Node::Input {\n                id,\n                value,'):fields.index('            Node::Code {\n',fields.index('            Node::Input {\n                id,\n                value,'))]
    props=fields[fields.index('pub(super) struct TextInput {')+len('pub(super) struct TextInput {'):fields.index('\n}',fields.index('pub(super) struct TextInput {'))]
    render=(base/'render.rs').read_text();idx=render.index('                search: true,');segment=render[idx:render.index('            Node::Input {',idx)]
    assert 'Text::Area(_) => None' in segment and '.unwrap_or_else(|| div().into_any_element())' in segment
    widget=(tree/'src/declarative/widget.rs').read_text();assert 'if *lines != 1' in widget and 'if !(1..=40).contains(lines)' in widget
    with tempfile.TemporaryDirectory() as tmp:
        t=Path(tmp);(t/'spec.rs').write_text((here/'frame.rs.in').read_text().replace('/*INPUT_PROPS*/',props).replace('/*ARM*/',branch))
        subprocess.run([a.rustc,'--edition=2024','--cfg',config,str(t/'spec.rs'),'-o',t/'check','--extern','serde_json='+str(lib),'-L','dependency='+str(lib.parent)],check=True)
        print(config,flush=True);subprocess.run([t/'check'],check=True)
        frame=(here/'frame.rs.in').read_text().split('fn node(height:')[0]+(here/'stimulus.rs').read_text()
        (t/'peer.rs').write_text(frame.replace('/*INPUT_PROPS*/',props).replace('/*ARM*/',branch))
        phase='baseline' if config=='before' else 'candidate'
        subprocess.run([a.rustc,'--edition=2024','--cfg',phase,str(t/'peer.rs'),'-o',t/'peer','--extern','serde_json='+str(lib),'-L','dependency='+str(lib.parent)],check=True)
        subprocess.run([t/'peer'],check=True)
