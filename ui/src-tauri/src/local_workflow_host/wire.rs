//! Version-one renderer contract. No renderer field is an owner receipt.
use lrt_local_workflow::schema::Graph;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

pub const PORT_VERSION: u32 = 1;
pub const MAX_REQUESTS: usize = 256;
pub const MAX_RUNS: usize = 64;
pub const MAX_DEFINITIONS: usize = 128;
pub const MAX_SAFE: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Definition {
    pub name: String,
    pub description: String,
    pub storage_revision: Option<String>,
    pub graph: Graph,
}
impl Definition {
    pub fn validate(&self) -> Result<(), String> {
        if self.name.trim().is_empty() || self.name.len() > 256 || self.description.len() > 4096
            || self.name.chars().any(char::is_control) {
            return Err("工作流名称或说明无效".into());
        }
        self.graph.clone().validate().map_err(|error| error.to_string())?;
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    SaveDefinition { definition: Definition, expected_storage_revision: Option<String> },
    AcquireProjectLease { project_id: String, project_path: String },
    ReleaseProjectLease { lease_id: String },
    Start { graph: Graph, lease_id: String, preflight_token: String },
    Stop { run_id: String },
    OpenReview { run_id: String, review_id: String },
    ReviewStep { run_id: String, operation_id: String, step: String, payload: Value },
}
impl Action {
    pub fn name(&self) -> &'static str {
        match self {
            Self::SaveDefinition { .. } => "save_definition",
            Self::AcquireProjectLease { .. } => "acquire_project_lease",
            Self::ReleaseProjectLease { .. } => "release_project_lease",
            Self::Start { .. } => "start", Self::Stop { .. } => "stop",
            Self::OpenReview { .. } => "open_review", Self::ReviewStep { .. } => "review_step",
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request { pub port_version: u32, pub request_id: String, pub command: Action }
impl Request {
    pub fn parse(value: Value) -> Result<Self, String> {
        if value.to_string().len() > 512 * 1024 { return Err("工作流请求超过大小限制".into()); }
        let request: Self = serde_json::from_value(value).map_err(|error| error.to_string())?;
        if request.port_version != PORT_VERSION || !identity(&request.request_id) {
            return Err("工作流端口版本或请求身份无效".into());
        }
        Ok(request)
    }
    pub fn receipt(&self, status: &str, message: &str) -> Value {
        json!({"request_id":self.request_id,"command_kind":self.command.name(),"status":status,"message":message})
    }
    pub fn success(&self, outcome: Value) -> Value {
        json!({"request_id":self.request_id,"command_kind":self.command.name(),"status":"succeeded","outcome":outcome})
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PreflightInput { pub port_version: u32, pub graph: Graph, pub lease_id: String }
pub fn identity(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128
        && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte))
}
pub fn unresolved(receipt: &Value) -> bool {
    matches!(receipt["status"].as_str(), Some("pending" | "unknown"))
}

/// Read-only image paging never enters the durable mutation submission queue.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReviewImageInput {
    pub port_version: u32, pub run_id: String, pub operation_id: String,
    pub review_id: String, pub review_sha256: String, pub side: String, pub sha256: String, pub page: u64,
}
