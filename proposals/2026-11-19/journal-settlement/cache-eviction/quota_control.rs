
#[cfg(test)]
mod r7_eviction_controls {
    use super::*;
    use std::fs::{File, FileTimes};
    use std::time::{Duration, UNIX_EPOCH};
    const M: u64 = 1024 * 1024;
    // evict accounts logical file lengths without opening or decoding their bytes.
    // Sparse fixtures let both versions exercise real metadata/unlink without 128MiB IO.
    fn file(dir: &Path, name: &str, bytes: u64, age: u64) -> PathBuf {
        let path = dir.join(name);
        let f = File::create(&path).unwrap();
        f.set_len(bytes).unwrap();
        f.set_times(FileTimes::new().set_modified(UNIX_EPOCH + Duration::from_secs(age))).unwrap();
        path
    }
    #[test]
    fn exact_quota_then_overflow_protects_keep_and_non_cache_and_removes_oldest_first() {
        let temp = tempfile::tempdir().unwrap();
        let dir = temp.path();
        let keep = file(dir, ".storage-cache-keep.json", 32 * M, 0);
        let oldest = file(dir, ".storage-cache-a.json", M, 1);
        let second = file(dir, ".storage-cache-b.json", 8 * M, 2);
        let newer = file(dir, ".storage-cache-c.json", 48 * M, 3);
        let newest = file(dir, ".storage-cache-d.json", 39 * M, 4);
        let other = file(dir, "unrelated.json", 70 * M, 1);
        let tmp = file(dir, ".storage-cache-write.tmp", 70 * M, 1);
        let directory = dir.join(".storage-cache-directory.json");
        std::fs::create_dir(&directory).unwrap();
        evict(dir, &keep).unwrap();
        assert!([&oldest, &second, &newer, &newest, &keep].iter().all(|p| p.exists()));
        let newest = file(dir, ".storage-cache-d.json", 40 * M + 1, 4);
        evict(dir, &keep).unwrap();
        assert!(!oldest.exists() && !second.exists());
        assert!([&keep, &newer, &newest, &other, &tmp, &directory].iter().all(|p| p.exists()));
    }
}
