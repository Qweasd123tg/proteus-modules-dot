"""Use the pinned source's actual old sidebar membership implementation."""
from pathlib import Path
import sys

src,out=map(Path,sys.argv[1:])
text=src.read_text()
start=text.index('    pub fn contains(&self, dir: &ChatKey) -> bool {')
end=text.index('\n\n    fn updated_at_ms',start)
code=text[start:end]
assert code.count('vec![self]') == 1
code=code.replace('pub fn contains(&self, dir: &ChatKey)',"pub(super) fn contains(root: &Row<'_>, dir: &ChatKey)")
code=code.replace('vec![self]','vec![root]')
out.write_text("use crate::sessions::Row;\nuse proteus_tabs::ChatKey;\n\n"+code.strip()+"\n")
