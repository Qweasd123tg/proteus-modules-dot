"""Test-only allocation and projection-visit probe; never shipping instrumentation."""
from pathlib import Path
import sys

root=Path(sys.argv[1])/'storage/session-storage/src'
p=root/'lib.rs'
p.write_text(p.read_text()+'''
#[cfg(test)]
mod r63_probe {
    use std::{alloc::{GlobalAlloc, Layout, System},cell::Cell};
    struct Measure;
    #[global_allocator]
    static ALLOCATOR:Measure=Measure;
    thread_local! {
        static FULL:Cell<bool>=const { Cell::new(false) };
        static ACTIVE:Cell<Option<(u64,u64,u64)>>=const { Cell::new(None) };
    }
    pub fn full_replay()->bool { FULL.get() }
    pub fn context_visit() {
        ACTIVE.with(|a| if let Some((calls,bytes,ctx))=a.get() {
            a.set(Some((calls,bytes,ctx+1)));
        });
    }
    pub fn measure<T>(full:bool,f:impl FnOnce()->T)->(T,(u64,u64,u64)) {
        FULL.set(full);
        ACTIVE.set(Some((0,0,0)));
        let info=f();
        let stats=ACTIVE.replace(None).unwrap();
        FULL.set(false);
        (info,stats)
    }
    fn count(n:usize) {
        ACTIVE.with(|a| if let Some((calls,bytes,ctx))=a.get() {
            a.set(Some((calls+1,bytes+n as u64,ctx)));
        });
    }
    unsafe impl GlobalAlloc for Measure {
        unsafe fn alloc(&self,l:Layout)->*mut u8 {
            count(l.size()); unsafe {System.alloc(l)}
        }
        unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {
            count(l.size()); unsafe {System.alloc_zeroed(l)}
        }
        unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {
            count(n); unsafe {System.realloc(p,l,n)}
        }
        unsafe fn dealloc(&self,p:*mut u8,l:Layout) {
            unsafe {System.dealloc(p,l)}
        }
    }
}
''')
p=root/'snapshot.rs'
s=p.read_text()
old='''        if MODEL_CONTEXT {
            self.model_context.apply(record);
        }'''
assert s.count(old)==1
p.write_text(s.replace(old,'''        if MODEL_CONTEXT {
            #[cfg(test)]
            crate::r63_probe::context_visit();
            self.model_context.apply(record);
        }'''))
p=root/'service.rs'
s=p.read_text()
old='''                Ok(SessionStorageResponse::Usage {
                    usage: self.get_snapshot(&snapshot)?.fold_usage()?.snapshot(id),
                })'''
assert s.count(old)==1
p.write_text(s.replace(old,'''                let source = self.get_snapshot(&snapshot)?;
                #[cfg(test)]
                if crate::r63_probe::full_replay() {
                    return Ok(SessionStorageResponse::Usage {
                        usage: source.fold()?.usage.snapshot(id),
                    });
                }
                Ok(SessionStorageResponse::Usage {
                    usage: source.fold_usage()?.snapshot(id),
                })'''))
p=root/'tests/usage.rs'
p.write_text(p.read_text()+'\n'+Path(__file__).with_name('usage-probe.rs').read_text())
