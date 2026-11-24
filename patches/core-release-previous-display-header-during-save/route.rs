// Storage transport and already-validated/rendered model are the two external boundaries.
type StorageService = std::rc::Rc<MemoryStore>;
impl Clone for RemoteSessionStore {
    fn clone(&self) -> Self {
        Self(self.0.clone())
    }
}
impl std::ops::Deref for RemoteSessionStore {
    type Target = MemoryStore;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}
impl RemoteSessionStore {
    fn open(s: StorageService, p: PathBuf) -> Result<Self> {
        anyhow::ensure!(s.session_dir() == p, "foreign path");
        Ok(Self(s))
    }
}
struct RemoteJournalSnapshot(Vec<AppTranscriptMessage>);
struct RemoteValidatedRead {
    model: SessionReadModel,
    cur: RemoteJournalCursor,
}
impl RemoteValidatedRead {
    fn open_for_display(s: RemoteSessionStore) -> Result<Self> {
        s.validated.set(s.validated.get() + 1);
        let model = s
            .staged
            .borrow_mut()
            .take()
            .ok_or_else(|| anyhow!("unexpected replay"))?;
        Ok(Self {
            model,
            cur: RemoteJournalCursor {
                snapshot: s.snap.clone(),
            },
        })
    }
    fn cursor(&self) -> RemoteJournalCursor {
        self.cur.clone()
    }
    fn history(&self) -> &[CanonicalMessage] {
        &self.model.conversation.messages
    }
}
// Distinct wrapper modules have different RemoteValidatedRead types. Use an arm-local trait
// to substitute validated-input decoding without introducing an inherent overload.
trait MakeModel {
    fn from_validated(
        s: &RemoteSessionStore,
        r: RemoteValidatedRead,
        render: impl FnOnce(&mut RemoteJournalSnapshot) -> Result<Vec<AppTranscriptMessage>>,
    ) -> Result<SessionReadModel>;
}
impl MakeModel for SessionReadModel {
    fn from_validated(
        _: &RemoteSessionStore,
        r: RemoteValidatedRead,
        render: impl FnOnce(&mut RemoteJournalSnapshot) -> Result<Vec<AppTranscriptMessage>>,
    ) -> Result<Self> {
        let mut m = r.model;
        m.transcript = render(&mut RemoteJournalSnapshot(std::mem::take(
            &mut m.transcript,
        )))?;
        Ok(m)
    }
}
