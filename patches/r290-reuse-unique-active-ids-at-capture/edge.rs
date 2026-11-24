// Direct proof-only index shape controls. No unsupported row is asserted to
// have come from the real HistoryCapture binding serializer.
use crate::{Case, OBS, SESSION, append, digest, fixture, late_row, meter, proof, strict_seed};
use proteus_contracts::model_standard::{CanonicalMessage, MessageRole};
use serde_json::json;
use uuid::Uuid;

pub(crate) fn run() {
    for mode in ["unknown-index", "not-singleton", "weak-index"] {
        proof::configure(false, None);
        let fx = fixture(Case {
            n: 17,
            mode: "settle-unique",
            shape: "plain",
            status: "success",
        });
        let (base, _, _, base_seq, physical) = strict_seed(&fx.records);
        let mut outcomes = Vec::new();
        let mut receipt = Vec::new();
        for candidate in [false, true] {
            let mut state = base.clone();
            let mut seq = base_seq;
            // A real append detaches the shared index before the direct probe.
            state
                .apply_sequenced(
                    SESSION,
                    &append(seq, state.history_revision(), late_row()),
                    &mut seq,
                )
                .unwrap();
            assert!(proof::is_unique(&state));
            let index = match mode {
                "unknown-index" => state.history().len() + 7,
                "not-singleton" => state
                    .history()
                    .iter()
                    .position(|m| m.parts.len() > 1)
                    .unwrap(),
                "weak-index" => {
                    let mut m = CanonicalMessage::text(
                        MessageRole::Assistant,
                        "new test-only captured row",
                    );
                    m.id = Uuid::from_u128(763701);
                    m.parts[0].part_id = Uuid::from_u128(763702);
                    proof::push_for_private_shape(&mut state, m)
                }
                _ => unreachable!(),
            };
            let weak = if mode == "weak-index" {
                Some(proof::weak_guard(&state))
            } else {
                None
            };
            assert_eq!(proof::is_unique(&state), mode != "weak-index");
            proof::configure(candidate, Some(OBS));
            meter::start();
            proof::direct_check(&mut state, index, candidate).unwrap();
            let result = meter::take();
            proof::configure(false, None);
            drop(weak);
            proof::check_exact_current_memberships(&state);
            let a = &result["active_checks"][0];
            assert_eq!(a["fast"], false);
            assert_eq!(a["result_ok"], true);
            assert_eq!(
                a["scanned_rows"].as_u64().unwrap(),
                state.history().len() as u64
            );
            outcomes.push((index, state));
            receipt.push(result);
        }
        assert_eq!(outcomes[0].0, outcomes[1].0);
        proof::compare(&outcomes[0].1, &outcomes[1].1);
        println!(
            "{}",
            json!({"direct":mode,"n":17,"physical_bytes":physical,"passed":true,
            "index":outcomes[0].0,"history_sha256":digest(&outcomes[0].1.history()),
            "meters":{"stock":receipt.remove(0),"candidate":receipt.remove(0)}})
        );
    }
}
