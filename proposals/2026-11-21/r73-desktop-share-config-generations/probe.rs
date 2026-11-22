#![allow(dead_code)]
mod adapter;
mod routes;
mod session;

use adapter::{ContextUsage, Session, accept_config, state};
use proteus_contracts::app_protocol::AppPendingRequests;
use proteus_contracts::app_protocol::config::{ConfigSummary, ConfigTool, ModelOption};
use proteus_contracts::app_protocol::settings::{SessionSetting, SessionSettingControl};
use routes::{Event, Host, Lifetime, Outgoing, Runtime};
use serde_json::json;
use session::{State, Update};
use std::path::PathBuf;
use uuid::Uuid;

fn payload(generation: usize, rows: usize) -> ConfigSummary {
    let session_settings = vec![
        SessionSetting {
            id: "fixture-unknown".into(),
            name: "Опции".into(),
            category: None,
            control: SessionSettingControl::Unsupported(json!({
                "type":"future",
                "z":[null, -0.0, u64::MAX],
                "a":{"κ":"строка\n\""}
            })),
        },
        SessionSetting {
            id: "mode".into(),
            name: "Mode".into(),
            category: Some("fixture".into()),
            control: SessionSettingControl::Select {
                value: "normal".into(),
                options: vec![],
            },
        },
    ];
    ConfigSummary {
        module_epoch: generation as u64,
        profile: format!("profile-{generation}-λ"),
        model_catalog_error: (generation == 2).then(|| "fixture unavailable".into()),
        model_options: (0..rows)
            .map(|i| ModelOption {
                name: format!("model-{i}"),
                description: Some("синтетическое описание ".repeat(8)),
                ..ModelOption::default()
            })
            .collect(),
        registered_tools: (0..rows / 2)
            .map(|i| ConfigTool {
                name: format!("tool-{i}"),
                description: "Synthetic tool description, not a command. ".repeat(20),
                ..ConfigTool::default()
            })
            .collect(),
        session_settings,
        ..ConfigSummary::default()
    }
}

fn resident(config: Option<ConfigSummary>, pending: bool) -> Session {
    let mut session = Session {
        connected: true,
        config: None,
        context: Some(ContextUsage {
            used: 37,
            max: 100,
            trigger: None,
        }),
        execution: Default::default(),
        pending: pending
            .then(|| AppPendingRequests::new(Uuid::from_u128(0x100), "fixture-stream".into())),
    };
    if let Some(config) = config {
        accept_config(&mut session, config);
    }
    session
}
fn profile(state: &State) -> (*const u8, &str) {
    let config = state.config.as_ref().unwrap();
    (config.profile.as_ptr(), config.profile.as_str())
}
fn snapshot(
    runtime: &Runtime,
    id: &str,
    path: Option<PathBuf>,
    session: &Session,
) -> Option<Outgoing> {
    runtime.should_snapshot(id, path.clone()).then(|| {
        let host = Host::new(path.clone());
        Outgoing::SessionSnapshot {
            context: id.into(),
            session_dir: path,
            state: host
                .supports_core(&())
                .then(|| Box::new(state(session, None))),
            // This headless slice exercises state-only snapshot readers.
            entries: vec![],
        }
    })
}
fn route_controls() {
    let a = PathBuf::from("/fixture/a");
    let b = PathBuf::from("/fixture/b");
    let mut one = Runtime::new(Lifetime::Workspace, true, false);
    let null = resident(None, false);
    assert!(snapshot(&one, "missing", Some(a.clone()), &null).is_none());
    one.scope("one", false, Some(a.clone()));
    let Some(snapshot_null) = snapshot(&one, "one", Some(a.clone()), &null) else {
        panic!("initial Core state with missing config still sends a snapshot");
    };
    let no_config = serde_json::to_string(&snapshot_null).unwrap();
    assert!(no_config.contains(r#""state":{"connected":true,"config":null"#));
    println!("{no_config}");

    one.scope("one", true, Some(a.clone()));
    one.scope("moved", false, Some(a.clone()));
    one.scope("other", false, Some(b.clone()));
    assert!(snapshot(&one, "moved", Some(a.clone()), &null).is_none());
    assert!(snapshot(&one, "other", Some(b.clone()), &null).is_some());

    let mut no_core = Runtime::new(Lifetime::Workspace, true, false);
    no_core.scope("empty", false, None);
    let empty = serde_json::to_string(&snapshot(&no_core, "empty", None, &null).unwrap()).unwrap();
    assert!(empty.contains(r#""session_dir":null,"state":null,"entries":[]"#));
    println!("{empty}");

    let mut no_events = Runtime::new(Lifetime::Workspace, false, true);
    let mut preview = Runtime::new(Lifetime::Preview, true, true);
    for r in [&mut no_events, &mut preview] {
        r.scope("one", false, Some(a.clone()));
        assert!(snapshot(r, "one", Some(a.clone()), &null).is_none());
    }
    let event = Event {
        session_dir: a.clone(),
        event_id: 17,
        update: Update::State {
            state: Box::new(state(&null, None)),
        },
    };
    let left = Host::new(Some(a.clone()));
    let unrelated = Host::new(Some(b));
    assert!(one.receive(&unrelated, &event).is_none()); // wrong route does not consume ID
    assert!(one.receive(&left, &event).is_some());
    assert!(one.receive(&left, &event).is_none()); // retained duplicate/rehost context suppressed
    assert!(no_events.receive(&left, &event).is_none());
    assert!(preview.receive(&left, &event).is_none());
    assert!(no_core.receive(&Host::new(None), &event).is_none());
    let entries = Event {
        session_dir: a,
        event_id: 18,
        update: Update::Entries {
            start: 0,
            removed: 0,
            entries: vec![],
        },
    };
    assert!(one.receive(&left, &entries).is_none());
    let mut full = Runtime::new(Lifetime::Workspace, true, true);
    assert!(full.receive(&left, &entries).is_some());
    assert!(full.receive(&left, &entries).is_none());
    assert!(adapter::accepts_local(1, 1) && !adapter::accepts_local(2, 1));
    assert!(adapter::accepts_discovered(2, 2) && !adapter::accepts_discovered(3, 2));
    eprintln!(
        "ROUTES later duplicate/same-session cold baseline suppressed; foreign/preview/disabled/entry-only controls; no-Core null state distinct from null config; stale local/discovered comparisons"
    );
}

fn frame_state(frame: &Outgoing) -> &State {
    match frame {
        Outgoing::SessionSnapshot {
            state: Some(state), ..
        }
        | Outgoing::SessionUpdate {
            update: Update::State { state },
            ..
        } => state,
        _ => unreachable!(),
    }
}
fn fanout(
    resident: &Session,
    generation: usize,
    rows: usize,
    readers: usize,
    candidate: bool,
) -> Vec<Outgoing> {
    let source = resident.config.as_ref().unwrap().profile.as_ptr();
    let path = PathBuf::from("/fixture/a");
    let event = Event {
        session_dir: path.clone(),
        event_id: generation as u64,
        update: Update::State {
            state: Box::new(state(resident, None)),
        },
    };
    let Update::State { state: projected } = &event.update else {
        unreachable!()
    };
    let project = usize::from(profile(projected).0 != source);
    let mut fanout = 0;
    let mut cold = 0;
    let messages = (0..readers)
        .map(|i| {
            let name = format!("fixture-{i}");
            let mut runtime = Runtime::new(Lifetime::Workspace, true, false);
            runtime.scope(&name, false, Some(path.clone()));
            let outgoing = if i < readers / 2 {
                let host = Host::new(Some(path.clone()));
                let update = runtime.receive(&host, &event).unwrap();
                assert!(runtime.receive(&host, &event).is_none());
                let outgoing = Outgoing::SessionUpdate {
                    context: name,
                    session_dir: path.clone(),
                    update,
                };
                fanout += usize::from(profile(frame_state(&outgoing)).0 != profile(projected).0);
                outgoing
            } else {
                let outgoing = snapshot(&runtime, &name, Some(path.clone()), resident).unwrap();
                cold += usize::from(profile(frame_state(&outgoing)).0 != source);
                outgoing
            };
            outgoing
        })
        .collect();
    let want = if candidate {
        (0, 0, 0)
    } else {
        (1, readers / 2, readers - readers / 2)
    };
    assert_eq!((project, fanout, cold), want);
    eprintln!(
        "WORK generation={generation} rows={rows} readers={readers} projection={project} subscriber={fanout} cold={cold} extra_profile_buffers={}",
        project + fanout + cold
    );
    messages
}

fn main() {
    let arm = env!("R73_CONFIG_PROBE_ARM");
    eprintln!("ARM {arm}");
    let candidate = arm.ends_with("/candidate");
    route_controls();
    let mut owner = resident(Some(payload(1, 8)), true);
    let old = fanout(&owner, 1, 8, 2, candidate);
    // Accepted discovery replaces the resident whole. Hold old frames live;
    // late discovery cannot mutate them or bind new frames to generation 1.
    if adapter::accepts_discovered(2, 2) {
        accept_config(&mut owner, payload(2, 512));
    }
    assert!(!adapter::accepts_discovered(3, 1));
    let fresh = fanout(&owner, 2, 512, 6, candidate);
    for (frames, wanted) in [(&old, "profile-1-λ"), (&fresh, "profile-2-λ")] {
        for frame in frames {
            assert_eq!(profile(frame_state(frame)).1, wanted);
            println!("{}", serde_json::to_string(frame).unwrap());
        }
    }
    assert_ne!(
        profile(frame_state(&old[0])).0,
        profile(frame_state(&fresh[0])).0
    );
}
