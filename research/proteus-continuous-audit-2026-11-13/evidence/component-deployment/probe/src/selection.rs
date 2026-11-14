use std::path::Path;
use crate::{Installed,Target,Snapshot,ComponentReplacement};
use crate::catalog::{inventory::Inventory,open::OFFICIAL};
pub struct Catalogs { pub inventory: Inventory }
pub struct Selection { pub snapshot: Snapshot, pub catalogs: Catalogs }
impl Selection {
    fn snapshot(&self)->Option<&Snapshot>{Some(&self.snapshot)}
    pub fn replacements(&self, installed:&Installed, previous:Option<&Installed>) -> Vec<ComponentReplacement> {
        let Target::Component {command,exports:_,..}=&installed.target;
        let previous_command = previous.and_then(|old| match &old.target {
            Target::Component { command, .. } => command.first(),
            _ => None,
        });
        let filename = command
            .first()
            .and_then(|command| Path::new(command).file_name());
        let bundled =
            self.catalogs
                .inventory
                .find(&installed.source, installed.kind, &installed.entry);
        let bundled_executable = bundled.and_then(|package| {
            let root = package.path.parent()?.parent()?.parent()?;
            Some(root.join("bin").join(filename?))
        });
        let replace = self
            .snapshot()
            .into_iter()
            .flat_map(|snapshot| &snapshot.plugins)
            .filter(|plugin| {
                previous_command.is_some_and(|old| plugin.command == *old)
                    || (OFFICIAL[0].matches(&installed.source)
                        && bundled.is_some()
                        && (Some(Path::new(&plugin.command)) == bundled_executable.as_deref()
                            || (Path::new(&plugin.command).components().count() == 1
                                && Path::new(&plugin.command).file_name() == filename)))
            })
            .map(|plugin| ComponentReplacement {
                id: plugin.id.clone(),
                command: plugin.command.clone(),
                expected_executable: if Path::new(&plugin.command).is_absolute() {
                    Some(plugin.command.clone().into())
                } else {
                    bundled_executable.clone()
                },
            })
            .collect();
        replace
    }
}
