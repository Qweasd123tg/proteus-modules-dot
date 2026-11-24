fn observe_header(h: &Header) {
    if !meter::collecting() {
        return;
    }
    pages::observe(&h.conversation, 0);
    pages::observe(&h.context, 0);
    pages::observe(&h.transcript, 1);
    for (k, v) in &h.tools {
        meter::string(k, 0);
        meter::string(v, 0)
    }
    if let Some(p) = &h.summary.preview {
        meter::string(p, 0)
    }
    if let Some(p) = &h.prefix {
        meter::string(p, 0)
    }
    if let Some(c) = &h.cursor {
        meter::string(&c.snapshot.session.key, 0);
        meter::string(&c.snapshot.snapshot_id, 0);
        meter::string(&c.snapshot.content_sha256, 0);
    }
    meter::string(&h.source.snapshot.session.key, 1);
    meter::string(&h.source.snapshot.snapshot_id, 1);
    meter::string(&h.source.snapshot.content_sha256, 1);
    meter::seal()
}
fn model(store: &RemoteSessionStore, count: usize, change: Option<usize>) -> SessionReadModel {
    let mut transcript: Vec<_> = (0..count)
        .map(|i| {
            let mut r = plain(i);
            r.text = format!("fixture {i}");
            r
        })
        .collect();
    transcript[1] = row("old-tool", 1, "done", json!({"z":2,"a":3}), None);
    if let Some(i) = change {
        transcript[i] = row(
            "new-tool",
            i,
            "done",
            json!({"z":[2],"a":3}),
            Some(json!({})),
        )
    }
    let messages = (0..count)
        .map(|i| CanonicalMessage {
            id: Uuid::from_u128(i as u128),
            role: MessageRole::User,
            phase: None,
            parts: vec![CanonicalPart {
                part_id: Uuid::from_u128(i as u128 + 100_000),
                provenance: PartProvenance::User,
                scope: PartScope::Conversation,
                payload: ContentPart::Text {
                    text: format!("fixture {i}"),
                },
            }],
            name: None,
            tool_call_id: None,
            metadata: Value::Null,
        })
        .collect();
    let rev = store.snap.revision.history_revision;
    let ctx = (0..count)
        .map(|i| ModelContextObservation::Usage {
            total_tokens: i as u64,
            last_tokens: 12,
        })
        .collect();
    let mut prefix = PrefixIdentities::default();
    prefix.history = vec![[rev as u8; 32]];
    SessionReadModel {
        summary: AppSessionSummary::new(
            store.session_dir().into(),
            store.session_id(),
            store.workspace_path().unwrap(),
            count,
            None,
            Some("visible preview".into()),
        ),
        conversation: ConversationSnapshot {
            revision: rev,
            messages,
            model_context: ctx,
        },
        transcript,
        usage: SessionUsageSnapshot {
            session_id: store.session_id(),
            revision: rev,
            latest_turn_id: None,
            requests: vec![],
        },
        prefix: Some(prefix),
    }
}
fn source(s: &RemoteSessionStore) -> RemoteCacheSource {
    RemoteCacheSource {
        snapshot: s.snap.clone(),
    }
}
fn new(capture: bool) -> RemoteSessionStore {
    RemoteSessionStore(std::rc::Rc::new(MemoryStore::new(capture)))
}
fn seed(s: &RemoteSessionStore, n: usize) -> Header {
    let m = model(s, n, None);
    let src = source(s);
    let c = RemoteJournalCursor {
        snapshot: s.snap.clone(),
    };
    assert_eq!(save_model(s, &src, &m, Some(&c)), Some(()));
    let h = header(s).unwrap();
    assert!(h.prefix.is_some());
    for v in [&h.conversation, &h.transcript, &h.context] {
        assert_eq!(v.rows, n);
        assert!(valid_section(v))
    }
    assert!(
        serde_json::to_value(&h.transcript).unwrap()["packs"]
            .as_array()
            .is_some_and(|p| !p.is_empty())
    );
    s.reset();
    h
}
fn advance(s: &mut RemoteSessionStore) {
    let inner = std::rc::Rc::get_mut(&mut s.0).unwrap();
    inner.snap.revision.history_revision += 1;
    inner.snap.revision.session_seq += 1;
    inner.snap.content_sha256 = "b".repeat(64);
    inner.snap.snapshot_id = "new immutable".into();
}
fn tail(h: &Header) -> String {
    format!("display-data-{}", h.transcript.pages.last().unwrap().hash)
}
fn named(src: &RemoteCacheSource) -> String {
    format!("display-revision-{}", src.revision().unwrap())
}
fn count(s: &RemoteSessionStore, k: char, key: &str) -> usize {
    s.ops
        .borrow()
        .iter()
        .filter(|o| o.kind == k && o.key == key)
        .count()
}
fn viewbytes(v: &SessionReadView) -> Vec<u8> {
    encoded(&(&v.summary, v.revision, &v.usage, &v.transcript, &v.cursor))
}
fn observation(label: &str, s: &RemoteSessionStore, result: &impl Serialize, r: &mut Ledger) {
    // Incremental length-framed transcript of every exact wire request and final stored value.
    // Keep original raw ordered bytes for equality across implementations (not digest-only).
    let mut bytes = vec![];
    let mut put = |v: &[u8]| {
        bytes.extend((v.len() as u64).to_le_bytes());
        bytes.extend(v)
    };
    for op in s.ops.borrow().iter() {
        put(&[op.kind as u8]);
        put(op.key.as_bytes());
        put(op.wire.as_ref().unwrap());
        put(op.reply.as_ref().unwrap());
    }
    put(b"final");
    for (k, v) in s.docs.borrow().iter() {
        put(k.as_bytes());
        put(&encoded(v));
    }
    put(&encoded(result));
    r.0.push((label.into(), bytes))
}
fn check_miss(s: &RemoteSessionStore, h: &Header, bad: bool) {
    assert!(header(s).is_some());
    s.reset();
    let val = load_saved_view(s);
    assert_eq!(val.is_none(), bad);
    assert_eq!(count(s, 'R', HEAD), 1);
    assert_eq!(count(s, 'R', &tail(h)), 1);
    assert!(s.ops.borrow().iter().all(|o| o.kind == 'R'));
    s.reset();
}
fn prepare(
    s: &RemoteSessionStore,
    m: SessionReadModel,
) -> (SessionReadView, Option<RemoteCacheSource>) {
    *s.staged.borrow_mut() = Some(m);
    let prep = prepared::PreparedSession::from_dir(s.0.clone(), s.session_dir().into()).unwrap();
    let (_, v, c) = prep
        .into_display_view(|snap| Ok(std::mem::take(&mut snap.0)))
        .unwrap();
    (v, c)
}
fn path_case(name: &str, r: &mut Ledger) {
    const N: usize = 200;
    let mut s = new(true);
    let h = seed(&s, N);
    let old = encoded(&s.docs.borrow()[HEAD]);
    let old_named = named(&h.source);
    let leaf = tail(&h);
    if name != "warm" {
        advance(&mut s)
    }
    let mut change = None;
    match name {
        "warm" | "warm-stale" => check_miss(&s, &h, false),
        "no-head" => {
            s.docs.borrow_mut().remove(HEAD);
            assert!(header(&s).is_none());
            s.reset();
        }
        "bad-unselected" => {
            s.docs.borrow_mut().get_mut(HEAD).unwrap()["context"]["rows"] = json!(N + 1);
            assert!(header(&s).is_none());
            assert!(load_saved_view(&s).is_none());
            s.reset();
        }
        _ => {
            if name.starts_with("corrupt") {
                s.docs
                    .borrow_mut()
                    .insert(leaf.clone(), json!({"bad":"hash"}));
            } else {
                s.docs.borrow_mut().remove(&leaf);
            }
            assert_eq!(old, encoded(&s.docs.borrow()[HEAD]));
            check_miss(&s, &h, true);
            if name.ends_with("changed") {
                change = Some(N - 1)
            }
            if name == "changed-earlier" {
                change = Some(11)
            }
        }
    }
    let m = model(&s, N, change);
    let new_src = source(&s);
    let unseen = name.starts_with("warm") || name == "no-head" || name == "bad-unselected";
    if unseen {
        meter::arm()
    }
    let (v, c) = prepare(&s, m);
    if unseen {
        meter::finish_unseen()
    }
    if name.starts_with("warm") {
        assert!(c.is_some() && s.validated.get() == 0);
        assert!(s.staged.borrow().is_some());
        assert!(s.ops.borrow().iter().all(|op| op.kind == 'R'));
        assert_eq!(v.revision, h.revision);
    } else {
        assert!(c.is_none() && s.validated.get() == 1 && s.staged.borrow().is_none());
        assert_eq!(v.revision, new_src.snapshot.revision.history_revision);
        assert_eq!(v.transcript.len(), 50);
        let cur = v.cursor.as_ref().unwrap();
        assert_eq!(cur.revision, new_src.revision().unwrap());
        assert_eq!(cur.before, N - 50);
        let want = match name {
            "missing-same" | "corrupt-same" => Some(N),
            "changed-earlier" => Some(11),
            "missing-changed" | "corrupt-changed" | "bad-unselected" | "no-head" => None,
            _ => panic!("unknown case: {name}"),
        };
        assert_eq!(cur.base.as_ref().map(|b| b.common_prefix), want);
        if let Some(b) = &cur.base {
            assert_eq!(b.revision, h.source.revision().unwrap())
        }
        assert_eq!(count(&s, 'W', HEAD), 1);
        if name.ends_with("same") {
            assert_eq!(count(&s, 'W', &leaf), 1)
        }
        if name.ends_with("changed") {
            assert_eq!(count(&s, 'W', &leaf), 0);
            assert!(count(&s, 'R', &leaf) >= 2)
        }
        assert!(s.docs.borrow().contains_key(&old_named));
        assert_eq!(s.docs.borrow()[HEAD], s.docs.borrow()[&named(&new_src)]);
    }
    observation(name, &s, &(viewbytes(&v), c, s.validated.get()), r);
}
fn errors(name: &str, r: &mut Ledger) {
    const N: usize = 200;
    let mut s = new(true);
    let h = seed(&s, N);
    let old = encoded(&s.docs.borrow()[HEAD]);
    let pre = encoded(&s.docs.borrow()[PREFIX]);
    s.docs.borrow_mut().remove(&tail(&h));
    advance(&mut s);
    let m = model(&s, N, Some(77));
    let src = source(&s);
    let tool = format!("display-data-{}", expected(&m.transcript[77]).0);
    let canonical = serde_json::to_value(&h.transcript).unwrap();
    let pk = format!(
        "display-data-{}",
        canonical["packs"][0]["hash"].as_str().unwrap()
    );
    match name {
        "compare-read-failed" => s.fail('R', &pk, 'e'),
        "tool-write-failed" => s.fail('W', &tool, 'n'),
        "prefix-write-failed" => s.fail('W', PREFIX, 'e'),
        "named-write-failed" => s.fail('W', &named(&src), 'd'),
        "head-write-failed" => s.fail('W', HEAD, 'e'),
        "page-write-failed" => s.fail('W', "*", 'n'),
        _ => unreachable!(),
    }
    let ok = save_model(&s, &src, &m, None);
    assert!(s.fault.borrow().is_none(), "fault not exercised: {name}");
    assert_eq!(
        ok.is_some(),
        name == "prefix-write-failed" || name == "compare-read-failed"
    );
    let d = s.docs.borrow();
    if ok.is_none() {
        assert_eq!(encoded(&d[HEAD]), old)
    }
    let has_named = d.contains_key(&named(&src));
    assert_eq!(has_named, ok.is_some() || name == "head-write-failed");
    assert_eq!(count(&s, 'W', HEAD), usize::from(has_named));
    assert_eq!(
        encoded(&d[PREFIX]) != pre,
        matches!(
            name,
            "compare-read-failed" | "named-write-failed" | "head-write-failed"
        )
    );
    if name == "prefix-write-failed" {
        assert_eq!(d[HEAD]["prefix"], Value::Null)
    }
    if name == "compare-read-failed" {
        assert_eq!(d[HEAD]["base"], Value::Null)
    }
    drop(d);
    observation(name, &s, &ok, r)
}
pub(super) fn run() -> Ledger {
    let mut r = Ledger::default();
    for n in [
        "warm",
        "warm-stale",
        "no-head",
        "bad-unselected",
        "missing-same",
        "corrupt-same",
        "missing-changed",
        "corrupt-changed",
        "changed-earlier",
    ] {
        path_case(n, &mut r)
    }
    for n in [
        "compare-read-failed",
        "page-write-failed",
        "tool-write-failed",
        "prefix-write-failed",
        "named-write-failed",
        "head-write-failed",
    ] {
        errors(n, &mut r)
    }
    r
}
// Scale manifest ownership only: alias real, writer-emitted immutable objects. This is not a replay of 50,000 distinct rows.
fn stretch(s: &RemoteSessionStore, n: usize, h: &mut Header) {
    if n == h.transcript.pages.len() {
        return;
    }
    // For packed sections repeat the first real pack, then fill using an existing singleton;
    // for the unpacked context use the same singleton at every logical position.
    for section in [&mut h.conversation, &mut h.transcript, &mut h.context] {
        let old = serde_json::to_value(&*section).unwrap();
        let mut pages = vec![];
        let mut packs = vec![];
        if let Some(p) = old["packs"].as_array().and_then(|ps| ps.first()) {
            let count = p["count"].as_u64().unwrap() as usize;
            while pages.len() + count < n {
                let mut block = p.clone();
                block["first"] = json!(pages.len());
                packs.push(block);
                pages.extend(old["pages"].as_array().unwrap()[..count].iter().cloned());
            }
        }
        // Fill singleton slots using a real, independently stored original BODY.
        while pages.len() < n {
            pages.push(old["pages"].as_array().unwrap().last().unwrap().clone());
        }
        *section =
            serde_json::from_value(json!({"rows":n*50,"pages":pages,"packs":packs})).unwrap();
        assert!(valid_section(section));
    }
    h.summary.message_count = h.conversation.rows;
    assert!(matches(s, h));
    let v = serde_json::to_value(&*h).unwrap();
    assert!(encoded(&v).len() < SESSION_STORAGE_MAX_CACHE_BYTES);
    s.docs.borrow_mut().insert(HEAD.into(), v);
}
pub(super) fn life(n: usize) -> meter::Report {
    let rows = if n == 100 { n * 50 } else { 200 };
    let mut s = new(false);
    let mut h = seed(&s, rows);
    stretch(&s, n, &mut h);
    let leaf = tail(&h);
    s.docs.borrow_mut().remove(&leaf);
    advance(&mut s);
    check_miss(&s, &h, true);
    drop(h);
    let m = model(&s, rows, Some(rows - 1));
    meter::arm();
    let (v, c) = prepare(&s, m);
    let x = meter::finish();
    assert!(c.is_none() && s.validated.get() == 1 && v.cursor.is_some());
    assert!(x.page[0] > 0 && x.page[1] > 0 && x.total.iter().all(|n| *n > 0));
    assert!(x.marks[0] >= 12 && x.marks[1] == 1);
    assert!(x.pack_heap > x.page[0]);
    if IS_STOCK {
        assert_eq!(x.pack_live, x.total);
        assert_eq!(x.page_live, x.total);
        assert_eq!(x.tool_live, x.total)
    } else {
        assert_eq!(x.pack_live, [0, x.total[1]]);
        assert_eq!(x.page_live, [0, x.total[1]]);
        assert_eq!(x.tool_live, [0, 0]);
    }
    x
}
