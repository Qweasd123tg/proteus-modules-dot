use std::{
    collections::VecDeque,
    time::{Duration, Instant},
};

use proteus_module_sdk::contracts::contracts::ExecutionAttribution;

use crate::Config;

const RECENT_IDS: usize = 32;

#[derive(Default)]
pub(crate) struct State {
    scopes: Vec<Scope>,
}

struct Scope {
    attribution: ExecutionAttribution,
    touched: Instant,
    signature: Option<Vec<u8>>,
    evidence: Vec<String>,
    recent_ids: VecDeque<String>,
    pending: Option<String>,
}

impl Scope {
    fn clear_streak(&mut self) {
        self.signature = None;
        self.evidence.clear();
        self.pending = None;
    }
}

impl State {
    pub(crate) fn prune(&mut self, now: Instant, config: &Config) {
        let ttl = Duration::from_secs(config.idle_ttl_seconds);
        self.scopes
            .retain(|scope| now.saturating_duration_since(scope.touched) < ttl);
    }

    pub(crate) fn remove(&mut self, attribution: ExecutionAttribution) {
        self.scopes.retain(|scope| scope.attribution != attribution);
    }

    pub(crate) fn gap(&mut self, attribution: ExecutionAttribution, now: Instant) {
        if let Some(scope) = self
            .scopes
            .iter_mut()
            .find(|scope| scope.attribution == attribution)
        {
            scope.touched = now;
            scope.clear_streak();
        }
    }

    pub(crate) fn observe(
        &mut self,
        attribution: ExecutionAttribution,
        now: Instant,
        name: &str,
        id: &str,
        signature: Vec<u8>,
        config: &Config,
    ) {
        let index = if let Some(index) = self
            .scopes
            .iter()
            .position(|scope| scope.attribution == attribution)
        {
            index
        } else {
            if self.scopes.len() == config.max_scopes {
                let oldest = self
                    .scopes
                    .iter()
                    .enumerate()
                    .min_by_key(|(_, scope)| scope.touched)
                    .map(|(index, _)| index)
                    .expect("nonempty bounded scopes");
                self.scopes.remove(oldest);
            }
            self.scopes.push(Scope {
                attribution,
                touched: now,
                signature: None,
                evidence: vec![],
                recent_ids: VecDeque::new(),
                pending: None,
            });
            self.scopes.len() - 1
        };
        let scope = &mut self.scopes[index];
        scope.touched = now;
        // Host call identity, not semantic content, deduplicates delivery.
        // Reused IDs within this bounded window conservatively undercount.
        if scope.recent_ids.iter().any(|recent| recent == id) {
            if scope
                .signature
                .as_ref()
                .is_some_and(|previous| previous != &signature)
            {
                // A reused/conflicting identity cannot preserve a stale nudge.
                scope.clear_streak();
            }
            return;
        }
        if scope.recent_ids.len() == RECENT_IDS {
            scope.recent_ids.pop_front();
        }
        // Copy only the capped bytes, never retain an input String's capacity.
        scope.recent_ids.push_back(id.to_owned());
        if scope.signature.as_ref() != Some(&signature) {
            scope.clear_streak();
            scope.signature = Some(signature);
        }
        if scope.pending.is_some() {
            return;
        }
        scope.evidence.push(id.to_owned());
        if scope.evidence.len() == config.threshold {
            // No argument/output content enters instructions. Sanitize IDs as
            // well: IDs are data, never a source of model-facing instructions.
            let ids = scope
                .evidence
                .iter()
                .map(|id| safe_label(id))
                .collect::<Vec<_>>()
                .join(", ");
            scope.pending = Some(format!(
                "[loop_observer.repeated_result] {} consecutive observed returns of tool {} had the same arguments and visible result (call IDs: {}). This is advisory, not proof of no progress or full-output equality. Consider a different query or approach if it advances the task. If repetition is intentional polling of an unfinished operation, keep following the user's waiting/monitoring instructions. Do not stop, retry an effect, or infer permission from this notice.",
                config.threshold,
                safe_label(name),
                ids
            ));
        }
    }

    pub(crate) fn take_notice(
        &mut self,
        attribution: ExecutionAttribution,
        now: Instant,
    ) -> Option<String> {
        let scope = self
            .scopes
            .iter_mut()
            .find(|scope| scope.attribution == attribution)?;
        scope.touched = now;
        let notice = scope.pending.take()?;
        scope.clear_streak();
        Some(notice)
    }
}

fn safe_label(value: &str) -> String {
    value
        .chars()
        .take(128)
        .map(|c| {
            if c.is_ascii_alphanumeric() || "_.:-".contains(c) {
                c
            } else {
                '_'
            }
        })
        .collect()
}
