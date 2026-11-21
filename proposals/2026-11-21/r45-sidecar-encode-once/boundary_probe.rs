// Append ONLY to a disposable copy of .../service/catalog/durable.rs.
#[cfg(test)]
#[test]
fn r45_exact_boundary_publication_preserves_prior_generation() {
    for kind in crate::tests::backends() {
        let mut f = crate::tests::Fixture::new(kind);
        f.append(vec![crate::tests::text("small")]);
        let dir = f.descriptor.local_path.as_ref().unwrap();
        f.service.catalog_summary(dir, false).unwrap();
        let side = dir.join(FILE);
        let env: Envelope = serde_json::from_slice(&std::fs::read(&side).unwrap()).unwrap();
        let index = env.data;
        let desc = index.summary.descriptor.clone();
        let (mut summary, prefix) = load(dir, &desc, &index.stamps).unwrap();
        summary.preview = Some(String::new());
        // Get padding from the independent, original typed Serde format.
        let oracle = |summary: &StorageSessionSummary| {
            let data = Index {
                summary: summary.clone(), stamps: index.stamps.clone(), blobs: index.blobs.clone(),
                revision: index.revision, extent: index.extent, fingerprint: index.fingerprint.clone(),
            };
            let checksum = crate::io::sha256_hex(&serde_json::to_vec(&data).unwrap());
            serde_json::to_vec(&Envelope { checksum, data }).unwrap()
        };
        let pad = MAX_BYTES - oracle(&summary).len();
        summary.preview = Some("x".repeat(pad));
        let exact = oracle(&summary); assert_eq!(exact.len(), 4_194_304);
        save(dir, &summary, &prefix, index.blobs.clone());
        assert!(std::fs::read(&side).unwrap()==exact);
        assert_eq!(load(dir, &desc, &index.stamps).unwrap().0, summary);
        let before=std::fs::metadata(&side).unwrap();
        summary.preview.as_mut().unwrap().push('x');
        assert_eq!(oracle(&summary).len(), 4_194_305);
        save(dir, &summary, &prefix, index.blobs.clone());
        assert!(std::fs::read(&side).unwrap()==exact);
        let same_file=std::fs::metadata(&side).unwrap();
        assert!(file_stamp(&before).unwrap()==file_stamp(&same_file).unwrap());
        assert!(std::fs::read_dir(dir).unwrap().flatten().all(|e| {
            let n=e.file_name();let n=n.to_string_lossy();
            !(n.starts_with(".storage-catalog-") && n.ends_with(".tmp"))}));
    }
}
