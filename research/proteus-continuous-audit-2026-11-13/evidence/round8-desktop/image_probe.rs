#![allow(dead_code)]
mod isolated {

use std::{cell::RefCell, collections::HashMap, path::PathBuf,
    sync::{Arc, Weak, atomic::{AtomicU64, Ordering}}};
type SharedString = String;
#[derive(Clone)] pub struct ImageRef { pub id: String, pub name: String, pub mime_type: String, pub path: PathBuf }
pub(crate) mod transcript { pub struct Entry { pub images: Vec<super::ImageRef> } }
mod schedule { #[derive(Default)] pub struct Queue; }
mod cache {
    use super::*;
    pub struct Bitmap;
    impl Bitmap { pub fn has_scene_lease(&self) -> bool { false } }
    #[derive(Default)] pub struct Cache;
    impl Cache {
        pub fn prune(&mut self) {}
        pub fn get(&mut self, _: &Key, _: &Arc<()>) -> Option<Arc<Bitmap>> { None }
    }
}
const THUMB: f32 = 96.;
static NEXT_TICKET: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Debug, PartialEq, Eq)]
struct Key {
    connection: u64,
    dir: PathBuf,
    id: String,
    edge: u32,
}

enum Stored {
    Loading,
    Waiting,
    Ready(Weak<cache::Bitmap>),
    Failed(SharedString),
}

struct Slot {
    key: Key,
    ticket: u64,
    owner: Arc<()>,
    state: Stored,
}

impl Slot {
    fn matches(&self, key: &Key, ticket: u64) -> bool {
        self.key == *key && self.ticket == ticket && matches!(self.state, Stored::Loading)
    }
}

#[derive(Default)]
struct Shared {
    cache: cache::Cache,
    queue: schedule::Queue,
}

thread_local! {
    static SHARED: RefCell<Shared> = RefCell::default();
}

#[derive(Default)]
pub(super) struct SentImages {
    by_id: HashMap<String, Slot>,
}

impl SentImages {
    pub(super) fn retain(&mut self, entries: &[crate::transcript::Entry]) {
        let ids: std::collections::HashSet<_> = entries
            .iter()
            .flat_map(|row| row.images.iter().map(|image| image.id.as_str()))
            .collect();
        self.by_id.retain(|id, _| ids.contains(id.as_str()));
        SHARED.with(|shared| shared.borrow_mut().cache.prune());
    }

    pub(super) fn missing(
        &mut self,
        images: &[ImageRef],
        connection: u64,
        dir: &std::path::Path,
        edge: u32,
    ) -> Vec<String> {
        let mut missing = Vec::new();
        for image in images {
            let key = Key {
                connection,
                dir: dir.into(),
                id: image.id.clone(),
                edge,
            };
            if self
                .by_id
                .get(&image.id)
                .is_some_and(|slot| slot.key != key)
            {
                self.by_id.remove(&image.id);
            }
            if let Some(slot) = self.by_id.get_mut(&image.id) {
                if let Some(image) =
                    SHARED.with(|shared| shared.borrow_mut().cache.get(&key, &slot.owner))
                {
                    slot.state = Stored::Ready(Arc::downgrade(&image));
                    continue;
                }
                if let Stored::Ready(bitmap) = &slot.state
                    && bitmap
                        .upgrade()
                        .is_some_and(|bitmap| bitmap.has_scene_lease())
                {
                    // Replayed GPUI scenes keep their bitmap safe after LRU
                    // eviction; reloading would also reset GIF frame timing.
                    continue;
                }
                if !matches!(&slot.state, Stored::Ready(_) | Stored::Waiting) {
                    continue;
                }
                // A raw frame/deferred cleanup Arc has no scene lease and
                // cannot make an evicted bitmap safe to upload again.
                slot.state = Stored::Loading;
            }
            missing.push(image.id.clone());
        }
        SHARED.with(|shared| shared.borrow_mut().cache.prune());
        missing
    }
}

impl Drop for SentImages {
    fn drop(&mut self) {
        self.by_id.clear();
        let _ = SHARED.try_with(|shared| {
            if let Ok(mut shared) = shared.try_borrow_mut() {
                shared.cache.prune();
            }
        });
    }
}


#[cfg(test)] mod probe_tests {
    use super::*;
    fn fixture() -> (SentImages, Key, ImageRef) {
        let key = Key { connection: 73, dir: "/session".into(), id: "image-1".into(), edge: 96 };
        let image = ImageRef { id: key.id.clone(), name: "ok.png".into(), mime_type: "image/png".into(), path: "images/ok.png".into() };
        let mut store = SentImages::default();
        store.by_id.insert(key.id.clone(), Slot { key: key.clone(), ticket: 1, owner: Arc::new(()), state: Stored::Failed("temporary connection reset".into()) });
        (store, key, image)
    }
    #[test]
    fn observed_failed_image_never_becomes_missing_at_same_connection_after_recovery() {
        let (mut store, key, image) = fixture();
        for _ in 0..100 {
            assert!(store.missing(&[image.clone()], key.connection, &key.dir, key.edge).is_empty());
        }
        assert!(matches!(store.by_id[&key.id].state, Stored::Failed(_)));
    }
    #[test]
    fn observed_authoritative_snapshot_reconciliation_does_not_clear_failure() {
        let (mut store, key, image) = fixture();
        store.retain(&[crate::transcript::Entry { images: vec![image.clone()] }]);
        assert!(store.missing(&[image], key.connection, &key.dir, key.edge).is_empty());
        assert!(matches!(store.by_id[&key.id].state, Stored::Failed(_)));
    }
    #[test]
    fn control_new_api_identity_or_thumbnail_scale_allows_retry() {
        for fresh_connection in [true, false] {
            let (mut store, key, image) = fixture();
            let connection = key.connection + u64::from(fresh_connection);
            let edge = key.edge + u32::from(!fresh_connection);
            assert_eq!(store.missing(&[image], connection, &key.dir, edge), vec![key.id]);
        }
    }
    #[test]
    fn control_eviction_and_return_allows_retry() {
        let (mut store, key, image) = fixture();
        store.retain(&[]);
        assert_eq!(store.missing(&[image], key.connection, &key.dir, key.edge), vec![key.id]);
    }
}

}
use isolated::transcript;
