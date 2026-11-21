"""Linux-only count probe, applied to a separate candidate checkout."""
from pathlib import Path
import sys

root=Path(sys.argv[1])/'storage/session-storage/src'
p=root/'display.rs'
s=p.read_text()
needle='    pub fn push(&mut self, record: &JournalRecord) -> Result<()> {'
assert s.count(needle)==1
s=s.replace(needle,'''    pub fn r61_capacity(&self) -> usize { self.writer.capacity() }

'''+needle)
p.write_text(s)
p=root/'service/display.rs'
s=p.read_text()
b='''        let mut display = match self.kind {
            BackendKind::Jsonl => DisplayWriter::for_jsonl(budget, source.extent()),
            BackendKind::Sqlite => DisplayWriter::new(budget),
        };'''
assert s.count(b)==1
s=s.replace(b,'''        let before_stage = r61_io::read();
        let mut display = if std::env::var_os("R61_FORCE_DEFAULT_STAGE").is_some() {
            DisplayWriter::new(budget)
        } else {
            match self.kind {
                BackendKind::Jsonl => DisplayWriter::for_jsonl(budget, source.extent()),
                BackendKind::Sqlite => DisplayWriter::new(budget),
            }
        };
        let capacity = display.as_ref().map_or(0, DisplayWriter::r61_capacity);''')
needle='        if source.source_version()? != version {'
assert s.count(needle)==1
s=s.replace(needle,'''        let after_stage = r61_io::read();
'''+needle)
needle='        let Some(display) = display.and_then(DisplayWriter::finish) else {'
assert s.count(needle)==1
s=s.replace(needle,'''        let before_finish = r61_io::read();
        let display = display.and_then(DisplayWriter::finish);
        let after_finish = r61_io::read();
        if let Some(stage) = &display {
            let (stream_calls, stream_bytes) = r61_io::delta(before_stage, after_stage);
            let (finish_calls, finish_bytes) = r61_io::delta(before_finish, after_finish);
            eprintln!("R61 {stream_calls} {stream_bytes} {finish_calls} {finish_bytes} {} {capacity}",
                      stage.bytes);
        }
        let Some(display) = display else {''')
p.write_text(s+'''
// Measurement-only Linux process counters, not an I/O interposer or policy change.
mod r61_io {
    pub fn read() -> (u64, u64) {
        let file = std::fs::read_to_string("/proc/self/io").expect("read own counters");
        let get = |name: &str| {
            file.lines().find_map(|l| l.strip_prefix(name)).unwrap().trim().parse::<u64>().unwrap()
        };
        (get("syscw:"), get("wchar:"))
    }
    pub fn delta(before: (u64, u64), after: (u64, u64)) -> (u64, u64) {
        (after.0 - before.0, after.1 - before.1)
    }
}
''')
