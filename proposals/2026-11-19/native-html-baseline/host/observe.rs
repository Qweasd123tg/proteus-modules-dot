// Test-only observers added to the private qualification copy, never the proposal.
static R5_COUNTS: [std::sync::atomic::AtomicUsize; 4] =
    [const { std::sync::atomic::AtomicUsize::new(0) }; 4];

pub(super) fn r5_tick(kind: usize, bytes: usize) {
    use std::sync::atomic::Ordering::Relaxed;
    R5_COUNTS[kind * 2].fetch_add(1, Relaxed);
    R5_COUNTS[kind * 2 + 1].fetch_add(bytes, Relaxed);
}

pub fn r5_counts() -> [usize; 4] {
    std::array::from_fn(|i| R5_COUNTS[i].load(std::sync::atomic::Ordering::Relaxed))
}

impl TextViewState {
    pub fn r5_config(&mut self, extensions: MarkdownExtensions, cx: &mut Context<Self>) {
        self.set_markdown_extensions(Arc::new(extensions), cx)
    }

    pub fn r5_snapshot(&self) -> (usize, usize, usize, bool, String, String, String, Option<String>, u64) {
        use std::hash::{DefaultHasher, Hash, Hasher};
        let mut digest = DefaultHasher::new();
        // Hash the debug representation of the actual committed document, separately
        // from user-visible plain/source/selection checks. The comparison is bounded
        // to these fixtures, two builds and this compiler, not a public serialization.
        format!("{:?}", self.parsed_content.document).hash(&mut digest);
        (self.revision, self.committed_revision, self.selection_revision, self.is_ready(),
         self.source().to_string(), self.rendered_text().as_str().to_owned(), self.selected_text(),
         self.parsed_error.as_ref().map(|x| x.to_string()), digest.finish())
    }
}
