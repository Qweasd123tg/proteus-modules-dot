use std::{alloc::{GlobalAlloc, Layout, System}, ffi::{OsStr,OsString}, sync::atomic::{AtomicUsize,Ordering}};
struct Count; static CALLS:AtomicUsize=AtomicUsize::new(0);static REQUEST:AtomicUsize=AtomicUsize::new(0);
unsafe impl GlobalAlloc for Count{
 unsafe fn alloc(&self,l:Layout)->*mut u8{CALLS.fetch_add(1,Ordering::Relaxed);REQUEST.fetch_add(l.size(),Ordering::Relaxed);unsafe{System.alloc(l)}}
 unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{CALLS.fetch_add(1,Ordering::Relaxed);REQUEST.fetch_add(n,Ordering::Relaxed);unsafe{System.realloc(p,l,n)}}
 unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
}
#[global_allocator]static A:Count=Count;
#[derive(Copy,Clone)]enum Kind{File,Dir,Symlink,Unknown}
impl Kind{fn is_dir(self)->bool{matches!(self,Self::Dir)} fn is_symlink(self)->bool{matches!(self,Self::Symlink)}
 fn text(self)->&'static str{match self{Self::File=>"file",Self::Dir=>"dir",Self::Symlink=>"symlink",Self::Unknown=>"unknown"}}}
struct Entry{n:OsString,k:Kind}
impl Entry{fn file_name(&self)->OsString{self.n.clone()}fn file_type(&self)->Result<Kind,()>{if matches!(self.k,Kind::Unknown){Err(())}else{Ok(self.k)}}}
// Only the source's entry-name/render/sort/join statements are spliced here.
// No fs, directory enumeration, tool invocation or configuration.
fn listing(entries:&[Entry])->String{
 let mut lines=Vec::new(); for entry in entries{
