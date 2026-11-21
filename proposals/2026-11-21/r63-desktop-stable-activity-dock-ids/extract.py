from pathlib import Path
import sys

source, dest, arm = map(str, sys.argv[1:])
src = Path(source).read_text()
begin = src.index("#[derive(Clone, Debug, PartialEq, Eq)]\npub(super) enum ActivityId")
end = src.index("\nstruct Activity {", begin)
state = src[begin:end]
begin = state.index("    fn key(")
end = state.index("    fn pending(", begin)
# The only method in this seam requiring ElementId/SharedString is the
# unchanged formatting of widget IDs. Selection methods remain exact.
state = state[:begin] + state[end:]
tests = src[src.index("#[cfg(test)]\nmod tests {"):]
if arm == "stock":
    assert ".sync(activities.iter().map(|item| item.id.clone()).collect());" in src
    apply = "self.sync(rendered.iter().cloned().collect());"
elif arm == "candidate":
    assert ".sync_rendered(activities.iter().map(|item| &item.id));" in src
    apply = "self.sync_rendered(rendered.iter());"
else:
    raise ValueError(arm)
scaffold = """
pub(super) fn probe_id(code: u8) -> ActivityId {
    match code {
        0 => ActivityId::Approval("shared".into()),
        1 => ActivityId::Question("shared".into()),
        2 => ActivityId::Extension("shared"),
        3 => ActivityId::Approval("other".into()),
        4 => ActivityId::Question("other".into()),
        5 => ActivityId::Extension("other"),
        6 => ActivityId::Approval("stale".into()),
        7 => ActivityId::Extension("stale"),
        _ => unreachable!(),
    }
}
fn code(id: &ActivityId) -> u8 {
    match id {
        ActivityId::Approval(id) => match id.as_str() {
            "shared" => 0, "other" => 3, "stale" => 6, _ => unreachable!(),
        },
        ActivityId::Question(id) => match id.as_str() {
            "shared" => 1, "other" => 4, _ => unreachable!(),
        },
        ActivityId::Extension(id) => match *id {
            "shared" => 2, "other" => 5, "stale" => 7, _ => unreachable!(),
        }
    }
}
impl DockState {
    pub(super) fn probe_from(live: &[u8], selected: Option<u8>) -> Self {
        Self { live: live.iter().map(|&id| probe_id(id)).collect(), selected: selected.map(probe_id) }
    }
    pub(super) fn probe_sync(&mut self, rendered: &[ActivityId]) {
        REPLACE_SYNC
    }
    pub(super) fn probe_snapshot(&self) -> crate::Snapshot {
        crate::Snapshot {
            live: self.live.iter().map(code).collect(),
            selected: self.selected().map(code),
            pending: self.pending_target().as_ref().map(code),
            presence: [
                self.present(false,false),
                self.present(false,true),
                self.present(true,false),
                self.present(true,true),
            ],
        }
    }
}
""".replace("REPLACE_SYNC",apply)
Path(dest).write_text(state + "\n" + scaffold + "\n" + tests)
