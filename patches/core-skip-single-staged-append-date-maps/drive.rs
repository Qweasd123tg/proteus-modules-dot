pub struct Input {
    source: RemoteJournalSnapshot,
    roots: Option<HashMap<TurnId, ThreadId>>,
}
pub fn prep(records: &[JournalRecord], route: &str) -> Input {
    let store = RemoteSessionStore::new(records, route);
    let source = if route == "direct" {
        RemoteJournalSnapshot::open(store).unwrap()
    } else {
        RemoteValidatedRead::open_for_display(store).unwrap().source
    };
    assert_eq!(source.display_records.is_some(), route != "direct");
    let roots = source
        .display_records
        .as_ref()
        .and_then(DisplayRecords::replay_roots);
    Input { source, roots }
}
impl Input {
    pub fn rearm(&mut self) {
        self.source
            .display_records
            .as_mut()
            .unwrap()
            .rearm_roots(self.roots.clone())
    }
    pub fn fail_read(&mut self) {
        self.source.display_records.as_mut().unwrap().fail_read()
    }
    pub fn zero_seq(&mut self, r: &JournalRecord) {
        self.source.display_records.as_mut().unwrap().zero_seq(r)
    }
    pub fn callback_fails(&mut self) -> String {
        self.source
            .display_records
            .as_mut()
            .unwrap()
            .scan(|_| anyhow::bail!("injected callback failure"))
            .unwrap_err()
            .to_string()
    }
    pub fn size(&self) -> u64 {
        self.source
            .display_records
            .as_ref()
            .map_or(0, DisplayRecords::test_last)
    }
    pub fn corrupt(&mut self, mode: &str, extra: &JournalRecord) {
        self.source
            .display_records
            .as_mut()
            .unwrap()
            .corrupt(mode, extra)
    }
    pub fn run(&mut self, live: Option<TurnId>) -> Result<Vec<AppTranscriptMessage>> {
        journal::journal_transcript_from_source(&mut self.source, live)
    }
    pub fn ops(&self) -> Vec<&'static str> {
        self.source.store.log.borrow().clone()
    }
}
