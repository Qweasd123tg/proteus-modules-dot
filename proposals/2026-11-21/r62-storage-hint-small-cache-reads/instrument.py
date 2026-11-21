"""Diagnostic worker only: paired ReadCache alloc counters, old flag at startup."""
from pathlib import Path
import sys

root=Path(sys.argv[1])
p=root/'components/session-storage-module/src/main.rs'
s=p.read_text()
old='        self.0.execute(request)'
assert s.count(old)==1
s=s.replace(old,'        r62_probe::execute(&self.0, request)')
assert s.count('fn main() {')==1
s=s.replace('fn main() {','fn main() {\n    session_storage::r62_initialize();')
p.write_text(s+'''
mod r62_probe {
    use super::*;
    use std::{alloc::{GlobalAlloc, Layout, System}, cell::Cell, sync::Mutex};
    struct Counter;
    #[global_allocator]
    static ALLOCATOR: Counter=Counter;
    thread_local! { static ACTIVE: Cell<Option<(u64,u64)>> = const { Cell::new(None) }; }
    static TOTALS: Mutex<(u64,u64,u64)> = Mutex::new((0,0,0));

    fn count(n: usize) {
        ACTIVE.with(|x| {
            if let Some((calls,bytes))=x.get() { x.set(Some((calls+1,bytes+n as u64))); }
        });
    }
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self,l:Layout)->*mut u8{count(l.size());unsafe{System.alloc(l)}}
        unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{count(l.size());unsafe{System.alloc_zeroed(l)}}
        unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{count(n);unsafe{System.realloc(p,l,n)}}
        unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
    }
    pub fn execute(storage:&StorageService,request:SessionStorageRequest)->Result<SessionStorageResponse> {
        if !matches!(&request,SessionStorageRequest::ReadCache { .. }) {
            return storage.execute(request);
        }
        ACTIVE.set(Some((0,0)));
        let out=storage.execute(request);
        let (calls,bytes)=ACTIVE.replace(None).unwrap();
        let mut total=TOTALS.lock().unwrap();
        total.0+=1;
        total.1+=calls;
        total.2+=bytes;
        if total.0==320 {
            eprintln!("R62 {} {} {}",total.0,total.1,total.2);
        } else if total.0==321 {
            eprintln!("R62 1 {calls} {bytes}");
        }
        out
    }
}
''')
p=root/'storage/session-storage/src/lib.rs'
s=p.read_text()
p.write_text(s+'''
// Bounds-measurement diagnostic only.
use std::sync::atomic::{AtomicBool, Ordering};
static R62_FORCE_DEFAULT: AtomicBool = AtomicBool::new(false);
pub fn r62_initialize() {
    R62_FORCE_DEFAULT.store(std::env::var_os("R62_FORCE_DEFAULT").is_some(), Ordering::Relaxed);
}
''')
p=root/'storage/session-storage/src/service/cache.rs'
s=p.read_text()
old='''    let bytes = match crate::io::bounded_read_with_size_hint(
        &path(&dir, &key),
'''
assert s.count(old)==1
n=s.index(old)
tail=s[n:]
end=tail.index('    ) {')
block=tail[:end+6].strip()
args=block.splitlines()[2:4]
assert len(args)==2 and 'CACHE_READ_HINT_MAX_BYTES' in args[1]
limit=args[0].strip().removesuffix(',')
new=f'''    let path = path(&dir, &key);
    let raw = if crate::R62_FORCE_DEFAULT.load(std::sync::atomic::Ordering::Relaxed) {{
        crate::io::bounded_read(&path, {limit})
    }} else {{
        crate::io::bounded_read_with_size_hint(&path, {limit}, CACHE_READ_HINT_MAX_BYTES)
    }};
    let bytes = match raw {{'''
assert s[n:n+end+7].endswith('{')

p.write_text(s[:n]+new+s[n+end+7:])
