//! Project the durable reducer into the existing renderer v1 DTO.
use lrt_local_workflow::{ports::ReceiptResult, scheduler::{PauseReason, RunStatus, Stage}, Scheduler};
use serde_json::{json, Value};
use super::data::{Data, Run};

pub fn run(scheduler: &Scheduler, meta: &Run) -> Value {
    let pending = scheduler.pending();
    let captured = scheduler.captured_input_count();
    let status = if !meta.handoff.is_null() && meta.handoff["mode"] != "automatic" { "paused" } else { match scheduler.status() {
        RunStatus::Running => "running", RunStatus::Paused { .. } => "paused",
        RunStatus::Complete => if meta.released { "complete" } else { "stopping" },
        RunStatus::Stopped => if !meta.released { "stopping" }
            else if meta.error.is_some() || scheduler.jobs().iter().any(|job| matches!(job.stage, Stage::Failed)) { "failed" } else { "stopped" },
    }};
    let stopped = matches!(scheduler.status(), RunStatus::Stopped);
    let mut review = Value::Null;
    if let RunStatus::Paused { detail: PauseReason::ReviewRequired { report_id, .. } } = scheduler.status() {
        if let Some(command) = pending {
            review = json!({"review_id":report_id,"file_id":command.identity.input_occurrence_id,
                "node_id":command.identity.node_id,"family":"compatible_preset","reason":"需要查看完整前后对比并明确批准；未批准时不会应用预设"});
        }
    }
    let files: Vec<_> = scheduler.jobs().iter().map(|job| {
        let current = pending.filter(|command| command.identity.input_occurrence_id == job.input.occurrence_id);
        let step = if let Some(command) = current {
            match scheduler.status() {
                RunStatus::Paused { detail: PauseReason::ReviewRequired { .. } } => "review_required",
                RunStatus::Paused { detail: PauseReason::UncertainOutcome { .. } } => "unknown",
                _ => { let _ = command; "pending" },
            }
        } else { match job.stage { Stage::Done => "succeeded", Stage::Skipped => "skipped", Stage::Failed => "failed", _ if stopped => "stopped", _ => "waiting" } };
        let stage = serde_json::to_value(&job.stage).unwrap_or(Value::Null);
        let nodes: Vec<_> = scheduler.graph().ordered_nodes().iter().map(|node| {
            let receipts: Vec<_> = job.receipts.iter().filter(|receipt| receipt.identity.node_id == node.id).collect();
            let final_receipt = receipts.last();
            let condition_skipped = !job.preset_condition_matched && matches!(node.operation,
                lrt_local_workflow::schema::NodeKind::CompatiblePreset { .. } | lrt_local_workflow::schema::NodeKind::AutomaticPreset { .. });
            let status = if current.is_some_and(|command| command.identity.node_id == node.id) { step }
                else if let Some(receipt) = final_receipt {
                    match &receipt.result { ReceiptResult::Failed { .. } => "failed", ReceiptResult::Cancelled { .. } => "skipped",
                        ReceiptResult::ImportPrepared { .. } | ReceiptResult::ExportFrozen { .. } | ReceiptResult::PresetPreflight { .. } => "running",
                        _ => "succeeded" }
                } else if node.id == scheduler.graph().source().id { "succeeded" }
                else if matches!(node.operation, lrt_local_workflow::schema::NodeKind::PathLabels { .. }) { "succeeded" }
                else { "waiting" };
            json!({"node_id":node.id,"status":status,"receipt_id":final_receipt.map(|receipt| receipt.identity.operation_id.clone()),
                "message":if condition_skipped { Some("已配置的标签条件不匹配；明确跳过整个预设，未应用其中任何模块") } else { None }})
        }).collect();
        let output = job.receipts.iter().rev().find_map(|receipt| match &receipt.result {
            ReceiptResult::Exported { outputs, .. } => outputs.first().map(|output| output.path.clone()), _ => None,
        });
        json!({"file_id":job.input.occurrence_id,"relative_path":job.input.relative_path,"status":step,
            "stage":stage,"labels":job.labels,"nodes":nodes,"message":job.warning,"output_path":output})
    }).collect();
    let mut diagnostics = Vec::new();
    if scheduler.graph().automatic() {
        diagnostics.push(match captured {
            Some(total) => json!({"severity":"info","code":"automatic_captured_inputs",
                "message":format!("本次固定捕获 {} 个原图；已登记 {} 个，尚未登记 {} 个。新增文件不加入本次任务；登记不代表处理成功。",
                    total, scheduler.jobs().len(), total.saturating_sub(scheduler.jobs().len()))}),
            None => json!({"severity":"info","code":"automatic_capture_pending",
                "message":"尚未保留完整来源捕获清单；不能将已登记数量当作全部请求照片。"}),
        });
    }
    if let Some(error) = &meta.error { diagnostics.push(json!({"severity":"error","code":"native_host_fence","message":error})); }
    if let RunStatus::Paused { detail: PauseReason::UncertainOutcome { detail, .. } } = scheduler.status() {
        diagnostics.push(json!({"severity":"error","code":"owner_outcome_unknown","message":detail}));
    }
    json!({"run_id":meta.run_id,"workflow_id":scheduler.graph().graph().workflow_id,
        "graph_revision":scheduler.graph().graph().revision,"execution_mode":if scheduler.graph().automatic() {"automatic"} else {"reviewed"},"status":status,"started_at":meta.started_at,
        "completed_files":scheduler.jobs().iter().filter(|job| matches!(job.stage, Stage::Done)).count(),
        "total_files":captured.unwrap_or(scheduler.jobs().len()),"captured_files":captured,
        "admitted_files":scheduler.jobs().len(),"sequence":meta.sequence,"lease_id":meta.lease_id,
        "effects_settled":meta.released && pending.is_none(),"files":files,"records_truncated":false,
        "diagnostics":diagnostics,"review":review,"handoff":meta.handoff})
}
pub fn workspace(data: &Data, available: bool, profile: &Value, profile_pending: bool) -> Value {
    let active = data.active_run.as_ref().and_then(|id| data.runs.get(id)).map(|run| run.snapshot.clone());
    json!({"port_version":1,"host_scope_id":data.host_scope_id,"workspace_revision":data.revision,
        "capabilities":{"available":available && data.blocked.is_none(),"reason":data.blocked,
            "can_save":data.blocked.is_none(),"can_run":available && data.blocked.is_none(),"can_open_review":available && data.blocked.is_none(),
            "error_policies":{"directory_source":["stop"],"managed_import":["stop"],
                "path_labels":["stop","skip"],"compatible_preset":["stop"],"automatic_preset":["stop","skip"],"export":["stop","skip"]}},
        "definitions":data.definitions.iter().map(|(id,row)|json!({"workflow_id":id,"name":row.definition.name,
            "storage_revision":row.definition.storage_revision,"updated_at":row.updated_at})).collect::<Vec<_>>(),
        "runs":data.runs.values().map(|run|run.snapshot.clone()).collect::<Vec<_>>(),"active_run":active,
        "lease":data.lease.as_ref().map(|lease|lease.public()),
        "recipe_sha256":profile["recipe_sha256"],"recipe_profile":profile["recipe_profile"],"recipe_profile_pending":profile_pending,
        "preset_catalogue":profile["preset_catalogue"],"export_profiles":profile["export_profiles"],
        "unresolved_requests":data.requests.values().filter(|row|super::wire::unresolved(&row.receipt))
            .map(|row|json!({"request_id":row.request.request_id,"command_kind":row.request.command.name()})).collect::<Vec<_>>()})
}
