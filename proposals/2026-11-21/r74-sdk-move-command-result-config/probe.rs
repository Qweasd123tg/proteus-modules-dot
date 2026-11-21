// Only compiled as a temporary SDK unit-test module, never in the shipped patch.
use super::*;
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

thread_local! {
    static ACTIVE: Cell<bool> = const { Cell::new(false) };
    static COUNTS: Cell<(usize, usize)> = const { Cell::new((0, 0)) };
}

struct Meter;

#[global_allocator]
static METER: Meter = Meter;

fn record(bytes: usize) {
    if ACTIVE.try_with(Cell::get).unwrap_or(false) {
        COUNTS.with(|c| {
            let (calls, old_bytes) = c.get();
            c.set((calls + 1, old_bytes + bytes));
        });
    }
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, previous: Layout, bytes: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, previous, bytes) };
        if !ptr.is_null() {
            record(bytes);
        }
        ptr
    }
}

fn measure<T>(f: impl FnOnce() -> T) -> (T, usize, usize) {
    COUNTS.with(|c| c.set((0, 0)));
    ACTIVE.with(|a| a.set(true));
    let out = std::hint::black_box(f());
    ACTIVE.with(|a| a.set(false));
    let (calls, bytes) = COUNTS.with(Cell::get);
    (out, calls, bytes)
}

const A: &str = "/settings-fixture/a";
const B: &str = "/settings-fixture/b";

fn context(host: &mut Host, extension: &mut impl Extension, name: &str, session: &str) {
    host.handle(
        extension,
        json!({"type":"context","context":name,
        "session_dir":session,"workspace":"/settings-fixture"}),
    )
    .unwrap();
}

fn inputs() -> Value {
    let path = std::env::var_os("R74_REPLY_FIXTURE").unwrap();
    serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
}

#[test]
fn meter_owned_config_reply() {
    let data = inputs();
    let expected_adoption = match std::env::var("R74_ADOPTS").unwrap().as_str() {
        "yes" => true,
        "no" => false,
        _ => unreachable!(),
    };
    // libtest writes a test-name prefix before captured telemetry in serial mode.
    println!();
    for (case, size, tools) in [
        ("accepted-small", 8, 4),
        ("accepted-large", 512, 256),
        ("accepted-rehost", 512, 256),
        ("null-rejected", 0, 0),
        ("missing-clears", 0, 0),
        ("cross-session-ack", 512, 256),
        ("no-live-route", 512, 256),
    ] {
        let (mut host, mut extension) = (Host::default(), Flaky::default());
        context(&mut host, &mut extension, "old", A);
        host.state = Some(json!({"config":{"profile":"original A"},"retained":["A"]}));
        host.pending
            .push(("setting-1".into(), "mode".into(), json!("plan")));
        host.command_error = Some("prior A".into());
        let is_accepted = case.starts_with("accepted-");
        let mut addressed = "old";
        let mut session = A;
        if case == "accepted-rehost" {
            context(&mut host, &mut extension, "new", A);
            host.handle(
                &mut extension,
                json!({"type":"close_context","context":"old"}),
            )
            .unwrap();
            assert!(!host.contexts.contains_key("old"));
            // Keep the destination active as the handler resolves the old route.
        } else if case == "cross-session-ack" {
            addressed = "other";
            context(&mut host, &mut extension, addressed, B);
            host.state = Some(json!({"config":{"profile":"original B"},"retained":["B"]}));
            host.command_error = Some("prior B".into());
            assert_eq!(host.sessions[&Some(A.into())].pending().len(), 1);
        } else if case == "no-live-route" {
            addressed = "unknown";
            session = B;
        }
        let mut reply = json!({"type":"command_result","id":"setting-1",
            "context":addressed,"session_dir":session,"error":null});
        if size > 0 {
            reply["config"] = data[if size == 8 { "small" } else { "large" }].clone();
        } else if case == "null-rejected" {
            reply["config"] = Value::Null;
            reply["error"] = json!("fixture denial");
        }
        if matches!(case, "cross-session-ack" | "no-live-route") {
            reply["error"] = json!("do not apply");
        }
        let before = host.state.as_ref().unwrap().to_string();
        let expected = reply["config"].to_string();
        let input_ptrs = if is_accepted {
            Some((
                reply["config"]["profile"].as_str().unwrap().as_ptr(),
                reply["config"]["model_options"][0]["label"]
                    .as_str()
                    .unwrap()
                    .as_ptr(),
            ))
        } else {
            None
        };
        let (result, calls, bytes) = measure(|| host.handle(&mut extension, reply));
        result.unwrap();
        assert!(host.sent.borrow().is_empty());
        let state = host.state.as_ref().unwrap();
        let actual = &state["config"];
        if let Some(input_ptrs) = input_ptrs {
            assert_eq!(actual.to_string(), expected);
            assert_eq!(actual["model_options"].as_array().unwrap().len(), size);
            assert_eq!(actual["registered_tools"].as_array().unwrap().len(), tools);
            assert_eq!(state["retained"], json!(["A"]));
            let held = (
                actual["profile"].as_str().unwrap().as_ptr(),
                actual["model_options"][0]["label"]
                    .as_str()
                    .unwrap()
                    .as_ptr(),
            );
            assert_eq!(held.0 == input_ptrs.0, expected_adoption, "{case}");
            assert_eq!(held.1 == input_ptrs.1, expected_adoption, "{case}");
        } else {
            assert_eq!(state.to_string(), before);
        }
        assert_eq!(
            host.command_error.as_deref(),
            match case {
                "null-rejected" => Some("fixture denial"),
                "cross-session-ack" => Some("prior B"),
                "no-live-route" => Some("prior A"),
                _ => None,
            }
        );
        assert_eq!(host.pending.len(), usize::from(case == "no-live-route"));
        if case == "cross-session-ack" {
            assert!(host.sessions[&Some(A.into())].pending().is_empty());
        }
        if case == "accepted-rehost" {
            assert_eq!(host.current_context.as_deref(), Some("new"));
            assert!(!host.contexts.contains_key("old"));
        }
        if case == "no-live-route" {
            assert_eq!(host.current_context.as_deref(), Some("old"));
            assert!(!host.contexts.contains_key(addressed));
        }
        let semantic = json!({"case":case,"rows":size,"tools":tools,
            "profile":actual["profile"],"mode":actual["permission_mode"],"session":host.session,
            "error":host.command_error,"pending":host.pending.len()});
        println!("r74-wire {semantic}");
        println!("r74-count {case} {size} {tools} {calls} {bytes}");
    }
}
