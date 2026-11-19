# Only for memory-budgeted isolated test build, analogous to previous control.
import sys,re
from pathlib import Path
p=Path(sys.argv[1])/'crates/proteus-core'
for f in [*(p/'src').rglob('*.rs'),*(p/'tests/support').rglob('*.rs')]:
 s=f.read_text();t=re.sub(r'(?m)^(\s*)#\[(tokio::test(?:\([^\]]*\))?|test)\](?!\s*async fn r9_real_turn_fixed_active_history)',r'\1#[allow(dead_code)]',s)
 if s!=t: f.write_text(t)
