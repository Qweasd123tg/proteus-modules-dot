from pathlib import Path
import shutil
import sys

root, destination, arm = map(Path, sys.argv[1:])
session = (root / "session.rs").read_text()
begin = session.index("        let tools_running = snapshot.transcript.iter()")
end = session.index("        self.snapshot_identity", begin)
apply = session[begin:end]
assert ("let message_ids: Vec<_>" in apply) == (str(arm) == "stock")
apply = apply.replace("self.feedback", "feedback", 1)
destination.mkdir(parents=True)
shutil.copy(root / "feedback/tests.rs", destination / "tests.rs")
adapter = """
pub(super) fn project_snapshot(
    feedback: &mut Feedback,
    snapshot: &proteus_contracts::app_protocol::AppSessionSnapshot,
) {
REPLACE
}
impl Feedback {
    pub(super) fn inspect(&self) -> super::ReceiptState {
        super::ReceiptState {
            sends: self.sends.iter().map(|send| (
                send.id.clone(), send.accepted, send.observed, send.message_id,
            )).collect(),
            latest: self.latest_receipt().map(|(send, before)| (send.id.clone(), before)),
            run: self.run.clone(),
            phase: match self.phase {
                Phase::Idle=>0, Phase::Thinking=>1, Phase::Writing=>2, Phase::Tools=>3,
            },
        }
    }
}
""".replace("REPLACE", apply.rstrip())
(destination / "mod.rs").write_text((root / "feedback/mod.rs").read_text() + "\n" + adapter)
