use anyhow::Result;
use async_trait::async_trait;
use proteus_module_sdk::contracts::contracts::{
    ApprovalRequest, ApprovalResponse, ApprovalTransport,
};
use proteus_strict_host_fixture::{expected_spec, write_call};
use serde_json::{Value, json};
use std::{path::PathBuf, sync::Mutex};

pub struct ExactApproval {
    cwd: PathBuf,
    deny: bool,
    requests: Mutex<Vec<Value>>,
}
impl ExactApproval {
    pub fn new(cwd: PathBuf, deny: bool) -> Self {
        Self {
            cwd,
            deny,
            requests: Mutex::new(vec![]),
        }
    }
    pub fn snapshot(&self) -> Vec<Value> {
        self.requests.lock().unwrap().clone()
    }
}
#[async_trait]
impl ApprovalTransport for ExactApproval {
    fn can_request_approval(&self) -> bool {
        true
    }
    async fn request_approval(&self, request: ApprovalRequest) -> Result<ApprovalResponse> {
        let mut requests = self.requests.lock().unwrap();
        let valid = requests.is_empty()
            && request.cwd.as_os_str() == self.cwd.as_os_str()
            && request.call == write_call()
            && request.tool_spec.as_ref().is_some_and(expected_spec)
            && request
                .tool_spec
                .as_ref()
                .is_some_and(|s| s.name == "write_file")
            && request
                .origin
                .as_ref()
                .is_some_and(|o| o.thread_id.is_some() && o.turn_id.is_some());
        let approved = valid && !self.deny;
        requests.push(json!({"call":request.call,"cwd":request.cwd,"reason":request.reason,"tool_spec":request.tool_spec,"origin":request.origin,"exact_match":valid,"approved":approved,"cache":"none"}));
        Ok(if approved {
            ApprovalResponse::approve()
        } else if valid {
            ApprovalResponse::deny("strict fixture approval deliberately denied")
        } else {
            ApprovalResponse::deny("unexpected strict fixture approval request")
        })
    }
}
