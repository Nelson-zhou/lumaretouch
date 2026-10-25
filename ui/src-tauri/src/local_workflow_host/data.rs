//! Durable UI identities and exact owner dispatch intents; no recovery replay.
use std::collections::BTreeMap;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use lrt_local_workflow::ports::{Command, Receipt};
use super::{storage, wire::{Definition, Request}};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SavedDefinition { pub definition: Definition, pub updated_at: String }
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Lease {
    pub lease_id: String, pub binding: Value, pub epoch: [u8; 16], pub expires: u64,
    pub arm_request: Value, pub arm_receipt: Value,
}
impl Lease {
    pub fn public(&self) -> Value {
        json!({"lease_id":self.lease_id,"project_id":self.binding["project_id"],"project_path":self.binding["path"],
            "saved":true,"dedicated":true,"expires_at":storage::timestamp(self.expires).unwrap_or_default()})
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UiExternal { pub phase: String, pub request: Value, pub epoch: [u8; 16] }
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RequestRow { pub request: Request, pub receipt: Value, pub external: Option<UiExternal> }
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Operation {
    pub command: Command, pub request: Value, pub epoch: [u8; 16],
    pub settled: bool, pub last_receipt: Option<Receipt>,
    #[serde(skip)] pub query: Option<Value>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Run {
    pub run_id: String, pub lease_id: String, pub started_at: String,
    pub managed_root_identity: [String; 2],
    pub sequence: u64, pub snapshot: Value, pub released: bool,
    pub release: Option<UiExternal>, pub error: Option<String>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Data {
    pub schema_version: u32, pub host_scope_id: String, pub revision: u64,
    pub definitions: BTreeMap<String, SavedDefinition>, pub requests: BTreeMap<String, RequestRow>,
    pub lease: Option<Lease>, pub runs: BTreeMap<String, Run>, pub active_run: Option<String>,
    pub operations: BTreeMap<String, Operation>, pub blocked: Option<String>,
}
impl Data {
    pub fn new() -> Result<Self, String> {
        Ok(Self { schema_version: 1, host_scope_id: storage::uuid()?, revision: 0,
            definitions: BTreeMap::new(), requests: BTreeMap::new(), lease: None,
            runs: BTreeMap::new(), active_run: None, operations: BTreeMap::new(), blocked: None })
    }
    pub fn recover(&mut self) -> Result<(), String> {
        if self.schema_version != 1 || self.requests.len() > super::wire::MAX_REQUESTS
            || self.runs.len() > super::wire::MAX_RUNS || self.definitions.len() > super::wire::MAX_DEFINITIONS
            || self.operations.len() > 4096 || !super::wire::identity(&self.host_scope_id) {
            return Err("工作流持久化版本、身份或容量无效；未重放写入".into());
        }
        for (id, saved) in &self.definitions {
            saved.definition.validate()?;
            if id != &saved.definition.graph.workflow_id || saved.definition.storage_revision.is_none() {
                return Err("保存定义身份不匹配".into());
            }
        }
        let outstanding = self.lease.is_some() || self.operations.values().any(|operation| !operation.settled)
            || self.requests.values().any(|row| super::wire::unresolved(&row.receipt))
            || self.runs.values().any(|run| !run.released);
        if outstanding {
            let message = "上次工作流仍有租约或未核验结果。引擎重启不能恢复原租约；保留原身份，只读核对，禁止自动重放。";
            self.blocked = Some(message.into());
            for row in self.requests.values_mut().filter(|row| super::wire::unresolved(&row.receipt)) {
                row.receipt = row.request.receipt("unknown", message);
            }
            for run in self.runs.values_mut().filter(|run| !run.released) {
                run.error = Some(message.into());
                run.snapshot["effects_settled"] = json!(false);
                if !matches!(run.snapshot["status"].as_str(), Some("stopped" | "failed")) { run.snapshot["status"] = json!("paused"); }
                run.snapshot["diagnostics"] = json!([{"severity":"error","code":"engine_epoch_lost","message":message}]);
            }
        }
        Ok(())
    }
}
