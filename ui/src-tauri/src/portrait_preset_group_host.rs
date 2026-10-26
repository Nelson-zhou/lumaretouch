//! Prepared-target group receipt checks only. AUTHORED / UNRUN.
//! Frozen candidates, history and publication remain engine batch-owned.
use serde_json::{json, Value};
use crate::spill_transfer_protocol::{hex, revision};
pub(crate) const ACTIONS: &[&str] = &["portrait_preset_catalogue", "portrait_preset_preflight", "portrait_preset_prepare", "portrait_preset_image", "portrait_preset_commit", "portrait_preset_save", "portrait_preset_export_preview", "portrait_preset_export_start", "portrait_preset_export_status", "portrait_preset_export_cancel"];
fn text(v: &Value, max: usize) -> bool {
    v.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= max && !s.chars().any(char::is_control))
}
fn unique_ids(rows: &[Value], key: Option<&str>) -> bool {
    let mut ids = std::collections::BTreeSet::new();
    rows.iter().all(|row| { let id = key.map_or(row, |k| &row[k]); text(id, 128) && ids.insert(id.as_str().unwrap()) })
}
fn retained_scope(v: &Value) -> bool {
    v.as_array().is_some_and(|ops| !ops.is_empty() && ops.len()<=4
        && ops.iter().any(|op|matches!(op.as_str(),Some("lnx.skin_finish.v1"|"lnx.skin_texture.v1")))
        && ops.iter().all(|op|matches!(op.as_str(),Some("lnx.skin_finish.v1"|"lnx.skin_texture.v1"|"lnx.exposure.v1"|"lnx.white_balance.v1")))
        && ops.iter().enumerate().all(|(i,op)|!ops[..i].contains(op)))
}
fn reference_scope(v: &Value) -> bool {
    v.as_array().is_some_and(|ops| ops.len()==1 && ops[0]=="lnx.reference_color.v1")
}
fn scope(v: &Value) -> bool {
    reference_scope(v) || retained_scope(v) || v.as_array().is_some_and(|ops| !ops.is_empty() && ops.len() <= 3
        && ops.iter().all(|op| matches!(op.as_str(), Some("lnx.skin.v1" | "lnx.exposure.v1" | "lnx.white_balance.v1")))
        && ops.iter().enumerate().all(|(i, op)| !ops[..i].contains(op)))
}
fn people_target(v: &Value) -> bool {
    let Some(refs)=v["face_refs"].as_array() else{return false;};
    !refs.is_empty() && refs.len()<=8 && v["face_count"].as_u64()==Some(refs.len() as u64)
        && unique_ids(refs,Some("face_instance_id")) && refs.iter().all(|r|
            r.as_object().is_some_and(|o|o.len()==3) && hex(&r["asset_sha256"],64)
            && r["asset_sha256"]==refs[0]["asset_sha256"]
            && r["analysis_revision"].as_u64().is_some_and(|n|n<=9007199254740991))
}
fn mode(v: &Value) -> bool {
    if reference_scope(&v["module_scope"]) {v["mode"]=="reference_color"}
    else if retained_scope(&v["module_scope"]) {v["mode"]=="retained_people"}
    else {v.get("mode").is_none() || v["mode"]=="legacy_scalar"}
}
fn compact(v: &Value) -> bool {
    let Some(bytes) = v["byte_length"].as_u64() else {return false;};
    v["mime"] == "image/png" && (33..=4 * 1024 * 1024).contains(&bytes)
        && hex(&v["sha256"], 64) && v["page_count"].as_u64() == Some((bytes + 65535) / 65536)
        && ["width", "height"].iter().all(|key| v[*key].as_u64().is_some_and(|n| (1..=1024).contains(&n)))
}
fn acks(v: &Value) -> bool {
    v.as_array().is_some_and(|rows| !rows.is_empty() && rows.len() <= 8 && unique_ids(rows, Some("document_id"))
        && rows.iter().all(|row| row.as_object().is_some_and(|o| o.len() == 5)
            && revision(&row["revision"]) && ["before_sha256", "after_sha256", "review_sha256"].iter().all(|k| hex(&row[*k], 64))))
}
pub(crate) fn selected(v: &Value) -> bool {
    v["action"].as_str().is_some_and(|s| ACTIONS.contains(&s)) || v.get("portrait_preset").is_some() || v.get("portrait_preset_ack").is_some()
}
fn preparation(v: &Value) -> bool {
    let Some(ids)=v["portrait_preset_docs"].as_array() else{return false;};
    v["preparation"]==true && v["editor_restored"].is_boolean() && !ids.is_empty() && ids.len()<=8 && unique_ids(ids,None)
        && v["preparation_results"].as_array().is_some_and(|rows|rows.len()==ids.len()
            && rows.iter().zip(ids).all(|(row,id)|row["document_id"]==*id
                && matches!(row["status"].as_str(),Some("prepared"|"failed"|"not_started"))
                && (row["status"]!="failed"||text(&row["error"],12000))))
}
fn delivery_action(v: &Value) -> bool {
    matches!(v["action"].as_str(), Some("portrait_preset_save"|"portrait_preset_export_preview"|"portrait_preset_export_start"|"portrait_preset_export_status"|"portrait_preset_export_cancel"))
}
fn delivery_targets(v: &Value) -> bool {
    v.as_array().is_some_and(|rows| !rows.is_empty() && rows.len()<=8 && unique_ids(rows,Some("document_id"))
        && rows.iter().all(|r| r.as_object().is_some_and(|o|o.len()==2) && revision(&r["revision"])))
}
fn delivery_receipt(v: &Value) -> bool {
    if v["delivery"]!=true || !hex(&v["preflight_token"],32) || !text(&v["batch_id"],128) || !v["outcome_unknown"].is_boolean() {return false;}
    if v["success"]==false {
        return text(&v["error"],12000) && v["committed"]!=true && v["operation_committed"]!=true;
    }
    if v["outcome_unknown"]!=false || v["requires_reload"]==true || v["requires_readback"]==true {return false;}
    if v["action"]=="portrait_preset_save" {
        return v["save_status"]=="saved" && hex(&v["saved_project_sha256"],64);
    }
    if v["action"]=="portrait_preset_export_preview" {
        let d=&v["destination"];
        return v["export_status"]=="preview" && d["schema_version"]=="lrt.export-destination.v1"
            && hex(&d["plan_id"],64) && d["intent_revision"]==v["intent_revision"]
            && d["entries"].as_array().is_some_and(|rows|!rows.is_empty() && rows.len()<=1024 && unique_ids(rows,Some("item_id"))
                && rows.iter().all(|r| hex(&r["frame_receipt"],64) && text(&r["source_path"],16384) && text(&r["target"],16384)
                    && matches!(r["disposition"].as_str(),Some("write"|"skip"|"needs_confirmation"))));
    }
    text(&v["export_task_id"],128) && matches!(v["export_status"].as_str(),Some("queued"|"running"|"succeeded"|"failed"|"cancelled"|"partial"))
        && v["items"].as_array().is_some_and(|rows|!rows.is_empty() && rows.len()<=8 && unique_ids(rows,Some("document_id"))
            && rows.iter().all(|r|matches!(r["state"].as_str(),Some("pending"|"succeeded"|"failed"|"skipped")))
            && (v["export_status"]!="succeeded" || rows.iter().all(|r|r["state"]=="succeeded")))
        && (v["action"]!="portrait_preset_export_start" || hex(&v["plan_id"],64) && v["intent_revision"].as_u64().is_some())
        && (!matches!(v["action"].as_str(),Some("portrait_preset_export_status"|"portrait_preset_export_cancel")) || v["task_id"]==v["export_task_id"])
}
pub(crate) fn receipt(v: &Value) -> bool {
    let Some(action) = v["action"].as_str().filter(|a| ACTIONS.contains(a)) else {return false;};
    if v["portrait_preset"] != true || !v["success"].is_boolean() {return false;}
    if delivery_action(v) {return delivery_receipt(v);}
    if action=="portrait_preset_prepare" && !(v["success"]==false && v["no_write"]==true && v["outcome_unknown"]==false) {
        if !preparation(v) {return false;}
        if v["success"]==true && (v["editor_restored"]!=true || v["outcome_unknown"]!=false
            || !v["preparation_results"].as_array().unwrap().iter().all(|r|r["status"]=="prepared")
            || !v["targets"].as_array().is_some_and(|rows|v["portrait_preset_docs"].as_array().is_some_and(|ids|
                rows.len()==ids.len() && rows.iter().zip(ids).all(|(r,id)|r["document_id"]==*id)))) {return false;}
    }
    if v["success"] == false {
        return v["outcome_unknown"].is_boolean() && text(&v["error"], 12000)
            && v["committed"] != true && v["operation_committed"] != true;
    }
    if v["outcome_unknown"] == true || v["requires_reload"] == true || v["requires_readback"] == true {return false;}
    match action {
        "portrait_preset_catalogue" => {
            let c = &v["catalogue"];
            c["complete"].is_boolean() && c["errors"].is_array() && c["presets"].as_array().is_some_and(|rows|
                rows.len() <= 4096 && unique_ids(rows, Some("id")) && rows.iter().all(|r|
                    text(&r["name"], 4096) && hex(&r["preset_sha256"], 64) && r["module_ids"].is_array()))
        }
        "portrait_preset_preflight" | "portrait_preset_prepare" => hex(&v["preflight_token"], 32) && text(&v["preset_id"], 128)
            && hex(&v["preset_sha256"], 64) && scope(&v["module_scope"]) && mode(v)
            && v["targets"].as_array().is_some_and(|rows| !rows.is_empty() && rows.len() <= 8
                && unique_ids(rows, Some("document_id")) && rows.iter().all(|r| revision(&r["revision"])
                    && text(&r["path"], 16384) && compact(&r["before"]) && compact(&r["after"])
                    && hex(&r["review_sha256"], 64) && r["blocked"].is_null()
                    && (!retained_scope(&v["module_scope"]) || people_target(r))
                    && (!reference_scope(&v["module_scope"]) || (hex(&r["reference_color"]["proof"],64)
                        && r["reference_color"]["target"]["document_id"]==r["document_id"]
                        && r["reference_color"]["target"]["revision"]==r["revision"])))),
        "portrait_preset_image" => {
            let (Some(page), Some(count), Some(bytes)) = (v["page"].as_u64(), v["page_count"].as_u64(), v["byte_length"].as_u64()) else {return false;};
            hex(&v["preflight_token"], 32) && text(&v["document_id"], 128)
                && matches!(v["side"].as_str(), Some("before" | "after"))
                && (33..=4 * 1024 * 1024).contains(&bytes) && count == (bytes + 65535) / 65536 && page < count
                && hex(&v["sha256"], 64) && hex(&v["page_sha256"], 64)
                && v["base64"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 87384)
        }
        "portrait_preset_commit" => hex(&v["preflight_token"], 32) && acks(&v["portrait_preset_ack"])
            && text(&v["batch_id"], 128) && scope(&v["module_scope"]) && mode(v)
            && hex(&v["workspace_generation"],32) && delivery_targets(&v["delivery_targets"])
            && v["delivery_targets"].as_array().is_some_and(|rows|v["portrait_preset_ack"].as_array().is_some_and(|acks|
                rows.len()==acks.len() && rows.iter().zip(acks).all(|(row,ack)|row["document_id"]==ack["document_id"])))
            && v["targets"].as_array().is_some_and(|rows| rows.len() == v["portrait_preset_ack"].as_array().unwrap().len()
                && rows.iter().all(|row| row.as_u64().is_some()) && rows.iter().enumerate().all(|(i, row)| !rows[..i].contains(row)))
            && v["skipped"].as_array().is_some_and(Vec::is_empty)
            && v["rejected_docs"].as_array().is_some_and(Vec::is_empty),
        _ => false,
    }
}
pub(crate) fn mutation(v: &Value) -> bool {
    v["cmd"] == "batch" && matches!(v["action"].as_str(),Some("portrait_preset_commit"|"portrait_preset_prepare"|"portrait_preset_save"|"portrait_preset_export_start"|"portrait_preset_export_cancel"))
}
pub(crate) fn matches_request(command: &Value, value: &Value) -> bool {
    if delivery_action(command) {
        return mutation(command) && receipt(value) && value["action"]==command["action"] && value["outcome_unknown"]==false
            && value["preflight_token"]==command["preflight_token"] && value["batch_id"]==command["batch_id"]
            && ["plan_id","intent_revision","task_id"].iter().all(|key|command.get(*key).map_or(true,|expected|value.get(*key)==Some(expected)))
            && (value["success"]==true || value["no_write"]==true);
    }
    if command["action"]=="portrait_preset_prepare" {
        return mutation(command) && receipt(value) && value["action"]==command["action"]
            && value["preset_id"]==command["preset_id"] && value["preset_sha256"]==command["preset_sha256"]
            && value["portrait_preset_docs"]==command["docs"] && value["outcome_unknown"]==false
            && (value["editor_restored"]==true || value["success"]==false && value["no_write"]==true);
    }
    mutation(command) && receipt(value) && value["action"] == command["action"]
        && value["preflight_token"] == command["preflight_token"]
        && value["portrait_preset_ack"] == command["portrait_preset_ack"]
        && value["outcome_unknown"] == false
        && (value["success"] == true || value["no_write"] == true)
}
/// Retain exact authorized request identities in the shared epoch mailbox.
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    if v["cmd"] != "batch" || !v["action"].as_str().is_some_and(|a| ACTIONS.contains(&a)) {return Ok(None);}
    let mut result = json!({"portrait_preset":true});
    if delivery_action(v) {
        crate::batch_api::portrait_preset_group::command(v)?;
        result["delivery"]=json!(true);
        for key in ["preflight_token","batch_id","plan_id","intent_revision","task_id"] {
            if let Some(value)=v.get(key) {result[key]=value.clone();}
        }
        return Ok(Some(result));
    }
    match v["action"].as_str().unwrap() {
        "portrait_preset_catalogue" => {},
        "portrait_preset_preflight" | "portrait_preset_prepare" => {
            if !text(&v["preset_id"],128) || !hex(&v["preset_sha256"],64)
                || !v["docs"].as_array().is_some_and(|rows| !rows.is_empty() && rows.len()<=8 && unique_ids(rows,None)) {return Err("Invalid portrait group selection".into());}
            result["preset_id"] = v["preset_id"].clone(); result["preset_sha256"] = v["preset_sha256"].clone();
            result["portrait_preset_docs"] = v["docs"].clone();
        },
        "portrait_preset_image" => {
            if !hex(&v["preflight_token"],32) || !text(&v["document_id"],128)
                || !matches!(v["side"].as_str(),Some("before"|"after")) || !v["page"].as_u64().is_some_and(|n|n<64) {return Err("Invalid portrait group image request".into());}
            for key in ["preflight_token","document_id","side","page"] {result[key] = v[key].clone();}
        },
        "portrait_preset_commit" => {
            if !hex(&v["preflight_token"],32) || v["accepted"]!=true || !acks(&v["portrait_preset_ack"]) {return Err("Invalid portrait group acceptance".into());}
            result["preflight_token"] = v["preflight_token"].clone(); result["portrait_preset_ack"] = v["portrait_preset_ack"].clone();
        },
        _ => unreachable!(),
    }
    Ok(Some(result))
}

#[cfg(test)]
mod tests_unrun {
    use super::*;
    use crate::batch_host::BatchHost;
    #[test]
    fn reference_scope_is_explicit_and_never_mixed_unrun() {
        assert!(scope(&json!(["lnx.reference_color.v1"])));
        assert!(!scope(&json!(["lnx.reference_color.v1","lnx.skin_finish.v1"])));
        assert!(!scope(&json!(["lnx.reference_color.v1","lnx.exposure.v1"])));
        assert!(mode(&json!({"module_scope":["lnx.reference_color.v1"],"mode":"reference_color"})));
        assert!(!mode(&json!({"module_scope":["lnx.reference_color.v1"],"mode":"legacy_scalar"})));
    }
    #[test]
    fn retained_finish_scope_and_face_count_are_exact_unrun() {
        assert!(scope(&json!(["lnx.skin_finish.v1"])));
        assert!(!scope(&json!(["lnx.skin_finish.v1","lnx.skin.v1"])));
        assert!(scope(&json!(["lnx.skin_texture.v1"])));
        assert!(scope(&json!(["lnx.skin_finish.v1","lnx.skin_texture.v1"])));
        assert!(!scope(&json!(["lnx.skin_texture.v1","lnx.skin_texture.v1"])));
        assert!(!scope(&json!(["lnx.skin_colour.v1"])));
        assert!(mode(&json!({"module_scope":["lnx.skin_finish.v1"],"mode":"retained_people"})));
        assert!(!mode(&json!({"module_scope":["lnx.skin_finish.v1"]})));
        let mixed=json!(["lnx.exposure.v1","lnx.white_balance.v1","lnx.skin_finish.v1","lnx.skin_texture.v1"]);
        assert!(retained_scope(&mixed));
        assert!(mode(&json!({"module_scope":mixed.clone(),"mode":"retained_people"})));
        assert!(!mode(&json!({"module_scope":mixed.clone(),"mode":"legacy_scalar"})));
        assert!(!mode(&json!({"module_scope":["lnx.exposure.v1"],"mode":"retained_people"})));
        assert!(!retained_scope(&json!(["lnx.exposure.v1","lnx.white_balance.v1"])));
        assert!(!scope(&json!(["lnx.exposure.v1","lnx.skin_texture.v1","lnx.crop.v1"])));
        let face=json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face-a","analysis_revision":0});
        let target=json!({"face_count":1,"face_refs":[face.clone()]});
        assert!(people_target(&target));
        assert!(!people_target(&json!({"face_count":2,"face_refs":[face.clone(),face]})));
        let mut bad=target.clone();bad["face_count"]=json!(2);assert!(!people_target(&bad));
    }

    // AUTHORED / UNRUN. A task admission is not completed output; known
    // cancellation settles only its original task, unknown never settles.
    #[test]
    fn delivery_task_identity_and_terminal_honesty_unrun() {
        let command=json!({"cmd":"batch","action":"portrait_preset_export_cancel","request_id":"cancel-group",
            "preflight_token":"f".repeat(32),"batch_id":"batch-a","task_id":"task-a"});
        let mut value=json!({"event":"batch_result","action":"portrait_preset_export_cancel","request_id":"cancel-group",
            "portrait_preset":true,"delivery":true,"success":true,"outcome_unknown":false,
            "preflight_token":"f".repeat(32),"batch_id":"batch-a","task_id":"task-a","export_task_id":"task-a",
            "export_status":"cancelled","items":[{"document_id":"a","state":"succeeded"},{"document_id":"b","state":"pending"}]});
        assert!(receipt(&value));assert!(matches_request(&command,&value));
        value["export_status"]=json!("succeeded");assert!(!receipt(&value));
        value["export_status"]=json!("cancelled");value["task_id"]=json!("task-b");assert!(!matches_request(&command,&value));
        value["task_id"]=json!("task-a");value["success"]=json!(false);value["outcome_unknown"]=json!(true);value["error"]=json!("outcome unconfirmed");
        assert!(receipt(&value));assert!(!matches_request(&command,&value));
        let mut saved=json!({"action":"portrait_preset_save","portrait_preset":true,"delivery":true,
            "success":true,"outcome_unknown":false,"preflight_token":"f".repeat(32),"batch_id":"batch-a",
            "save_status":"saved","saved_project_sha256":"a".repeat(64)});
        assert!(receipt(&saved));saved["saved_project_sha256"]=Value::Null;assert!(!receipt(&saved));
    }
    // AUTHORED / UNRUN: exact task readback settles the original start only;
    // another task or group cannot reuse its pending admission authority.
    #[test]
    fn exact_export_readback_reconciles_original_unknown_unrun() {
        let epoch=[179;16];
        let command=json!({"cmd":"batch","action":"portrait_preset_export_start","request_id":"start-reconcile",
            "preflight_token":"f".repeat(32),"batch_id":"batch-a","plan_id":"e".repeat(64),"intent_revision":4});
        let mut host=BatchHost::default();host.reset(epoch);host.ready(epoch,true);
        host.begin_command(epoch,&command).unwrap();crate::project_recovery_fence::issued(epoch,&command).unwrap();
        let mut reply=command.clone();reply.as_object_mut().unwrap().remove("cmd");
        reply["event"]=json!("batch_result");reply["portrait_preset"]=json!(true);reply["delivery"]=json!(true);
        reply["success"]=json!(false);reply["outcome_unknown"]=json!(true);reply["error"]=json!("original task pending readback");
        reply["export_task_id"]=json!("task-a");host.receive(epoch,&reply);
        assert_eq!(host.status("start-reconcile")["result"]["export_task_id"],"task-a");
        let query=json!({"cmd":"batch","action":"portrait_preset_export_status","request_id":"readback-a",
            "preflight_token":"f".repeat(32),"batch_id":"batch-a","task_id":"task-a"});
        assert!(crate::project_recovery_fence::issued(epoch,&query).is_ok());
        let mut foreign=query.clone();foreign["batch_id"]=json!("other-batch");assert!(crate::project_recovery_fence::issued(epoch,&foreign).is_err());
        reply.as_object_mut().unwrap().remove("error");reply["success"]=json!(true);reply["outcome_unknown"]=json!(false);
        reply["export_reconciled"]=json!(true);reply["export_status"]=json!("running");reply["items"]=json!([{"document_id":"a","state":"pending"}]);
        reply["export_task_id"]=json!("task-b");host.receive(epoch,&reply);assert!(crate::project_recovery_fence::proof(epoch).is_err());
        reply["export_task_id"]=json!("task-a");host.receive(epoch,&reply);assert!(crate::project_recovery_fence::proof(epoch).is_ok());
        assert_eq!(host.status("start-reconcile")["result"]["export_status"],"running");
    }
    fn compact_fixture() -> Value {
        json!({"mime":"image/png","width":8,"height":8,"sha256":"a".repeat(64),"byte_length":99,"page_count":1})
    }
    fn plan() -> Value {
        json!({"request_id":"group-plan","action":"portrait_preset_preflight","success":true,"portrait_preset":true,
            "preflight_token":"f".repeat(32),"preset_id":"skin","preset_sha256":"e".repeat(64),
            "module_scope":["lnx.skin.v1"],"targets":[{"document_id":"target","revision":"2","path":"/target.png",
                "before":compact_fixture(),"after":compact_fixture(),"review_sha256":"b".repeat(64)}]})
    }
    // AUTHORED / UNRUN: preparation may retain successful earlier targets,
    // but only the complete exact receipt + restored editor settles recovery.
    #[test]
    fn preparation_partial_identity_and_editor_restore_are_required_unrun(){
        let command=json!({"cmd":"batch","action":"portrait_preset_prepare","request_id":"prepare-group",
            "docs":["a","b"],"preset_id":"skin","preset_sha256":"e".repeat(64)});
        let mut value=json!({"event":"batch_result","action":"portrait_preset_prepare","request_id":"prepare-group",
            "portrait_preset":true,"preparation":true,"success":false,"outcome_unknown":false,
            "preset_id":"skin","preset_sha256":"e".repeat(64),"portrait_preset_docs":["a","b"],
            "editor_restored":true,"error":"second target failed","preparation_results":[
                {"document_id":"a","status":"prepared"},{"document_id":"b","status":"failed","error":"no face"}]});
        assert!(mutation(&command));assert!(receipt(&value));assert!(matches_request(&command,&value));
        value["editor_restored"]=json!(false);assert!(!matches_request(&command,&value));
        value["editor_restored"]=json!(true);value["outcome_unknown"]=json!(true);assert!(!matches_request(&command,&value));
        value["outcome_unknown"]=json!(false);value["portrait_preset_docs"]=json!(["b","a"]);assert!(!receipt(&value));
        let mut good=plan();good["action"]=json!("portrait_preset_prepare");good["preparation"]=json!(true);
        good["outcome_unknown"]=json!(false);good["editor_restored"]=json!(true);good["portrait_preset_docs"]=json!(["target"]);
        good["preparation_results"]=json!([{"document_id":"target","status":"prepared"}]);assert!(receipt(&good));
        for key in ["preparation","outcome_unknown","editor_restored","portrait_preset_docs","preparation_results"]{
            let mut bad=good.clone();bad.as_object_mut().unwrap().remove(key);assert!(!receipt(&bad),"{key}");
        }
        good["preparation_results"][0]["status"]=json!("not_started");assert!(!receipt(&good));
    }
    #[test]
    fn group_target_completeness_and_compact_bounds_are_required_unrun() {
        let good=plan(); assert!(receipt(&good));
        for path in ["/targets/0/revision","/targets/0/review_sha256","/targets/0/before/sha256","/targets/0/after/page_count"] {
            let mut bad=good.clone(); *bad.pointer_mut(path).unwrap()=Value::Null; assert!(!receipt(&bad),"{path}");
        }
        let mut duplicated=good.clone(); let row=duplicated["targets"][0].clone();
        duplicated["targets"].as_array_mut().unwrap().push(row); assert!(!receipt(&duplicated));
    }
    #[test]
    fn wrong_target_cannot_settle_original_preflight_unrun() {
        let mut host=BatchHost::default(); host.reset([4;16]); host.ready([4;16],true);
        host.begin_command([4;16], &json!({"cmd":"batch","request_id":"group-plan","action":"portrait_preset_preflight",
            "docs":["original-target"],"preset_id":"skin","preset_sha256":"e".repeat(64)})).unwrap();
        host.receive([4;16],&plan());
        assert_eq!(host.status("group-plan")["result"]["outcome_unknown"],true);
    }
    #[test]
    fn commit_receipt_requires_all_original_acks_and_keeps_unknown_locked_unrun() {
        let ack=json!([{"document_id":"target","revision":"2","before_sha256":"a".repeat(64),
            "after_sha256":"a".repeat(64),"review_sha256":"b".repeat(64)}]);
        let command=json!({"cmd":"batch","request_id":"group-commit","action":"portrait_preset_commit",
            "preflight_token":"f".repeat(32),"accepted":true,"portrait_preset_ack":ack});
        let mut host=BatchHost::default(); host.reset([4;16]); host.ready([4;16],true);
        host.begin_command([4;16],&command).unwrap();
        let mut result=json!({"request_id":"group-commit","action":"portrait_preset_commit","success":true,
            "portrait_preset":true,"preflight_token":"f".repeat(32),"portrait_preset_ack":ack,
            "batch_id":"group-batch","workspace_generation":"d".repeat(32),"delivery_targets":[{"document_id":"target","revision":"3"}],"module_scope":["lnx.skin.v1"],"targets":[1],"skipped":[],"rejected_docs":[]});
        assert!(receipt(&result));
        result["portrait_preset_ack"][0]["after_sha256"]=json!("c".repeat(64));
        host.receive([4;16],&result);
        assert_eq!(host.status("group-commit")["result"]["outcome_unknown"],true);
        assert!(host.guards_review([4;16],"group-commit"));
        assert_eq!(host.status("group-commit")["result"]["portrait_preset_ack"],command["portrait_preset_ack"]);
    }
}
