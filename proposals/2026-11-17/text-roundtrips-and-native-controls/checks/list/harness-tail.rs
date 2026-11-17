 output
}
fn expected(entries:&[Entry])->String{let mut rows:Vec<_>=entries.iter().map(|e|format!("{}\t{}",e.k.text(),e.n.to_string_lossy())).collect();rows.sort();rows.join("\n")}
fn counts()->(usize,usize){(CALLS.load(Ordering::Relaxed),REQUEST.load(Ordering::Relaxed))}
fn test_listing(label:&str,names:&[OsString],n:usize)->(usize,usize) {
 let entries=(0..n).map(|i|Entry{n:names[(i*19+3)%names.len()].clone(),k:[Kind::Dir,Kind::File,Kind::Symlink,Kind::Unknown][i%4]}).collect::<Vec<_>>();
 let want=expected(&entries);let (a,b)=counts();let output=std::hint::black_box(listing(std::hint::black_box(&entries)));let (c,d)=counts();
 assert_eq!(output,want,"{label}: sorted output must be byte-for-byte unchanged");
 println!("{label}: rows={n} output_bytes={} alloc_or_realloc={} gross_requested_bytes={}",output.len(),c-a,d-b);
 (c-a,d-b)
}
fn main(){
 let ascii:Vec<OsString>=(0..512).map(|i|OsString::from(format!("desktop-pref-{i:04}.json"))).collect();
 let mixed:Vec<OsString>=["pic.png","a","A","Capital Letter Version 2","Отчёт 2026.md","東京.png","é.txt","e\u{301}.txt","📎.md","dup.doc"].into_iter().map(OsString::from).collect();
 for n in [0,1,4,33,1024]{test_listing("names/control",&mixed,n);}
 #[cfg(unix)]{use std::os::unix::ffi::OsStrExt;let names=[OsStr::from_bytes(b"old_\xff.dat").to_owned(),OsString::from("report.md")];
 test_listing("lossy/control",&names,79);}
 let (a,_)=test_listing("bulk/ascii",&ascii,8192);test_listing("bulk/mixed",&mixed,8192);
 // One owned name from the synthetic DirEntry plus its retained final row; vector, stable-sort scratch and the final join need far fewer than 100 additional requests.
 assert!(a<=2*8192+100,"too many allocations for UTF-8 lines: {a}");
}
