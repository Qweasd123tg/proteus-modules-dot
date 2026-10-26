//! Small deterministic protocol responder used ONLY by our authored child fixture.
//! It never launches commands, loads plugins, reads files, or opens network sockets.
use crate::{LEGACY_VERSION, MODERN_VERSION, rich_tool};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Scenario {
    Legacy,
    Modern,
    Dual,
    IdlessLegacyError,
    FallbackFails,
    UnsupportedVersion,
    CapabilityRejected,
    HeaderMismatch,
    WrongErrorId,
    WrongSuccessId,
    WrongDiscoverResult,
    CloseDuringDiscover,
    SilentDiscover,
    ModernInputRequired,
    ModernDomainError,
}
impl Scenario {
    pub fn parse(name: &str) -> Option<Self> {
        Some(match name {
            "legacy" => Self::Legacy,
            "modern" => Self::Modern,
            "dual" => Self::Dual,
            "idless-legacy-error" => Self::IdlessLegacyError,
            "fallback-fails" => Self::FallbackFails,
            "unsupported-version" => Self::UnsupportedVersion,
            "capability-rejected" => Self::CapabilityRejected,
            "header-mismatch" => Self::HeaderMismatch,
            "wrong-error-id" => Self::WrongErrorId,
            "wrong-success-id" => Self::WrongSuccessId,
            "wrong-discover-result" => Self::WrongDiscoverResult,
            "close-during-discover" => Self::CloseDuringDiscover,
            "silent-discover" => Self::SilentDiscover,
            "modern-input-required" => Self::ModernInputRequired,
            "modern-domain-error" => Self::ModernDomainError,
            _ => return None,
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase {
    New,
    Legacy,
    Modern,
}

#[derive(Debug)]
pub enum Step {
    Reply(Value),
    Ignore,
    Exit,
}

pub struct Responder {
    scenario: Scenario,
    phase: Phase,
}
impl Responder {
    pub fn new(scenario: Scenario) -> Self {
        Self {
            scenario,
            phase: Phase::New,
        }
    }

    pub fn handle(&mut self, request: &Value) -> Step {
        let Some(method) = request["method"].as_str() else {
            return Step::Exit;
        };
        let id = request.get("id").cloned();
        if method.starts_with("notifications/") {
            return Step::Ignore;
        }
        let Some(id) = id else { return Step::Exit };
        if request["jsonrpc"] != "2.0" {
            return error(id, -32600, "fixture requires JSON-RPC2.0", None);
        }
        match method {
            "initialize" => self.initialize(id, request),
            "server/discover" => self.discover(id, request),
            "tools/list" | "tools/call" => {
                if self.phase == Phase::New {
                    return error(id, -32000, "fixture handshake missing", None);
                }
                if self.phase == Phase::Modern && !modern_metadata_valid(request) {
                    return error(id, -32020, "fixture request metadata mismatch", None);
                }
                if method == "tools/list" {
                    let mut result = json!({"tools":[rich_tool()]});
                    if self.phase == Phase::Modern {
                        result["resultType"] = json!("complete");
                        result["ttlMs"] = json!(0);
                        result["cacheScope"] = json!("private");
                    }
                    reply(id, result)
                } else if request["params"]["name"] != "lookup.record" {
                    error(id, -32602, "fixture unknown raw tool name", None)
                } else if request["params"]["arguments"] != json!({"id":"fixture-42"}) {
                    error(
                        id,
                        -32602,
                        "fixture requires exact authored arguments",
                        None,
                    )
                } else if self.scenario == Scenario::ModernInputRequired {
                    reply(
                        id,
                        json!({"resultType":"input_required","requestState":"opaque-authored-state"}),
                    )
                } else {
                    let is_error = self.scenario == Scenario::ModernDomainError;
                    let mut result = json!({"content":[{"type":"text","text":if is_error{"fixture remote refusal"}else{"fixture result"}}],"structuredContent":{"status":if is_error{"refused"}else{"found"}},"isError":is_error});
                    if self.phase == Phase::Modern {
                        result["resultType"] = json!("complete");
                    }
                    reply(id, result)
                }
            }
            _ => error(id, -32601, "fixture unsupported method", None),
        }
    }

    fn initialize(&mut self, id: Value, request: &Value) -> Step {
        match self.scenario {
            Scenario::Legacy
            | Scenario::Dual
            | Scenario::IdlessLegacyError
            | Scenario::SilentDiscover => {}
            Scenario::FallbackFails => {
                return error(id, -32000, "authored legacy initialization failure", None);
            }
            _ => {
                return error(
                    id,
                    -32601,
                    "fixture modern-only: initialize unsupported",
                    None,
                );
            }
        }
        if request["params"]["clientInfo"]["name"].as_str() != Some("authored-sdk-probe") {
            return error(id, -32602, "fixture client identity mismatch", None);
        }
        self.phase = Phase::Legacy;
        reply(id, legacy_result())
    }

    fn discover(&mut self, id: Value, request: &Value) -> Step {
        match self.scenario {
            Scenario::Legacy | Scenario::FallbackFails => {
                return error(id, -32601, "authored legacy discovery refusal", None);
            }
            Scenario::IdlessLegacyError => {
                return Step::Reply(
                    json!({"jsonrpc":"2.0","error":{"code":-32601,"message":"authored idless legacy refusal"}}),
                );
            }
            Scenario::SilentDiscover => return Step::Ignore,
            Scenario::CloseDuringDiscover => return Step::Exit,
            _ => {}
        }
        if !modern_metadata_valid(request) {
            return error(id, -32021, "fixture missing modern client metadata", None);
        }
        match self.scenario {
            Scenario::UnsupportedVersion => {
                return error(
                    id,
                    -32022,
                    "authored unsupported protocol version",
                    Some(json!({"supported":["2099-01-01"]})),
                );
            }
            Scenario::CapabilityRejected => {
                return error(id, -32021, "authored required capability rejection", None);
            }
            Scenario::HeaderMismatch => return error(id, -32020, "authored header mismatch", None),
            Scenario::WrongErrorId => {
                return error(
                    json!("wrong-authored-id"),
                    -32601,
                    "authored wrong correlation",
                    None,
                );
            }
            Scenario::WrongSuccessId => return reply(json!("wrong-authored-id"), modern_result()),
            Scenario::WrongDiscoverResult => return reply(id, legacy_result()),
            _ => {}
        }
        self.phase = Phase::Modern;
        reply(id, modern_result())
    }
}

pub fn modern_metadata_valid(request: &Value) -> bool {
    let meta = &request["params"]["_meta"];
    meta["io.modelcontextprotocol/protocolVersion"] == MODERN_VERSION
        && meta["io.modelcontextprotocol/clientInfo"]["name"] == "authored-sdk-probe"
        && meta["io.modelcontextprotocol/clientInfo"]["version"] == "0.1.0"
        && meta["io.modelcontextprotocol/clientCapabilities"].is_object()
}
fn legacy_result() -> Value {
    json!({"protocolVersion":LEGACY_VERSION,"capabilities":{"tools":{}},"serverInfo":{"name":"authored-fixture","version":"0.1.0"}})
}
fn modern_result() -> Value {
    json!({"resultType":"complete","supportedVersions":[MODERN_VERSION],"capabilities":{"tools":{}},"ttlMs":0,"cacheScope":"private","_meta":{"io.modelcontextprotocol/serverInfo":{"name":"authored-fixture","version":"0.1.0"}}})
}
fn reply(id: Value, result: Value) -> Step {
    Step::Reply(json!({"jsonrpc":"2.0","id":id,"result":result}))
}
fn error(id: Value, code: i32, message: &str, data: Option<Value>) -> Step {
    let mut error = json!({"code":code,"message":message});
    if let Some(data) = data {
        error["data"] = data;
    }
    Step::Reply(json!({"jsonrpc":"2.0","id":id,"error":error}))
}
