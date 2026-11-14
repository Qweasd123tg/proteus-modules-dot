#!/usr/bin/env python3
"""Compile unchanged production SentImages state with headless cache/type stubs."""
from pathlib import Path
import subprocess, hashlib
ROOT = Path('/workspace/scratch/3ba0fff8d310/desktop-behaviour')
OUT = Path(__file__).resolve().parent
source = (ROOT / 'src/ui/chat/images.rs').read_text()
chunk = source[source.index('const THUMB:'):source.index('\nimpl Chat {')]
# These stubs model an empty successful-image cache. The methods under test are
# copied byte-for-byte, not reimplemented. No GUI rendering or HTTP is exercised.
prefix = r'''
#![allow(dead_code)]
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
mod tested {
use super::*;
'''
tests = r'''
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
'''
# cache stub sits in the outer module, so production Key must be imported there.
prefix += chunk + '\n'
code = prefix + tests + '\nuse tested::Key;\n'
# Production Key is private. In the shim use a sibling re-export rather than
# changing the copied source; keep cache in tested instead.
code = code.replace('mod tested {\nuse super::*;\n', '')
code = code.replace('\n}\n\nuse tested::Key;\n', '\n')
# pub(super) visibility requires an enclosing module. Wrap everything once.
code = '#![allow(dead_code)]\nmod isolated {\n' + code.replace('#![allow(dead_code)]\n', '', 1) + '\n}\nuse isolated::transcript;\n'
(OUT / 'image_probe.rs').write_text(code)
print('Desktop SHA:', subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT,text=True).strip(), flush=True)
print('images.rs sha256:', hashlib.sha256(source.encode()).hexdigest(), flush=True)
print('Extracted lines:', source[:source.index('const THUMB:')].count('\n')+1, '-', source[:source.index('\nimpl Chat {')].count('\n')+1, flush=True)
subprocess.run(['rustc','--edition=2024','--test',str(OUT/'image_probe.rs'),'-o',str(OUT/'image_probe')], check=True)
subprocess.run([str(OUT/'image_probe'),'--nocapture'],check=True)
