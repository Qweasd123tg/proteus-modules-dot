"""Build a leaf-level presentation probe. No app, theme preferences, or real windows are accessed."""
from pathlib import Path
import json,subprocess,sys,tempfile,os
proof=Path(__file__).resolve().parent
base,patch=map(Path,sys.argv[1:3])
def braced(text,needle):
    start=text.index(needle);ix=text.index('{',start);depth=1
    while depth:
        ix+=1
        depth+=(text[ix]=='{')-(text[ix]=='}')
    return text[start:ix+1]
v=base/'vendor/gpui-component/src/theme'
colors=(v/'color.rs').read_text()
vendor='\n'.join(braced(colors,needle) for needle in ['pub fn try_parse_background(', 'pub(crate) fn try_parse_theme_color(', 'struct ParsedLinearGradient', 'fn parse_linear_gradient(', 'fn split_top_level_commas(', 'fn parse_linear_gradient_angle(', 'fn parse_linear_gradient_direction(', 'fn parse_linear_color_stop('])
vendor+='\n'+braced((v/'schema.rs').read_text(),'fn try_parse_theme_token(').replace('anyhow::Result','Result')
vendor+='\n'+braced((v/'theme_color.rs').read_text(),'impl From<ThemeToken> for Fill')
bg=braced((base/'vendor/gpui-fast/src/styled.rs').read_text(),'fn bg<F>')
paint=(patch/'src/ui/selection.rs').read_text()
fn=braced(paint,'pub(crate) fn background(')
menu=braced(paint[paint.index('// Keep native menu padding'):],'.when(selected, |row|')+')'
fn+='\nfn menu_surface(selected:bool,theme:&Theme)->Div{div()'+menu+'}'
src=(proof/'frame.rs').read_text().replace('/* VENDOR */',vendor).replace('/* STYLE */',bg).replace('/* PAINT */',fn)
theme=json.loads((proof/'theme.json').read_text())['themes'][0]['colors']
with tempfile.TemporaryDirectory() as tmp:
    rd=Path(tmp);(rd/'proof.rs').write_text(src)
    subprocess.run([os.getenv('RUSTC','rustc'),'--edition=2024','-Awarnings',str(rd/'proof.rs'),'-o',str(rd/'probe')],check=True)
    a=subprocess.run([str(rd/'probe'),theme['sidebar.accent.background'],theme['list.hover.background']])
    b=subprocess.run([str(rd/'probe'),'#2255aa88','#558855'],check=True)
    sys.exit(a.returncode)
