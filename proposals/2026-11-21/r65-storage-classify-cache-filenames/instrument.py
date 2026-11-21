"""Add test-only paired classifier/candidate counts to the exact checkout."""
from pathlib import Path
import subprocess
import sys

repo=Path(sys.argv[1])
root=repo/'storage/session-storage/src'
p=root/'lib.rs'
p.write_text(p.read_text()+'''
#[cfg(test)]
mod r65_probe {
    use std::{alloc::{GlobalAlloc, Layout, System},cell::Cell};
    struct Alloc;
    #[global_allocator]
    static COUNT: Alloc = Alloc;
    thread_local! { static METER: Cell<Option<[u64;7]>> = const { Cell::new(None) }; }
    fn add(i:usize,n:usize) {
        METER.with(|v| if let Some(mut a)=v.get() {a[i]+=n as u64;v.set(Some(a));});
    }
    pub fn observe_name(name:&std::ffi::OsStr,old:bool) {
        add(0,1);
        add(1,name.as_encoded_bytes().len());
        if old { add(2,name.as_encoded_bytes().len()); }
    }
    pub fn keep_lookup() { add(3,1); }
    pub fn metadata() { add(4,1); }
    pub fn count_scope<T>(f:impl FnOnce()->T)->(T,[u64;7]) {
        METER.set(Some([0;7]));
        let out=f();
        (out,METER.replace(None).unwrap())
    }
    fn count(n:usize){add(5,1);add(6,n);}
    unsafe impl GlobalAlloc for Alloc {
        unsafe fn alloc(&self,l:Layout)->*mut u8 {count(l.size());unsafe{System.alloc(l)}}
        unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {count(l.size());unsafe{System.alloc_zeroed(l)}}
        unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {count(n);unsafe{System.realloc(p,l,n)}}
        unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
    }
}
''')
p=root/'service/cache.rs'
s=p.read_text()
needle='    let keep_name = keep.file_name();'
assert s.count(needle)==1
s=s.replace(needle,'''    #[cfg(test)]
    crate::r65_probe::keep_lookup();
'''+needle)
needle='        if !is_cache_name(&name) {'
assert s.count(needle)==1
s=s.replace(needle,'''        #[cfg(test)]
        crate::r65_probe::observe_name(&name, false);
'''+needle)
needle='        let meta = entry.metadata()?;'
assert s.count(needle)==1
s=s.replace(needle,'''        #[cfg(test)]
        crate::r65_probe::metadata();
'''+needle)
old=subprocess.check_output(['git','-C',str(repo),'show','HEAD:storage/session-storage/src/service/cache.rs'],text=True)
old=old[old.index('fn evict('):].strip()
old=old.replace('fn evict(','fn legacy_evict(',1)
old=old.replace('        let label = name.to_string_lossy();','''        crate::r65_probe::observe_name(&name, true);
        let label = name.to_string_lossy();''')
old=old.replace('        let meta = entry.metadata()?;', '''        crate::r65_probe::metadata();
        let meta = entry.metadata()?;''')
old=old.replace('        if Some(name.as_os_str()) != keep.file_name() {','''        crate::r65_probe::keep_lookup();
        if Some(name.as_os_str()) != keep.file_name() {''')
p.write_text(s+'\n#[cfg(test)]\n'+old+'\n')
p=root/'service/cache/tests.rs'
p.write_text(p.read_text()+'\n'+Path(__file__).with_name('evict-probe.rs').read_text())
