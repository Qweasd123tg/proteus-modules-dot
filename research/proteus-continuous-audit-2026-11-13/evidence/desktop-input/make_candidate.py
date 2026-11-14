from pathlib import Path
import difflib
out=Path(__file__).resolve().parent;root=out.parent
src=(out/'probe/src/lib.rs').read_text()
a=src.index('                                InputEvent::Change\n');b=src.index('\n                                {',a)
assert 'input.value != text.as_ref()' in src[a:b]
fixed=src[:a]+'                                InputEvent::Change =>'+src[b:]
(out/'fixed-probe/src').mkdir(parents=True,exist_ok=True)
for name in ['Cargo.toml','Cargo.lock']:(out/'fixed-probe'/name).write_bytes((out/'probe'/name).read_bytes())
(out/'fixed-probe/src/widget.rs').write_bytes((out/'probe/src/widget.rs').read_bytes())
fixed=fixed.replace('InputEvent::Change =>\n                                {', 'InputEvent::Change => {').replace('let (action, submit, identity) = (action.clone(), submit.clone(), id.clone());', 'let (action, submit) = (action.clone(), submit.clone());')
(out/'fixed-probe/src/lib.rs').write_text(fixed.replace(str(out/'probe/src/widget.rs'),str(out/'fixed-probe/src/widget.rs')))
p='src/ui/extensions/declarative/fields.rs';s=(root/p).read_text();a=s.index('                                InputEvent::Change\n');b=s.index('\n                                {',a);new=s[:a]+'                                InputEvent::Change =>'+s[b:]
new=new.replace('InputEvent::Change =>\n                                {', 'InputEvent::Change => {').replace('let (action, submit, identity) = (action.clone(), submit.clone(), id.clone());', 'let (action, submit) = (action.clone(), submit.clone());')
(out/'candidate-send-all-input-changes.patch').write_text(''.join(difflib.unified_diff(s.splitlines(True),new.splitlines(True),fromfile='a/'+p,tofile='b/'+p)))
