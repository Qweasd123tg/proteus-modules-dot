#![allow(dead_code)]
mod probe {
use std::collections::HashSet;
use std::marker::PhantomData;
use proteus_contracts::app_protocol::{config_builder::ConfigBuilderSnapshot, addons::AppAddonsSnapshot};
use settings::draft::Draft;
use settings::mcp::mcp_problems;
pub mod settings {
    #[path = "/workspace/shared/desktop-state-edges-audit/src/settings/mcp.rs"] pub mod mcp;
    #[path = "/workspace/shared/desktop-state-edges-audit/src/settings/draft.rs"] pub mod draft;
    #[path = "/workspace/shared/desktop-state-edges-audit/src/settings/addons.rs"] pub mod addons;
}
#[derive(Default)] struct Context<T>(PhantomData<T>);
impl<T> Context<T> { fn notify(&mut self) {} }
#[derive(Default)] struct Editors { error: bool }
impl Editors { fn has_errors(&self)->bool {self.error} }
#[derive(Default)] struct Catalogs {busy:bool}
#[derive(Default)] enum LoadState { #[default] Unavailable, Loading, Failed(String), Ready(Box<ConfigBuilderSnapshot>) }
#[derive(Default)] struct SettingsView {
 state: LoadState, baseline: Draft, draft: Draft, editors: Editors, catalogs: Catalogs,
 saving:bool, reloading:bool, edit_revision:u64, catalog_conflict:Option<String>,
 json:HashSet<(String,String)>, feedback:Option<String>, feedback_timer:Option<()>
}
impl SettingsView {
 fn addons(&self)->Option<&AppAddonsSnapshot>{None}
 fn show_feedback(&mut self,text:impl Into<String>,_:bool,_:&mut Context<Self>){self.feedback=Some(text.into());}
    fn accept(&mut self, snapshot: ConfigBuilderSnapshot) {
        self.catalog_conflict = None;
        self.baseline = Draft::from_snapshot(&snapshot);
        self.draft = self.baseline.clone();
        self.forget_editors();
        self.state = LoadState::Ready(Box::new(snapshot));
    }

    fn snapshot(&self) -> Option<&ConfigBuilderSnapshot> {
        match &self.state {
            LoadState::Ready(snapshot) => Some(snapshot),
            _ => None,
        }
    }

    fn dirty(&self) -> bool {
        self.draft.is_dirty(&self.baseline) || self.editors.has_errors()
    }

    pub(super) fn has_unsaved_changes(&self) -> bool {
        self.dirty() || self.saving || self.catalogs.busy
    }

    fn can_save(&self) -> bool {
        self.snapshot().is_some_and(|snapshot| snapshot.writable)
            && !self.saving
            && !self.catalogs.busy
            && self.dirty()
            && !self.has_errors()
    }

    fn has_errors(&self) -> bool {
        self.editors.has_errors() || !mcp_problems(&self.draft, self.addons()).is_empty()
    }

    fn update_draft(&mut self, cx: &mut Context<Self>, change: impl FnOnce(&mut Draft)) {
        change(&mut self.draft);
        self.edit_revision = self.edit_revision.wrapping_add(1);
        self.clear_feedback();
        cx.notify();
    }

    fn replace_draft(&mut self, draft: Draft, cx: &mut Context<Self>) {
        self.catalog_conflict = None;
        self.draft = draft;
        self.edit_revision = self.edit_revision.wrapping_add(1);
        self.forget_editors();
        self.clear_feedback();
        cx.notify();
    }

    fn discard(&mut self, cx: &mut Context<Self>) {
        self.replace_draft(self.baseline.clone(), cx);
    }

    fn forget_editors(&mut self) {
        self.editors = Editors::default();
        self.json.clear();
    }

    fn clear_feedback(&mut self) {
        self.feedback = None;
        self.feedback_timer = None;
    }

    pub(super) fn accept_save(&mut self, snapshot: ConfigBuilderSnapshot, submitted_revision: u64) {
        self.catalog_conflict = None;
        if self.edit_revision == submitted_revision {
            self.accept(snapshot);
        } else {
            self.baseline = Draft::from_snapshot(&snapshot);
            self.state = LoadState::Ready(Box::new(snapshot));
        }
    }
 fn complete_reload(&mut self, result:anyhow::Result<ConfigBuilderSnapshot>, cx:&mut Context<Self>) {
  let this=self;
                this.reloading = false;
                match result {
                    // Edits made while the profile was read win over it.
                    Ok(_) if this.dirty() => {}
                    Ok(snapshot) => this.accept(snapshot),
                    Err(error) if this.snapshot().is_some() => this.show_feedback(
                        format!("Не удалось перечитать профиль: {error:#}"),
                        true,
                        cx,
                    ),
                    Err(error) => this.state = LoadState::Failed(format!("{error:#}").into()),
                }
                cx.notify();
 }
}
#[cfg(test)] #[path="/workspace/shared/desktop-state-edges-audit/audit-state-edges/probe/src/tests.rs"] mod tests;
}
