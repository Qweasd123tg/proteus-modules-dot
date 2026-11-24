fn model(store: &RemoteSessionStore, messages: Vec<CanonicalMessage>) -> SessionReadModel {
    let n = messages.len();
    SessionReadModel {
        summary: AppSessionSummary::new(
            store.session_dir().to_owned(),
            store.session_id(),
            store.workspace_path().unwrap(),
            n,
            None,
            None,
        ),
        conversation: ConversationSnapshot {
            revision: 2,
            messages,
            model_context: vec![],
        },
        transcript: (0..n).map(transcript).collect(),
        usage: SessionUsageSnapshot {
            session_id: store.session_id(),
            revision: 2,
            latest_turn_id: None,
            requests: vec![],
        },
        prefix: None,
    }
}
fn seed(path: &str, n: usize) -> CacheFixture {
    let dummy = Rc::new(Service::new(Response::Done, vec![], false));
    let store = RemoteSessionStore(Rc::new(Opened::new(path.into(), Attempt::Cold(n), dummy)));
    let m = model(&store, (0..n).map(canonical).collect());
    assert_eq!(
        save_model(
            &store,
            &RemoteCacheSource {
                snapshot: snapshot()
            },
            &m,
            None
        ),
        Some(())
    );
    let (s, v) = load_saved_view(&store).unwrap();
    assert_eq!(s.snapshot, snapshot());
    assert_eq!(v.summary.message_count, n);
    CacheFixture {
        path: path.into(),
        docs: std::mem::take(&mut *store.writes.borrow_mut()),
    }
}
type Observations = Vec<(String, Vec<u8>)>;
fn run(
    label: &str,
    svc: Service,
    want: &[&[u8]],
    expected: Option<(&[u8], usize, bool)>,
    err: Option<&str>,
    out: &mut Observations,
) {
    let svc = Rc::new(svc);
    let cfg = Path::new("/cfg");
    let cwd = Path::new("/work");
    let res = prepared::prepare_latest_workspace_session(svc.clone(), cfg, cwd);
    let got: Vec<_> = svc
        .events
        .borrow()
        .iter()
        .filter(|e| e.0 == "open")
        .map(|e| e.1.clone())
        .collect();
    assert_eq!(got, want, "attempt order: {label}");
    assert_eq!(svc.opens.get(), want.len());
    assert_eq!(
        svc.events.borrow()[0],
        Event(
            "list-candidates".into(),
            encode(&Request::ListCandidates {
                config_root: cfg.to_owned(),
                workspace_path: Some(cwd.to_owned())
            })
        )
    );
    let returned = match (res, expected, err) {
        (Ok(Some(prepared)), Some((path, n, was_cached)), None) => {
            assert_eq!(prepared.session_dir().as_os_str().as_bytes(), path);
            assert_eq!(prepared.message_count(), n);
            let (slot, v, source) = prepared
                .into_display_view(|r| Ok(std::mem::take(r)))
                .unwrap();
            assert_eq!(slot.session_dir().as_os_str().as_bytes(), path);
            assert_eq!(v.summary.message_count, n);
            assert_eq!(v.transcript.len(), n.min(PAGE_ROWS));
            assert_eq!(source.is_some(), was_cached);
            if !was_cached {
                assert!(slot.writes.borrow().contains_key(HEAD));
                assert!(v.cursor.is_some());
            }
            encode(&(v.revision, v.transcript, v.cursor, was_cached))
        }
        (Ok(None), None, None) => vec![],
        (Err(e), None, Some(want)) => {
            assert_eq!(e.to_string(), want);
            encode(&want)
        }
        _ => panic!("selection assertion failed: {label}"),
    };
    let bytes = encode(&(&*svc.events.borrow(), returned));
    out.push((label.into(), bytes));
}
fn row(i: usize, ts: i64, path: Option<&str>, child: bool) -> StorageSessionDescriptor {
    descriptor(i, ts, path.map(PathBuf::from), child, 4, 15, 40)
}
fn response(sessions: Vec<StorageSessionDescriptor>, plans: Vec<Attempt>) -> Service {
    Service::new(Response::Candidates { sessions }, plans, true)
}
fn edges(out: &mut Observations) {
    run("empty", response(vec![], vec![]), &[], None, None, out);
    run(
        "root-none-and-child",
        response(
            vec![row(1, 9, Some("/other"), true), row(2, 8, None, false)],
            vec![],
        ),
        &[],
        None,
        None,
        out,
    );
    run(
        "single-cold",
        response(vec![row(1, 9, Some("/one"), false)], vec![Attempt::Cold(1)]),
        &[b"/one"],
        Some((b"/one", 1, false)),
        None,
        out,
    );
    let mut err = response(vec![], vec![]);
    err.error = true;
    run(
        "transport-error",
        err,
        &[],
        None,
        Some("injected catalog transport failure"),
        out,
    );
    run(
        "unexpected-response",
        Service::new(Response::Done, vec![], true),
        &[],
        None,
        Some("storage returned an unexpected candidate response"),
        out,
    );
    let mut err = response(vec![], vec![]);
    err.wire = b"unknown".to_vec();
    run(
        "parse-error",
        err,
        &[],
        None,
        Some("expected value at line 1 column 1"),
        out,
    );
    let variants = vec![
        row(1, 20, Some("/s/a"), false),
        row(2, 25, Some("/placeholder-first"), false),
        row(3, 20, Some("/s//a/"), false),
        row(4, 20, Some("/s/a"), false),
        row(5, i64::MIN, Some("/should-not-open"), false),
        row(6, 25, Some("/placeholder-second"), false),
        row(7, i64::MAX, None, false),
        row(8, i64::MAX, Some("/child"), true),
    ];
    let mut svc = response(
        variants,
        vec![
            Attempt::Error,
            Attempt::ValidateError,
            Attempt::Cold(0),
            Attempt::Error,
            Attempt::Cold(1),
        ],
    );
    svc.raw = vec![
        (1, vec![b'/', b's', b'/', 0xFE]),
        (5, vec![b'/', b's', b'/', 0xFF]),
    ];
    run(
        "raw-nonutf-tie-stability-duplicate",
        svc,
        &[b"/s/\xff", b"/s/\xfe", b"/s/a", b"/s//a/", b"/s/a"],
        Some((b"/s/a", 1, false)),
        None,
        out,
    );
    let list = |paths: &[&str]| {
        paths
            .iter()
            .enumerate()
            .map(|(i, p)| row(i, 100 - i as i64, Some(p), false))
            .collect()
    };
    let mut warm = response(
        list(&["/error", "/warm", "/later"]),
        vec![Attempt::Error, Attempt::Warm(3)],
    );
    warm.cache = seed("/warm", 3);
    run(
        "warm-after-open-error",
        warm,
        &[b"/error", b"/warm"],
        Some((b"/warm", 3, true)),
        None,
        out,
    );
    let mut blank = response(list(&["/blank", "/later"]), vec![Attempt::EmptyCache(2)]);
    blank.cache = seed("/blank", 0);
    run(
        "cached-empty-observes-append",
        blank,
        &[b"/blank"],
        Some((b"/blank", 2, false)),
        None,
        out,
    );
    let mut blank = response(
        list(&["/blank", "/later"]),
        vec![Attempt::EmptyCache(0), Attempt::Cold(2)],
    );
    blank.cache = seed("/blank", 0);
    run(
        "cached-empty-then-fallback",
        blank,
        &[b"/blank", b"/later"],
        Some((b"/later", 2, false)),
        None,
        out,
    );
    run(
        "all-empty-failed",
        response(
            list(&["/first", "/second", "/third"]),
            vec![Attempt::ValidateError, Attempt::Error, Attempt::Cold(0)],
        ),
        &[b"/first", b"/second", b"/third"],
        None,
        None,
        out,
    );
}
fn scale(out: &mut Observations) {
    for n in [31usize, 32, 33, 128] {
        for order in ["ordered", "reverse", "mixed-order"] {
            let mut rows = (0..n)
                .map(|i| row(i, 1, Some(&format!("/s/{:03}", n - i)), false))
                .collect::<Vec<_>>();
            match order {
                "reverse" => rows.reverse(),
                "mixed-order" => {
                    rows.rotate_left(n / 3);
                    rows[0].parent_session_id = Some(Uuid::nil());
                    rows[1].local_path = None;
                }
                _ => (),
            }
            let mut expected: Vec<_> = rows
                .iter()
                .filter(|r| r.parent_session_id.is_none())
                .filter_map(|r| r.local_path.as_ref())
                .map(|p| p.as_os_str().as_bytes())
                .collect();
            expected.sort_by(|a, b| b.cmp(a));
            let mut p = vec![Attempt::Cold(0); expected.len()];
            *p.last_mut().unwrap() = Attempt::Cold(1);
            run(
                &format!("{n}:{order}"),
                response(rows.clone(), p),
                &expected,
                Some((expected.last().unwrap(), 1, false)),
                None,
                out,
            );
        }
    }
}
fn providers(out: &mut Observations) {
    for backend in ["jsonl", "sqlite"] {
        for order in ["distinct", "aligned", "tied-opaque-opposes-path"] {
            let mut rows=(0..128usize).map(|i|{
               let path=PathBuf::from(format!("/cfg/{backend}/sessions/fixture/project/{i:010}"));
               let mut d=descriptor(i,if order=="distinct"{i as i64}else{86},Some(path),false,87,30,48);
               d.session.key=if order=="tied-opaque-opposes-path"{
                   format!("{backend}-opaque-{:03}",128-i)
               }else{
                   format!(r#"{{"version":1,"path":"{}","workspace":"/work","parent_session_id":null}}"#,d.local_path.as_ref().unwrap().display())
               };
               d
            }).collect::<Vec<_>>();
            // Source-derived provider order (same comparator for both backends), not a capture.
            rows.sort_by(|a, b| {
                b.updated_at_ms
                    .cmp(&a.updated_at_ms)
                    .then_with(|| b.session.key.cmp(&a.session.key))
            });
            let expected = (0..4usize)
                .map(|i| format!("/cfg/{backend}/sessions/fixture/project/{:010}", 127 - i))
                .collect::<Vec<_>>();
            let want = expected.iter().map(|s| s.as_bytes()).collect::<Vec<_>>();
            run(
                &format!("provider-shape:{backend}:{order}"),
                response(
                    rows,
                    vec![
                        Attempt::Cold(0),
                        Attempt::Cold(0),
                        Attempt::Cold(0),
                        Attempt::Cold(1),
                    ],
                ),
                &want,
                Some((want[3], 1, false)),
                None,
                out,
            );
        }
    }
}
pub(super) fn semantics() -> Observations {
    let mut r = vec![];
    edges(&mut r);
    scale(&mut r);
    providers(&mut r);
    r
}
pub(super) fn alloc(s: Rc<Service>) -> (usize, meter::Stats) {
    let (_, stats) = meter::scope(|| {
        let p = prepared::prepare_latest_workspace_session(
            s.clone(),
            Path::new("/cfg"),
            Path::new("/work"),
        )
        .unwrap();
        if let Some(p) = &p {
            assert_eq!(p.message_count(), 1)
        }
        drop(std::hint::black_box(p));
    });
    (s.opens.get(), stats)
}
