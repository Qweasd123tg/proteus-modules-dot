# Build-only: keep wire responses untouched. Tiny fixture IDs fit in usize.
base=out/'storage/session-storage/src'
def sub(file, a, b):
    p=base/file; s=p.read_text(); assert s.count(a)==1,(file,a); p.write_text(s.replace(a,b))
p=base/'lib.rs'
p.write_text(p.read_text()+'''
pub(crate) mod diag {
    use std::{cell::RefCell,time::Instant};
    thread_local! { static C: RefCell<(Vec<u128>,[usize;3])> = const {RefCell::new((Vec::new(),[0;3]))}; }
    pub fn visit(id: u128){C.with_borrow_mut(|c|c.0.push(id));}
    pub fn hit(k:usize){C.with_borrow_mut(|c|c.1[k]+=1);}
    pub fn reset(){C.with_borrow_mut(|c|{c.0.clear();c.1=[0;3];});}
    pub fn report(t:Instant) {let ns=t.elapsed().as_nanos(); C.with_borrow(|c|eprintln!("R42 {} {:?} {:?}",ns,c.1,c.0));}
}
''')
sub('service/catalog.rs','let descriptor = state.open(path)?;', 'let descriptor = state.open(path)?; crate::diag::visit(descriptor.session.session_id.as_u128());')
sub('service/catalog.rs','return Some(summary);','crate::diag::hit(0); return Some(summary);')
sub('service/catalog.rs','        Some(summary)\n','        crate::diag::hit(1); Some(summary)\n')
sub('service/catalog.rs','let session = self.descriptor.session.session_id;', 'crate::diag::hit(2); let session = self.descriptor.session.session_id;')
sub('service/sessions.rs','let _scan = self.lock_catalog()?;', 'let _scan = self.lock_catalog()?; crate::diag::reset(); let t=std::time::Instant::now();')
sub('service/sessions.rs','Ok(SessionStorageResponse::Sessions { sessions: result })','crate::diag::report(t); Ok(SessionStorageResponse::Sessions { sessions: result })')
