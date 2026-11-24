fn with_source(s: &RemoteSessionStore) -> RemoteCacheSource {
    RemoteCacheSource {
        snapshot: s.snap.clone(),
    }
}
type Index = BTreeMap<String, String>;
fn update(s: &RemoteSessionStore, m: &mut Index, rows: &[AppTranscriptMessage]) -> Option<()> {
    update_tools(s, &with_source(s), m, rows)
}
fn policy_cases(rec: &mut Ledger) {
    let s = RemoteSessionStore::new(true);
    let mut m = Index::new();
    let mut rows = vec![
        plain(1),
        row("read", 2, "failed", json!(1), None),
        row("read", 3, "denied", json!(2), None),
    ];
    assert!(update(&s, &mut m, &rows).is_some() && s.kinds().is_empty() && m.is_empty());
    rec.take("ignored", &s, &m, &());
    rows = vec![
        row("read", 4, "", nested(32), None),
        row("write", 5, "FAILED", json!(null), Some(Value::Null)),
        row("read", 6, "complete", json!([0, false]), Some(nested(57))),
        row("read", 7, "denied", json!(22), None),
        row("read", 8, "failed", json!(23), None),
    ];
    let input = encoded(&rows);
    let (a, va) = expected(&rows[0]);
    let (b, vb) = expected(&rows[1]);
    let (c, vc) = expected(&rows[2]);
    assert!(update(&s, &mut m, &rows).is_some());
    assert_eq!(s.kinds(), "RWRWRW");
    assert_eq!(
        m,
        Index::from([("read".into(), c.clone()), ("write".into(), b.clone())])
    );
    assert_eq!(input, encoded(&rows));
    for (key, v) in [(&a, &va), (&b, &vb), (&c, &vc)] {
        let docs = s.docs.borrow();
        let object = &docs[&format!("display-data-{key}")];
        assert_eq!(encoded(object), encoded(v));
        assert_eq!(object.as_object().unwrap().len(), 5);
        assert!(
            object.get("effective_args").is_some()
                && object.get("metadata").is_none()
                && object.get("result").is_none()
                && object.get("terminal").is_none()
        );
        if cfg!(feature = "preserve_order") {
            assert_eq!(
                object
                    .as_object()
                    .unwrap()
                    .keys()
                    .map(String::as_str)
                    .collect::<Vec<_>>(),
                ["call_id", "name", "status", "args", "effective_args"]
            );
        }
    }
    rec.take("typed", &s, &m, &());
    s.reset();
    assert!(update(&s, &mut m, &rows).is_some());
    assert_eq!(s.kinds(), "RRR");
    rec.take("hit", &s, &m, &());
    for (kind, mode) in [('R', 'e'), ('R', 'd'), ('W', 'e'), ('W', 'n'), ('W', 'd')] {
        let t = RemoteSessionStore::new(true);
        let mut m = Index::new();
        t.fail(kind, &format!("display-data-{c}"), mode);
        let ok = update(&t, &mut m, &rows);
        if kind == 'W' {
            assert!(ok.is_none());
            assert_eq!(m["read"], a);
            assert!(!t.docs.borrow().contains_key(&format!("display-data-{c}")));
        } else {
            assert!(ok.is_some());
            assert_eq!(m["read"], c);
        }
        assert_eq!(t.kinds(), "RWRWRW");
        assert_eq!(m["write"], b);
        rec.take(&format!("failure-{kind}{mode}"), &t, &m, &ok);
    }
    s.reset();
    s.docs
        .borrow_mut()
        .insert(format!("display-data-{a}"), json!({"corrupted":true}));
    assert!(update(&s, &mut m, &rows[..1]).is_some());
    assert_eq!(s.kinds(), "RW");
    assert_eq!(m["read"], a);
    assert_eq!(
        encoded(&s.docs.borrow()[&format!("display-data-{a}")]),
        encoded(&va)
    );
    rec.take("corrupt rewrite", &s, &m, &());
    // Bound is checked after all accepted rows; neither backend writes nor map changes are rolled back.
    let t = RemoteSessionStore::new(true);
    let mut m = (0..16_383)
        .map(|i| (format!("pre-{i}"), String::from("retained")))
        .collect::<Index>();
    assert!(update(&t, &mut m, &rows[..1]).is_some());
    assert_eq!(m.len(), 16_384);
    assert!(update(&t, &mut m, &rows[2..3]).is_some());
    assert_eq!(m.len(), 16_384);
    let ok = update(&t, &mut m, &rows[1..]);
    assert!(ok.is_none());
    assert_eq!(t.kinds(), "RWRWRWR");
    assert_eq!(m.len(), 16_385);
    assert_eq!(m["read"], c);
    assert!(update(&t, &mut m, &[]).is_none());
    rec.take("postwrite cap", &t, &m, &ok);
}
fn cold_model(s: &RemoteSessionStore, rows: Vec<AppTranscriptMessage>) -> SessionReadModel {
    SessionReadModel {
        summary: AppSessionSummary::new(
            s.session_dir().into(),
            s.session_id(),
            s.descriptor.workspace_path.clone(),
            0,
            None,
            None,
        ),
        transcript: rows,
        usage: SessionUsageSnapshot {
            session_id: s.session_id(),
            revision: 2,
            latest_turn_id: None,
            requests: vec![],
        },
        conversation: ConversationSnapshot {
            revision: 2,
            messages: vec![],
            model_context: vec![],
        },
        prefix: None,
    }
}
fn saved(s: &RemoteSessionStore) -> Header {
    let h = header(s).unwrap();
    s.reset();
    h
}
fn archive(rec: &mut Ledger) {
    let s = RemoteSessionStore::new(true);
    let mut rows = (0..151).map(plain).collect::<Vec<_>>();
    rows[1] = row("read", 1, "working", json!([false]), None);
    rows[55] = row("write", 55, "arbitrary", json!(false), Some(Value::Null));
    rows[99] = row("read", 99, "completed", nested(57), Some(nested(19)));
    rows[120] = row("read", 120, "failed", json!(1), None);
    rows[150] = row("read", 150, "denied", json!(2), None);
    let (read, want) = expected(&rows[99]);
    let (write, _) = expected(&rows[55]);
    let m = Index::from([("read".into(), read.clone()), ("write".into(), write)]);
    let model = cold_model(&s, rows);
    let snap = with_source(&s);
    let cursor = RemoteJournalCursor {
        snapshot: snap.snapshot.clone(),
    };
    assert!(save_model(&s, &snap, &model, Some(&cursor)).is_some());
    assert_eq!(
        s.ops.borrow().last().map(|op| (op.kind, op.key.as_str())),
        Some(('W', HEAD))
    );
    rec.take("cold ops and stored bytes", &s, &m, &());
    let h = saved(&s);
    assert_eq!(h.tools, m);
    let section = serde_json::to_value(&h.transcript).unwrap();
    assert!(section["packs"].as_array().unwrap().len() >= 1);
    rec.take("cold saved bytes", &s, &m, &());
    let docs = s.docs.borrow().clone();
    let rev = snap.revision().unwrap();
    for name in ["absent", "write", "read"] {
        s.reset();
        let r = tool_state(&s, name).unwrap();
        assert_eq!(r.revision, rev);
        match name {
            "absent" => {
                assert!(r.tool.is_none());
                assert_eq!(s.kinds(), "RSS");
            }
            "write" => {
                assert!(r.tool.as_ref().unwrap().effective_args.is_none());
                assert_eq!(s.kinds(), "RSRS");
            }
            _ => {
                assert_eq!(
                    encoded(&r.tool.as_ref().unwrap()),
                    encoded(&serde_json::from_value::<AppToolState>(want.clone()).unwrap())
                );
                assert_eq!(s.kinds(), "RSRS");
            }
        }
        rec.take(&format!("direct-{name}"), &s, &m, &r);
    }
    let k = format!("display-data-{read}");
    let reset = || {
        *s.docs.borrow_mut() = docs.clone();
        s.reset();
    };
    for case in [
        "missing",
        "corrupt",
        "read-error",
        "publish-error",
        "publish-head",
        "stale",
        "page-failure",
        "write-failure",
        "malformed",
        "wrong-name",
        "denied",
        "failed",
        "extra-key",
        "missing-effective",
    ] {
        reset();
        match case {
            "corrupt" => {
                s.docs
                    .borrow_mut()
                    .insert(k.clone(), json!({"bad hash":42}));
            }
            "read-error" => s.fail('R', &k, 'e'),
            "wrong-name" | "denied" | "failed" | "malformed" | "extra-key"
            | "missing-effective" => {
                let mut doc = want.clone();
                match case {
                    "wrong-name" => doc["name"] = json!("not read"),
                    "denied" | "failed" => doc["status"] = json!(case),
                    "malformed" => doc["args"] = json!(0),
                    "extra-key" => doc["unused"] = json!(true),
                    "missing-effective" => {
                        doc.as_object_mut().unwrap().remove("effective_args");
                    }
                    _ => unreachable!(),
                };
                if case == "malformed" {
                    doc.as_object_mut().unwrap().remove("status");
                }
                let d = hash(&doc).unwrap();
                let mut local = h.clone();
                local.tools.insert("read".into(), d.clone());
                let mut ds = s.docs.borrow_mut();
                ds.insert(format!("display-data-{d}"), doc);
                ds.insert(HEAD.into(), serde_json::to_value(local).unwrap());
            }
            _ => {
                s.docs.borrow_mut().remove(&k);
            }
        };
        match case {
            "stale" => s.stale_on.set(Some(2)),
            "page-failure" => s.fail(
                'R',
                &format!(
                    "display-data-{}",
                    section["packs"][0]["hash"].as_str().unwrap()
                ),
                'e',
            ),
            "write-failure" => s.fail('W', &k, 'n'),
            "publish-error" => s.fail('W', &format!("display-revision-{rev}"), 'e'),
            "publish-head" => s.fail('W', HEAD, 'd'),
            _ => (),
        }
        let r = tool_state(&s, "read");
        let kinds = s.kinds();
        match case {
            "wrong-name" | "denied" | "failed" => {
                assert!(r.is_none());
                assert_eq!(kinds, "RSR");
            }
            "stale" | "page-failure" | "write-failure" => {
                assert!(r.is_none());
                if case == "stale" {
                    assert!(kinds.ends_with('S'));
                    assert!(
                        !s.ops
                            .borrow()
                            .iter()
                            .any(|op| op.kind == 'W' && op.key == HEAD)
                    );
                }
            }
            "missing-effective" => {
                assert!(
                    r.as_ref()
                        .unwrap()
                        .tool
                        .as_ref()
                        .unwrap()
                        .effective_args
                        .is_none()
                );
                assert_eq!(kinds, "RSRS");
            }
            _ => {
                let state = r.as_ref().unwrap().tool.as_ref().unwrap();
                assert_eq!(serde_json::to_value(state).unwrap(), want);
                assert_eq!(r.as_ref().unwrap().revision, rev);
                assert!(s.ops.borrow().iter().any(|op| op.key
                    == format!(
                        "display-data-{}",
                        section["packs"][0]["hash"].as_str().unwrap()
                    )));
            }
        }
        rec.take(&format!("rebuild-{case}"), &s, &m, &r);
    }
    reset();
    let mut next = h.clone();
    let suffix = [
        row("read", 190, "ready", json!(501), None),
        row("read", 191, "denied", json!(0), None),
    ];
    next.transcript = pages::append_section(&s, &snap, &next.transcript, &suffix).unwrap();
    assert!(update_tools(&s, &snap, &mut next.tools, &suffix).is_some());
    assert!(publish(&s, &next).is_some());
    assert_eq!(next.tools["read"], expected(&suffix[0]).0);
    assert_eq!(next.tools["write"], m["write"]);
    let r = tool_state(&s, "read").unwrap();
    assert_eq!(r.tool.as_ref().unwrap().args, json!(501));
    rec.take("existing header plus suffix", &s, &next.tools, &r);
}
fn cold_reachable(rec: &mut Ledger) {
    let s = RemoteSessionStore::new(false);
    let rows = vec![row(
        "big",
        6,
        "running",
        nested(1 << 20),
        Some(nested(2 << 20)),
    )];
    let (digest_key, expected_value) = expected(&rows[0]);
    let original = encoded(&rows);
    let model = cold_model(&s, rows);
    assert!(save_model(&s, &with_source(&s), &model, None).is_some());
    let h = header(&s).unwrap();
    assert_eq!(h.transcript.rows, 1);
    assert_eq!(h.tools["big"], digest_key);
    assert_eq!(
        encoded(&s.docs.borrow()[&format!("display-data-{digest_key}")]),
        encoded(&expected_value)
    );
    assert_eq!(encoded(&model.transcript), original);
    let actual = tool_state(&s, "big").unwrap().tool.unwrap();
    assert_eq!(
        encoded(&serde_json::to_value(actual).unwrap()),
        encoded(&expected_value)
    );
    let contents = s
        .docs
        .borrow()
        .iter()
        .map(|(k, v)| (k.clone(), digest(&encoded(v))))
        .collect::<BTreeMap<_, _>>();
    rec.0.push((
        "3 MiB cold save and lookup".into(),
        encoded(&(&*s.ops.borrow(), contents, h.tools)),
    ));
}
fn big(rec: &mut Ledger) {
    let mut rr = row("big", 0, "", Value::String(String::new()), None);
    let base = core::session_store::json_size::encoded_len(
        &AppToolState::from(rr.tool.as_ref().unwrap()),
        SESSION_STORAGE_MAX_CACHE_BYTES,
    )
    .unwrap();
    for delta in [0, 1] {
        let s = RemoteSessionStore::new(false);
        let mut m = Index::new();
        let n = SESSION_STORAGE_MAX_CACHE_BYTES - base + delta;
        rr.tool.as_mut().unwrap().args = Value::String("a".repeat(n));
        let ok = update(&s, &mut m, std::slice::from_ref(&rr));
        if delta == 0 {
            assert!(ok.is_some());
            assert_eq!(s.kinds(), "RW");
            let ds = s.docs.borrow();
            let v = &ds[&format!("display-data-{}", m["big"])];
            assert_eq!(v["args"], rr.tool.as_ref().unwrap().args);
            assert_eq!(
                core::session_store::json_size::encoded_len(v, SESSION_STORAGE_MAX_CACHE_BYTES),
                Some(SESSION_STORAGE_MAX_CACHE_BYTES)
            );
        } else {
            assert!(
                ok.is_none() && m.is_empty() && s.kinds().is_empty() && s.docs.borrow().is_empty()
            );
        }
        rec.0
            .push((format!("hard cap +{delta}"), encoded(&(ok, m, s.kinds()))));
    }
    let r = row("big", 2, "ok", nested(1 << 20), Some(nested(2 << 20)));
    let s = RemoteSessionStore::new(false);
    let mut m = Index::new();
    let want = expected(&r);
    let orig = encoded(&r);
    assert!(update(&s, &mut m, std::slice::from_ref(&r)).is_some());
    assert_eq!(m["big"], want.0);
    assert_eq!(
        encoded(&s.docs.borrow()[&format!("display-data-{}", want.0)]),
        encoded(&want.1)
    );
    assert_eq!(encoded(&r), orig);
    rec.0.push((
        "3 MiB nested".into(),
        encoded(&(m, s.kinds(), digest(&orig))),
    ));
}
pub(super) fn run() -> Ledger {
    let mut r = Ledger::default();
    policy_cases(&mut r);
    archive(&mut r);
    big(&mut r);
    cold_reachable(&mut r);
    r
}
pub(super) fn cost(rows: &[AppTranscriptMessage]) -> meter::Stats {
    let s = RemoteSessionStore::new(false);
    let src = with_source(&s);
    // All mutated stores/indices/logs start empty. Release them INSIDE the meter.
    let (_, v) = meter::scope(|| {
        let mut m = Index::new();
        std::hint::black_box(update_tools(&s, &src, &mut m, rows));
        drop(m);
        drop(std::mem::take(&mut *s.docs.borrow_mut()));
        drop(std::mem::take(&mut *s.ops.borrow_mut()));
    });
    v
}

pub(super) fn cold_cost(rows: Vec<AppTranscriptMessage>) -> meter::Stats {
    let s = RemoteSessionStore::new(false);
    let model = cold_model(&s, rows);
    let src = with_source(&s);
    let (_, v) = meter::scope(|| {
        assert!(std::hint::black_box(save_model(&s, &src, &model, None)).is_some());
        drop(std::mem::take(&mut *s.docs.borrow_mut()));
        drop(std::mem::take(&mut *s.ops.borrow_mut()));
    });
    v
}
