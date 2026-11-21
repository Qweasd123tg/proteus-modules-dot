# Synthetic worker only. Counters are request-thread local. A custom serializer
# for Index's mandatory first field counts actual visits to the typed value.
from pathlib import Path
p=out/'storage/session-storage/src/service/catalog/durable.rs'
s=p.read_text()
def edit(old,new):
    global s
    assert s.count(old)==1,old
    s=s.replace(old,new)
edit('struct Index {\n    summary:', 'struct Index {\n    #[serde(serialize_with="count_summary")]\n    summary:')
key='pub(in crate::service) fn blob_stamps('
edit(key,'''thread_local! { static PASSES: std::cell::Cell<u32> = const { std::cell::Cell::new(0) }; }
fn count_summary<S: serde::Serializer>(summary: &StorageSessionSummary, serializer:S) -> std::result::Result<S::Ok,S::Error> {
    PASSES.set(PASSES.get()+1); summary.serialize(serializer)
}
'''+key)
# Begin AFTER constructing the Index, equally in both branches. The temporary
# instrumented candidate uses an explicit binding and drops it before I/O.
if a.candidate:
    edit('let bytes = encode(&Index {\n            summary:', 'let data = Index {\n            summary:')
    edit('fingerprint: prefix.hint.fingerprint.clone(),\n        })?;', 'fingerprint: prefix.hint.fingerprint.clone(),\n        };\n        let bytes = encode(&data)?;\n        drop(data);')
    marker='        let bytes = encode(&data)?;'
else: marker='        let checksum = crate::io::sha256_hex(&serde_json::to_vec(&data)?);'
edit(marker,'''        PASSES.set(0);
        let started=std::time::Instant::now();
'''+marker)
key='        let temporary = dir.join(format!'
edit(key,'''        let encode_ns=started.elapsed().as_nanos();
        let n_passes=PASSES.get();
'''+key)
edit('        write\n', '''        if write.is_ok() {
            eprintln!("R45 {} {} {}", n_passes,bytes.len(),encode_ns);
        }
        write
''')
if a.cpu_clock:
    key='thread_local! { static PASSES:'
    edit(key,'''fn cpu_ns() -> u64 {
        let mut tm=libc::timespec {tv_sec:0,tv_nsec:0};
        // Local Linux-only probe; the clock writes one valid timespec.
        assert_eq!(unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID,&mut tm) },0);
        tm.tv_sec as u64 * 1_000_000_000 + tm.tv_nsec as u64
    }
    '''+key)
    edit('let started=std::time::Instant::now();','let started=std::time::Instant::now();let cpu_start=cpu_ns();')
    edit('let encode_ns=started.elapsed().as_nanos();','let cpu_elapsed=cpu_ns()-cpu_start;let encode_ns=started.elapsed().as_nanos();')
    edit('eprintln!("R45 {} {} {}", n_passes,bytes.len(),encode_ns);','eprintln!("R45 {} {} {} {}", n_passes,bytes.len(),encode_ns,cpu_elapsed);')
p.write_text(s)
