// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Native owner isolation and causal replacement fixtures.
use super::*;
fn smoothing(id: &str) -> Value {
    json!({"cmd":"people","request_id":id,"action":"patch","document_id":"doc","document_epoch":"workspace",
        "document_revision":1,"state_revision":1,"association_revision":0,
        "target":{"scope":"face","target_id":"face","face_ref":{"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":1}},
        "payload":{"patches":[{"operation_id":"lnx.hair_smoothing.v1","parameter_path":"/amount","unset":false,"value":0}]}})
}
fn terminal(command:&Value, smoothing:bool) -> Value {
    let mut value=json!({"event":"people_result","protocol":1,"request_id":command["request_id"],"action":"patch",
        "document_id":"doc","success":false,"outcome_unknown":false,"error":"prewrite refusal","frame_emitted":false});
    if smoothing {value[hair_smoothing::MARKER]=hair_smoothing::binding(command).unwrap().unwrap()[hair_smoothing::MARKER].clone();}
    value
}
fn host(epoch:[u8;16]) -> ReceiptHost<PeopleKind> {
    let mut host=ReceiptHost::default();host.reset(epoch);host.ready(epoch,true);host
}
#[test] fn foreign_smoothing_terminal_does_not_settle_ordinary_patch_or_reverse() {
    let epoch=[213;16];let command=smoothing("collision");let foreign=terminal(&command,true);
    let mut ordinary=host(epoch);ordinary.begin_bound(epoch,"collision","patch",Some("doc")).unwrap();
    ordinary.receive(epoch,&foreign);assert_eq!(ordinary.status("collision")["phase"],"pending");
    let rightful=terminal(&command,false);ordinary.receive(epoch,&rightful);
    assert_eq!(ordinary.status("collision")["result"],rightful);
    let mut owned=host(epoch);owned.begin_command(epoch,&command).unwrap();
    owned.receive(epoch,&rightful);assert_eq!(owned.status("collision")["phase"],"pending");
    owned.receive(epoch,&foreign);assert_eq!(owned.status("collision")["result"],foreign);
}
#[test] fn reverse_collision_cannot_release_cross_domain_fence() {
    let epoch=[214;16];let mut ordinary=smoothing("fence-collision");
    ordinary["payload"]["patches"][0]["operation_id"]=json!("lnx.enhance.v1");
    ordinary["payload"]["patches"][0]["parameter_path"]=json!("/eye_light");
    crate::project_recovery_fence::issued(epoch,&ordinary).unwrap();
    crate::project_recovery_fence::observed(epoch,&terminal(&smoothing("fence-collision"),true));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&terminal(&ordinary,false));
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn ordinary_patch_terminal_cannot_release_smoothing_fence() {
    let epoch=[218;16];let command=smoothing("smoothing-fence-owner");
    crate::project_recovery_fence::issued(epoch,&command).unwrap();
    crate::project_recovery_fence::observed(epoch,&terminal(&command,false));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&terminal(&command,true));
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn earlier_buffered_open_admission_and_busy_queue_never_abandon() {
    let epoch=[215;16];let command=smoothing("causal-open");let mut host=host(epoch);
    host.begin_command(epoch,&command).unwrap();
    let idle=json!({"pending":0,"in_flight":false,"closed":false});
    assert!(host.hair_smoothing_recovery("causal-open",epoch,epoch,4,&idle).is_none()); // admission unfinished
    host.hair_smoothing_admission_finished("causal-open");
    let busy=json!({"pending":0,"in_flight":true,"closed":false});
    assert!(host.hair_smoothing_recovery("causal-open",epoch,epoch,4,&busy).is_none());
    // Earlier open is already consumed before this first unresolved+idle query.
    assert!(host.hair_smoothing_recovery("causal-open",epoch,epoch,4,&idle).is_none());
    assert!(host.hair_smoothing_recovery("causal-open",epoch,epoch,4,&idle).is_none()); // refresh/timeout not authority
    assert!(host.hair_smoothing_recovery("causal-open",epoch,epoch,5,&busy).is_none());
    let proof=host.hair_smoothing_recovery("causal-open",epoch,epoch,5,&idle).unwrap();
    assert_eq!(proof["previous_outcome"],"unknown");assert_eq!(proof[hair_smoothing::MARKER],hair_smoothing::binding(&command).unwrap().unwrap()[hair_smoothing::MARKER]);
    host.receive(epoch,&terminal(&command,true));assert_eq!(host.status("causal-open")["phase"],"pending"); // late outcome not relabelled
}
#[test] fn exact_old_engine_can_be_abandoned_only_when_replacement_queue_is_idle() {
    let epoch=[216;16];let command=smoothing("new-engine");let mut host=host(epoch);
    host.begin_command(epoch,&command).unwrap();host.hair_smoothing_admission_finished("new-engine");
    let idle=json!({"pending":0,"in_flight":false,"closed":false});
    assert!(host.hair_smoothing_recovery("new-engine",[0;16],[217;16],2,&idle).is_none());
    assert!(host.hair_smoothing_recovery("new-engine",epoch,[217;16],2,&json!({"pending":1,"in_flight":false,"closed":false})).is_none());
    assert!(host.hair_smoothing_recovery("new-engine",epoch,[217;16],2,&idle).is_some());
    let mut ordinary=host_for_ordinary(epoch); // No tagged owner means no retirement authority.
    assert!(ordinary.hair_smoothing_recovery("ordinary",epoch,[217;16],2,&idle).is_none());
}
fn host_for_ordinary(epoch:[u8;16])->ReceiptHost<PeopleKind>{let mut h=host(epoch);h.begin_bound(epoch,"ordinary","patch",Some("doc")).unwrap();h}
