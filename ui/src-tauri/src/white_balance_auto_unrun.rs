//! AUTHORED / UNRUN. Native identity/fence specifications, not acceptance results.
use super::*;
fn request(id:&str)->Value {json!({"cmd":"white_balance","action":"auto","request_id":id,"document_id":"doc",
    "input_id":"a".repeat(64),"recipe_document_id":"recipe","recipe_revision":"7"})}
fn exposure_state()->Value {json!({"ev":1.0,"temperature_shift":500.0,"tint_shift":0.2,"contrast":10.0,"highlights":20.0,
    "shadows":30.0,"saturation":40.0,"reference_k":null,"lit":true,
    "options":{"version":1,"algorithm":ALGORITHMS[0],"picked_gains":[1.0,1.0,1.0]}})}
fn success(command:&Value)->Value {
    let before=exposure_state();let mut after=before.clone();after["options"]["picked_gains"]=json!([1.2,1.0,0.85]);
    json!({"event":"white_balance_result","protocol":1,"request_id":command["request_id"],"document_id":"doc","action":"auto",
        "original_request":command,"success":true,"outcome_unknown":false,"requires_reload":false,"phase":"applied","no_write":false,"no_change":false,
        "before":before,"after":after,"history_limit":64,"before_history":{"undo_steps":2,"redo_steps":1},"history":{"undo_steps":3,"redo_steps":0},
        "diagnostic":{"origin":"classic-statistical-estimate","policy":"stratified-trimmed-log-gray-world-v1",
            "domain":"pre-wb-linear-working-srgb","quality":"current-proxy-stratified","samples":1024,"accepted":1024,
            "stable_tiles":16,"spread":0.0,"illuminant":[0.8,1.0,1.2]}})
}
fn rejected(command:&Value)->Value {json!({"event":"white_balance_result","protocol":1,
    "request_id":command["request_id"],"document_id":command["document_id"],"action":"auto","original_request":command,
    "success":false,"outcome_unknown":false,"requires_reload":false,"phase":"rejected","no_write":true,
    "authority":"native-admission","error":"not enqueued: another owner already holds this ID"})}
#[test] fn exact_auto_binding_has_no_manual_picker_claim(){
    let command=request("auto-owner");let result=success(&command);
    assert!(crate::white_balance_api::matches_request(&command,&result));
    for key in ["capture_id","ticket","generation","region"] {assert!(result.get(key).is_none());}
    let mut h=WhiteBalanceHost::default();h.reset([241;16]);h.ready([241;16],true);h.begin_command([241;16],&command).unwrap();
    let mut wrong=result.clone();wrong["original_request"]["recipe_revision"]=json!("8");h.receive([241;16],&wrong);
    assert_eq!(h.status("auto-owner")["result"]["outcome_unknown"],true);
    h.receive([241;16],&result);assert_eq!(h.status("auto-owner")["result"]["outcome_unknown"],true); // No late overwrite.
}
#[test] fn successful_estimate_must_preserve_manual_algorithm_reference_and_exposure(){
    let command=request("auto-preserve");let result=success(&command);
    for key in ["ev","temperature_shift","tint_shift","contrast","highlights","shadows","saturation","reference_k"] {
        let mut changed=result.clone();changed["after"][key]=json!(123.0);assert!(!WhiteBalanceKind::valid(&changed,Some("doc")),"{key}");
    }
    let mut changed=result;changed["after"]["options"]["algorithm"]=json!(ALGORITHMS[1]);assert!(!WhiteBalanceKind::valid(&changed,Some("doc")));
}
#[test] fn rollback_requires_exact_recipe_and_history_and_unknown_stays_pinned(){
    let command=request("auto-rollback");let mut value=success(&command);
    value["success"]=json!(false);value["phase"]=json!("rolled_back");value["no_write"]=json!(true);value["error"]=json!("render failed; exact rollback verified");
    assert!(!WhiteBalanceKind::valid(&value,Some("doc")));
    value["after"]=value["before"].clone();value["history"]=value["before_history"].clone();
    assert!(WhiteBalanceKind::valid(&value,Some("doc")));
    let mut h=WhiteBalanceHost::default();h.reset([242;16]);h.ready([242;16],true);
    for i in 0..crate::receipt_host::MAX_RECORDS {
        let id=format!("auto-unknown-{i}");h.begin_command([242;16],&request(&id)).unwrap();h.failed(&id,"transport unknown");
    }
    assert!(h.begin_command([242;16],&request("cannot-evict-unknown")).is_err());
}
#[test] fn unrelated_result_or_bare_reopen_cannot_settle_original_auto_fence(){
    let epoch=[243;16];let command=request("auto-fence");let result=success(&command);
    crate::project_recovery_fence::issued(epoch,&command).unwrap();
    crate::project_recovery_fence::observed(epoch,&json!({"event":"exposure_done","request_id":"auto-fence","success":true}));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    let mut wrong=result.clone();wrong["original_request"]["input_id"]=json!("b".repeat(64));
    crate::project_recovery_fence::observed(epoch,&wrong);assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&result);assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn native_auto_no_write_collision_cannot_clear_or_mask_other_owner(){
    for (epoch,other,event) in [([244;16],json!({"cmd":"exposure","request_id":"collision","ev":1.0}),"exposure_done"),
        ([245;16],json!({"cmd":"white_balance","action":"reset","request_id":"collision","document_id":"doc"}),"white_balance_result")] {
        crate::project_recovery_fence::issued(epoch,&other).unwrap();
        let command=request("collision");let mut host=WhiteBalanceHost::default();host.reset(epoch);host.ready(epoch,true);
        host.begin_command(epoch,&command).unwrap();
        assert!(crate::project_recovery_fence::issued(epoch,&command).is_err());
        host.receive(epoch,&rejected(&command));
        assert_eq!(host.status("collision")["result"]["outcome_unknown"],false);
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        assert!(!host.guards_auto_white_balance(epoch,"collision")); // RX must allow rightful terminal through.
        crate::project_recovery_fence::observed(epoch,&json!({"event":event,"request_id":"collision","action":"reset",
            "success":false,"outcome_unknown":false,"requires_reload":false,"error":"other owner's safe rejection"}));
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    }
}
#[test] fn malformed_auto_may_poison_only_exact_current_auto_not_manual_or_new_epoch(){
    let command=request("same-id");let value=success(&command);
    let mut host=WhiteBalanceHost::default();host.reset([247;16]);host.ready([247;16],true);
    host.begin_command([247;16],&command).unwrap();
    host.failed_bound_auto_white_balance([246;16],&value,"buffered malformed old engine");
    assert_eq!(host.status("same-id")["phase"],"pending");
    let mut wrong=value.clone();wrong["original_request"]["input_id"]=json!("b".repeat(64));
    host.failed_bound_auto_white_balance([247;16],&wrong,"wrong original request");
    assert_eq!(host.status("same-id")["phase"],"pending");
    host.failed_bound_auto_white_balance([247;16],&value,"bound current malformed record");
    assert_eq!(host.status("same-id")["result"]["outcome_unknown"],true);
    host.reset([248;16]);host.ready([248;16],true);host.begin_bound([248;16],"same-id","reset",Some("doc")).unwrap();
    host.failed_bound_auto_white_balance([247;16],&value,"old auto engine after reset");
    host.failed_bound_auto_white_balance([248;16],&value,"auto event names a manual request");
    assert_eq!(host.status("same-id")["phase"],"pending");
}
#[test] fn applied_auto_requires_actual_capped_undo_increment_and_cleared_redo(){
    let command=request("auto-history-cap");let mut value=success(&command);
    value["history"]["redo_steps"]=json!(1);assert!(!WhiteBalanceKind::valid(&value,Some("doc")));
    value["history"]["redo_steps"]=json!(0);value["history"]["undo_steps"]=json!(2);
    assert!(!WhiteBalanceKind::valid(&value,Some("doc")));
    value["before_history"]["undo_steps"]=json!(64);value["history"]["undo_steps"]=json!(64);
    assert!(WhiteBalanceKind::valid(&value,Some("doc")));
    value["history"]["undo_steps"]=json!(65);assert!(!WhiteBalanceKind::valid(&value,Some("doc")));
    value["history_limit"]=Value::Null;assert!(!WhiteBalanceKind::valid(&value,Some("doc")));
}
#[test] fn creating_empty_project_does_not_restore_unknown_live_auto_or_flip(){
    for (epoch,command) in [([249;16],request("auto-create-is-not-restore")),([250;16],json!({"cmd":"final_canvas_flip", "request_id":"flip-create-is-not-restore",
        "document_id":"doc","revision":"7","horizontal":true,"vertical":false}))] {
        crate::project_recovery_fence::issued(epoch,&command).unwrap();
        assert!(crate::project_recovery_fence::issued(epoch,&json!({"cmd":"project","action":"create","name":"new","directory":"/fixture"})).is_err());
        crate::project_recovery_fence::observed(epoch,&json!({"event":"project_created","open":true,"path":"/fixture/new.lrt","project_id":"new","docs":1,"dirty":true}));
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened","open":true,"path":"/fixture/confirmed.lrt","project_id":"confirmed","docs":1,"dirty":false}));
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    }
    assert!(crate::project_recovery_fence::issued([251;16],&json!({"cmd":"project","action":"create","name":"clean","directory":"/fixture"})).is_ok());
}
