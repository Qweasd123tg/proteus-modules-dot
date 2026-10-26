mod common;
use common::*;
use proteus_example_correction_memory::{
    store::{Stage, Store},
    util::sha256,
    *,
};
use serde_json::json;
use std::{
    fs,
    os::unix::fs::{PermissionsExt, symlink},
    sync::{Arc, Barrier},
};

#[test]
fn unknown_empty_and_foreign_schema_are_unchanged() {
    let e = Env::new();
    fs::write(e.db(), []).unwrap();
    fs::set_permissions(e.db(), fs::Permissions::from_mode(0o600)).unwrap();
    fail(
        &e.call(INIT, json!({}), &mut e.host()),
        "invalid_store_size",
    );
    assert_eq!(fs::metadata(e.db()).unwrap().len(), 0);
    fs::remove_file(e.db()).unwrap();
    e.init();
    let conn = rusqlite::Connection::open(e.db()).unwrap();
    conn.execute_batch("CREATE TABLE unrelated(data TEXT)")
        .unwrap();
    drop(conn);
    let before = fs::read(e.db()).unwrap();
    fail(
        &e.call(INIT, json!({}), &mut e.host()),
        "invalid_store_schema",
    );
    fail(
        &e.call(
            READ,
            json!({"kind":"entry","key":"release.status"}),
            &mut e.host(),
        ),
        "invalid_store_schema",
    );
    assert_eq!(before, fs::read(e.db()).unwrap());
}

#[test]
fn sqlite_prefix_lookalike_trigger_cannot_hide_from_schema_check() {
    let e = Env::new();
    e.init();
    assert_eq!(e.entry()["revision"], 0);
    let request = e.prepared();
    let conn = rusqlite::Connection::open(e.db()).unwrap();
    conn.execute_batch("CREATE TRIGGER sqliteX_hidden AFTER INSERT ON entries BEGIN SELECT 1; END")
        .unwrap();
    drop(conn);
    let before = fs::read(e.db()).unwrap();
    let mut host = e.host();
    fail(&e.apply(&request, &mut host), "invalid_store_schema");
    assert_eq!(host.count(), 0);
    assert_eq!(before, fs::read(e.db()).unwrap());
}

#[test]
fn trigger_sharing_a_table_name_is_still_an_extra_schema_object() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let conn = rusqlite::Connection::open(e.db()).unwrap();
    conn.execute_batch("CREATE TRIGGER entries AFTER INSERT ON entries BEGIN SELECT 1; END")
        .unwrap();
    let count: i64 = conn
        .query_row(
            "SELECT count(*) FROM sqlite_schema WHERE name='entries'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(count, 2);
    drop(conn);
    let before = fs::read(e.db()).unwrap();
    let mut host = e.host();
    fail(&e.apply(&request, &mut host), "invalid_store_schema");
    assert_eq!(host.count(), 0);
    assert_eq!(before, fs::read(e.db()).unwrap());
}

#[test]
fn corrupt_entry_operation_id_is_bounded_and_refused_without_write() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    assert!(e.apply(&request, &mut e.host()).ok);
    assert_eq!(e.entry()["revision"], 1);
    for bad in ["x".repeat(65), "invalid/id".into()] {
        let conn = rusqlite::Connection::open(e.db()).unwrap();
        conn.execute_batch("PRAGMA foreign_keys=OFF").unwrap();
        conn.execute(
            "UPDATE entries SET last_operation=?1 WHERE key='release.status'",
            [bad],
        )
        .unwrap();
        drop(conn);
        let before = fs::read(e.db()).unwrap();
        let result = e.call(
            READ,
            json!({"kind":"entry","key":"release.status"}),
            &mut e.host(),
        );
        fail(&result, "invalid_store_entry_operation");
        assert_eq!(before, fs::read(e.db()).unwrap());
    }
}
#[test]
fn wal_header_is_refused_without_auxiliary_creation() {
    let e = Env::new();
    e.init();
    assert_eq!(e.entry()["revision"], 0);
    let conn = rusqlite::Connection::open(e.db()).unwrap();
    conn.execute_batch("PRAGMA journal_mode=WAL").unwrap();
    drop(conn);
    let before = fs::read(e.db()).unwrap();
    assert_eq!(before[18], 2);
    assert_eq!(before[19], 2);
    let names = || {
        let mut n: Vec<_> = fs::read_dir(e.db().parent().unwrap())
            .unwrap()
            .map(|x| x.unwrap().file_name())
            .collect();
        n.sort();
        n
    };
    let files = names();
    fail(
        &e.call(
            READ,
            json!({"kind":"entry","key":"release.status"}),
            &mut e.host(),
        ),
        "store_requires_rollback_format",
    );
    assert_eq!(before, fs::read(e.db()).unwrap());
    assert_eq!(files, names());
}
#[test]
fn symlink_hardlink_and_nonprivate_parent_are_refused() {
    let e = Env::new();
    let target = e.cwd().join("target");
    fs::write(&target, b"untouched").unwrap();
    symlink(&target, e.db()).unwrap();
    fail(&e.call(INIT, json!({}), &mut e.host()), "store_open_error");
    assert_eq!(fs::read(&target).unwrap(), b"untouched");
    fs::remove_file(e.db()).unwrap();
    e.init();
    let link = e.cwd().join("other-link");
    fs::hard_link(e.db(), &link).unwrap();
    fail(
        &e.call(
            READ,
            json!({"kind":"entry","key":"release.status"}),
            &mut e.host(),
        ),
        "store_file_type",
    );
    fs::remove_file(link).unwrap();
    fs::set_permissions(e.db().parent().unwrap(), fs::Permissions::from_mode(0o755)).unwrap();
    fail(
        &e.call(
            READ,
            json!({"kind":"entry","key":"release.status"}),
            &mut e.host(),
        ),
        "store_parent_not_private",
    );
}
#[test]
fn replacement_during_valid_verifier_callback_cannot_mutate_new_instance() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let old = request.proposal.database_instance_id.clone();
    let path = e.db();
    let cwd = e.cwd().to_path_buf();
    let config = e.config.clone();
    let mut host = e.host();
    host.after = Box::new(move || {
        fs::rename(&path, path.with_extension("previous")).unwrap();
        let replacement = CorrectionMemory::new(config.clone()).unwrap();
        let mut h = Host::new(&cwd);
        let result = invoke(&replacement, &cwd, INIT, json!({}), &mut h);
        assert!(result.ok, "{result:?}");
    });
    fail(&e.apply(&request, &mut host), "store_instance_mismatch");
    assert_eq!(host.count(), 1);
    let entry = e.entry();
    assert_eq!(entry["revision"], 0);
    assert_ne!(entry["identity"]["database_instance_id"], old);
    assert!(e.operation(&request.operation_id)["record"].is_null());
}
#[test]
fn callback_holds_no_read_connection_or_lock() {
    let e = Env::new();
    e.init();
    let outer = e.prepared();
    let mut competitor = outer.clone();
    competitor.operation_id = "callback-writer".into();
    let cwd = e.cwd().to_path_buf();
    let config = e.config.clone();
    let mut host = e.host();
    host.after = Box::new(move || {
        let module = CorrectionMemory::new(config.clone()).unwrap();
        let result = invoke(
            &module,
            &cwd,
            APPLY,
            serde_json::to_value(&competitor).unwrap(),
            &mut Host::new(&cwd),
        );
        assert_eq!(outcome(&result)["decision"], "applied");
    });
    let result = e.apply(&outer, &mut host);
    assert_eq!(outcome(&result)["decision"], "conflict");
    assert_eq!(e.entry()["revision"], 1);
}
#[test]
fn precommit_faults_roll_back_and_postcommit_loss_recovers() {
    for stage in [
        Stage::BeforeMutation,
        Stage::AfterEntry,
        Stage::BeforeCommit,
        Stage::AfterCommit,
    ] {
        let e = Env::new();
        e.init();
        let request = e.prepared();
        let o = observation(e.cwd(), &request.proposal.evidence, "verified-now");
        let store = Store::resolve(&e.config, e.module.policy_sha256(), e.cwd()).unwrap();
        let result = store.apply(
            &request,
            &o,
            |s| {
                if s == stage {
                    anyhow::bail!("injected_cancellation")
                }
                Ok(())
            },
            |r, _| Ok(r.clone()),
        );
        assert!(
            result
                .unwrap_err()
                .to_string()
                .contains("injected_cancellation")
        );
        if stage == Stage::AfterCommit {
            assert_eq!(e.entry()["revision"], 1);
            let mut h = e.host();
            assert_eq!(outcome(&e.apply(&request, &mut h))["decision"], "applied");
            assert_eq!(h.count(), 0);
        } else {
            assert_eq!(e.entry()["revision"], 0);
            assert!(e.operation(&request.operation_id)["record"].is_null());
            assert!(e.apply(&request, &mut e.host()).ok);
        }
    }
}
#[test]
fn response_construction_failure_precedes_all_sql_mutations() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let o = observation(e.cwd(), &request.proposal.evidence, "verified-now");
    let store = Store::resolve(&e.config, e.module.policy_sha256(), e.cwd()).unwrap();
    let before = sha256(&fs::read(e.db()).unwrap());
    let result: anyhow::Result<()> = store.apply(
        &request,
        &o,
        |_| Ok(()),
        |_, _| anyhow::bail!("response_too_large"),
    );
    assert_eq!(result.unwrap_err().to_string(), "response_too_large");
    assert_eq!(before, sha256(&fs::read(e.db()).unwrap()));
    assert_eq!(e.entry()["revision"], 0);
}

#[test]
fn transactional_replay_polls_cancellation_after_response_build() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    assert!(e.apply(&request, &mut e.host()).ok);
    let o = observation(e.cwd(), &request.proposal.evidence, "verified-now");
    let store = Store::resolve(&e.config, e.module.policy_sha256(), e.cwd()).unwrap();
    let canceled = std::cell::Cell::new(false);
    let result = store.apply(
        &request,
        &o,
        |_| {
            anyhow::ensure!(!canceled.get(), "canceled");
            Ok(())
        },
        |_, replayed| {
            assert!(replayed);
            canceled.set(true);
            Ok(())
        },
    );
    assert_eq!(result.unwrap_err().to_string(), "canceled");
    assert_eq!(e.entry()["revision"], 1);
}

#[test]
fn idempotent_init_polls_cancellation_after_reading_identity() {
    let e = Env::new();
    e.init();
    let store = Store::resolve(&e.config, e.module.policy_sha256(), e.cwd()).unwrap();
    let before = std::fs::read(e.db()).unwrap();
    let result = store.init(
        |stage| {
            anyhow::ensure!(stage != Stage::BeforeReturn, "canceled");
            Ok(())
        },
        |identity| Ok(identity.clone()),
    );
    assert_eq!(result.unwrap_err().to_string(), "canceled");
    assert_eq!(before, std::fs::read(e.db()).unwrap());
}

#[test]
fn incomplete_init_is_not_silently_repaired_or_deleted() {
    let e = Env::new();
    let store = Store::resolve(&e.config, e.module.policy_sha256(), e.cwd()).unwrap();
    let result = store.init(
        |stage| {
            anyhow::ensure!(stage != Stage::BeforeCommit, "injected_before_init_commit");
            Ok(())
        },
        |identity| Ok(identity.clone()),
    );
    assert_eq!(
        result.unwrap_err().to_string(),
        "injected_before_init_commit"
    );
    assert!(e.db().exists());
    let incomplete = fs::read(e.db()).unwrap();
    let second = e.call(INIT, json!({}), &mut e.host());
    assert!(!second.ok, "{second:?}");
    assert!(second.error.unwrap().contains("invalid_store_"));
    assert_eq!(incomplete, fs::read(e.db()).unwrap());
}
#[test]
fn busy_writer_returns_busy_without_record_and_exact_retry_works() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let conn = rusqlite::Connection::open(e.db()).unwrap();
    conn.execute_batch("BEGIN IMMEDIATE").unwrap();
    fail(&e.apply(&request, &mut e.host()), "busy");
    conn.execute_batch("ROLLBACK").unwrap();
    assert!(e.operation(&request.operation_id)["record"].is_null());
    assert!(e.apply(&request, &mut e.host()).ok);
}
fn race(same_id: bool, different_payload: bool) {
    let e = Env::new();
    e.init();
    let a = e.prepared();
    let mut b = a.clone();
    if !same_id {
        b.operation_id = "op-two".into();
    }
    if different_payload {
        b.proposal.new_text = "Alternative correction.".into();
    }
    let barrier = Arc::new(Barrier::new(2));
    let mut threads = vec![];
    for request in [a.clone(), b.clone()] {
        let cwd = e.cwd().to_path_buf();
        let config = e.config.clone();
        let barrier = barrier.clone();
        threads.push(std::thread::spawn(move || {
            let module = CorrectionMemory::new(config).unwrap();
            let mut host = Host::new(&cwd);
            host.after = Box::new(move || {
                barrier.wait();
            });
            let result = invoke(
                &module,
                &cwd,
                APPLY,
                serde_json::to_value(&request).unwrap(),
                &mut host,
            );
            // No module retry. The fixture explicitly retries a known busy response
            // only after both original invocations have completed (below).
            (request, result)
        }));
    }
    let mut results: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    for (request, result) in &mut results {
        if !result.ok && result.error.as_deref().unwrap_or("").ends_with("busy") {
            *result = e.apply(request, &mut e.host());
        }
    }
    assert_eq!(e.entry()["revision"], 1);
    if same_id && different_payload {
        assert_eq!(results.iter().filter(|(_, r)| r.ok).count(), 1);
        let failed = &results.iter().find(|(_, r)| !r.ok).unwrap().1;
        fail(failed, "operation_payload_mismatch");
    } else if same_id {
        assert_eq!(outcome(&results[0].1), outcome(&results[1].1));
    } else {
        let decisions: Vec<_> = results
            .iter()
            .map(|(_, r)| outcome(r)["decision"].as_str().unwrap().to_owned())
            .collect();
        assert_eq!(decisions.iter().filter(|x| *x == "applied").count(), 1);
        assert_eq!(decisions.iter().filter(|x| *x == "conflict").count(), 1);
    }
}
#[test]
fn independent_connections_same_revision_one_winner() {
    race(false, false)
}
#[test]
fn independent_connections_identical_id_payload_commit_once() {
    race(true, false)
}
#[test]
fn independent_connections_changed_payload_one_id_one_winner() {
    race(true, true)
}
