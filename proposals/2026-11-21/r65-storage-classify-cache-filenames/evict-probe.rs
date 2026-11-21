#[test]
fn r65_count_real_names_without_changing_quota_results() {
    let baseline = std::env::var_os("R65_PRIVATE_CACHE_VIEW").expect("R65_PRIVATE_CACHE_VIEW");
    let baseline = PathBuf::from(baseline);
    let manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(baseline.with_file_name("baseline-view.json")).unwrap())
        .unwrap();
    let docs=manifest["documents"].as_object().unwrap();
    assert_eq!(docs.len(),320);
    for (name,hash) in docs {
        assert_eq!(crate::io::sha256_hex(&fs::read(baseline.join(name)).unwrap()), hash.as_str().unwrap());
    }
    let original = |old, dir:&Path, keep:&Path| {
        if old {legacy_evict(dir,keep)} else {evict(dir,keep)}
    };
    let mut stats=[vec![],vec![]];
    for old in [true,false,false,true] {
        let dir = tempfile::tempdir().unwrap();
        for name in ["journal.jsonl","identity.json","writer.lock"] {
            File::create(dir.path().join(name)).unwrap();
        }
        let mut sum = [0_u64;7];
        for name in docs.keys() {
            let target=dir.path().join(name);
            fs::copy(baseline.join(name),&target).unwrap();
            let (out,counts)=crate::r65_probe::count_scope(|| original(old,dir.path(),&target));
            out.unwrap();
            for (a,b) in sum.iter_mut().zip(counts) {*a+=b;}
        }
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(),323);
        for (name,hash) in docs {
            assert_eq!(crate::io::sha256_hex(&fs::read(dir.path().join(name)).unwrap()),hash.as_str().unwrap());
        }
        assert_eq!(sum[0],52320);
        assert_eq!(sum[1], 4326080);
        assert_eq!(sum[2],if old {sum[1]} else{0});
        assert_eq!(sum[3],if old {51360} else{320});
        assert_eq!(sum[4],51360);
        println!("R65 old={old} names={} name_bytes={} lossy_input_bytes={} basename_evaluations={} stat_calls={} allocs={} alloc_requested={}",
            sum[0],sum[1],sum[2],sum[3],sum[4],sum[5],sum[6]);
        stats[usize::from(old)].push(sum);
    }
    assert_eq!(stats[0].len(),2);
    assert_eq!(stats[1].len(),2);
    for (old,new) in stats[1].iter().zip(&stats[0]) {
        assert_eq!(old[5..],new[5..],"standard ASCII names do not allocate a lossy string");
    }

    // Real native comparison on separate owned sparse quota folders: protection
    // and oldest victim are the same, including an ordinary retired directory.
    let large=1024*1024;
    for old in [true,false] {
        let inside=tempfile::tempdir().unwrap();
        let past=inside.path().join("retired");
        fs::create_dir(&past).unwrap();
        let keep=OsStr::new(".storage-cache-keep.json");
        let first=OsStr::new(".storage-cache-first.json");
        let second=OsStr::new(".storage-cache-second.json");
        size_and_age(&past,keep,16*large,100);
        size_and_age(&past,first,64*large,200);
        size_and_age(&past,second,64*large,300);
        original(old,&past,&past.join(keep)).unwrap();
        assert!(!past.join(first).exists()&&past.join(keep).exists()&&past.join(second).exists());
        // Ordinary owner cleanup of a test-only directory; renamed filesystem
        // entry is no longer the path passed to the cache operation.
        fs::rename(&past,inside.path().join("moved")).unwrap();
        let e=original(old,&past,&past.join(keep)).unwrap_err();
        assert_eq!(e.downcast_ref::<std::io::Error>().unwrap().kind(),std::io::ErrorKind::NotFound);
    }

    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStringExt;
        let dir=tempfile::tempdir().unwrap();
        for name in [b".storage-cache-caf\xe9.json".as_slice(),b"caf\xe9.bin".as_slice()] {
            File::create(dir.path().join(OsString::from_vec(name.to_vec()))).unwrap();
        }
        let keep=dir.path().join(".storage-cache-café.json");
        let a=crate::r65_probe::count_scope(|| original(true,dir.path(),&keep));
        let b=crate::r65_probe::count_scope(|| original(false,dir.path(),&keep));
        a.0.unwrap();b.0.unwrap();
        assert_eq!(a.1[4],1);
        assert_eq!(a.1[4],b.1[4]);
        assert!(a.1[5]>b.1[5]&&a.1[6]>b.1[6]);
        println!("R65 unix_legacy_file_control old={:?} new={:?}",a.1,b.1);
    }
}
