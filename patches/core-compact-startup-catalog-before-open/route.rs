type StorageService = std::rc::Rc<Service>;
type RemoteJournalSnapshot = Vec<AppTranscriptMessage>;
#[derive(Clone)]
pub(crate) struct RemoteSessionStore(std::rc::Rc<Opened>);

impl std::ops::Deref for RemoteSessionStore {
    type Target = Opened;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}
impl RemoteSessionStore {
    fn open(service: StorageService, path: PathBuf) -> Result<Self> {
        meter::checkpoint(4);
        service.mark("open", &path);
        let at = service.opens.get();
        service.opens.set(at + 1);
        let plan = service.plans.get(at).unwrap_or(&Attempt::Cold(1));
        if *plan == Attempt::Error {
            bail!("injected open failure")
        }
        let docs = if matches!(plan, Attempt::Warm(_) | Attempt::EmptyCache(_)) {
            Some(&service.cache)
        } else {
            None
        };
        let store = Self(std::rc::Rc::new(Opened::new(
            path.clone(),
            *plan,
            service.clone(),
        )));
        if let Some(docs) = docs {
            assert_eq!(path, &*docs.path);
            // Clone the response on read, not the whole service cache on open.
        }
        Ok(store)
    }
}
struct RemoteValidatedRead {
    history: Vec<CanonicalMessage>,
}
impl RemoteValidatedRead {
    fn open_for_display(store: RemoteSessionStore) -> Result<Self> {
        meter::checkpoint(5);
        store.service.mark("strict-display", store.session_dir());
        let n = match store.plan {
            Attempt::ValidateError => bail!("injected display validation failure"),
            Attempt::Cold(n) | Attempt::EmptyCache(n) => n,
            _ => panic!("unexpected validation route"),
        };
        Ok(Self {
            history: (0..n).map(canonical).collect(),
        })
    }
    fn cursor(&self) -> RemoteJournalCursor {
        RemoteJournalCursor {
            snapshot: snapshot(),
        }
    }
    fn history(&self) -> &[CanonicalMessage] {
        &self.history
    }
}
trait MakeModel {
    fn from_validated(
        s: &RemoteSessionStore,
        r: RemoteValidatedRead,
        render: impl FnOnce(&mut RemoteJournalSnapshot) -> Result<Vec<AppTranscriptMessage>>,
    ) -> Result<SessionReadModel>;
}
impl MakeModel for SessionReadModel {
    fn from_validated(
        s: &RemoteSessionStore,
        r: RemoteValidatedRead,
        render: impl FnOnce(&mut RemoteJournalSnapshot) -> Result<Vec<AppTranscriptMessage>>,
    ) -> Result<Self> {
        let mut m = model(s, r.history);
        m.transcript = render(&mut m.transcript)?;
        Ok(m)
    }
}
