use super::TurnProgress;
use crate::{Fixture, Row};

pub struct State(TurnProgress);

impl State {
    pub fn new(input: Fixture) -> Self {
        Self(TurnProgress {
            messages: input.messages,
            submitted: input.submitted,
            submitted_at: input.submitted_at,
            submitted_images: input.submitted_images,
            failed_queued_inputs: input.failed,
            background_subagents: input.background,
            ..TurnProgress::default()
        })
    }

    pub fn snapshot(&self) -> Vec<Row> {
        self.0.snapshot()
    }
}
