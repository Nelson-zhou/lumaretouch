//! AUTHORED / UNRUN. These fixtures have not been compiled or executed.
use super::*;
fn command(action: &str) -> Value {
    json!({"cmd":"people","request_id":"read-request","action":action,"payload":{},
        "document_id":"d".repeat(32),"document_epoch":"epoch","document_revision":7,
        "state_revision":11,"association_revision":3,
        "target":{"scope":"face","target_id":"face","face_ref":{"asset_sha256":"a".repeat(64),
            "face_instance_id":"face","analysis_revision":2}}})
}
fn host() -> ReceiptHost<PeopleKind> {
    let mut h = ReceiptHost::default(); h.reset([3;16]); h.ready([3;16],true); h
}
fn cancelled(c: &Value) -> Value {
    let mut request = c.clone(); request.as_object_mut().unwrap().remove("cmd");
    request.as_object_mut().unwrap().remove("request_id");
    json!({"event":"people_result","protocol":1,"request_id":c["request_id"],"action":c["action"],
        "document_id":c["document_id"],"success":false,"outcome_unknown":false,
        "eye_bag_cancelled":true,"error":"Read-only work stopped after cancellation",
        "eye_bag_request":request})
}
#[test] fn pending_read_proof_is_queryable_without_mutating_receipt() {
    let mut h=host(); let c=command("eye_bag_reference"); h.begin_command([3;16],&c).unwrap();
    let before=h.status("read-request"); let proof=eye_read_request(&h,"read-request").unwrap();
    assert_eq!(proof["action"],"eye_bag_reference"); assert_eq!(h.status("read-request"),before);
    assert!(!settled_read(&before)); assert!(eye_read_request(&h,"missing").is_err());
}
#[test] fn generic_write_and_confirmation_never_supply_read_control_proof() {
    let mut h=host(); h.begin_bound([3;16],"write","patch",Some("document")).unwrap();
    assert!(eye_read_request(&h,"write").is_err());
    let mut c=command("eye_bag_confirm"); c["request_id"]=json!("confirm");
    c["payload"]=json!({"token":"b".repeat(32),"ack":{"review_sha256":"c".repeat(64),
        "before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64),"support_overlay_sha256":"f".repeat(64)}});
    h.begin_command([3;16],&c).unwrap(); assert!(eye_read_request(&h,"confirm").is_err());
}
#[test] fn ended_read_retains_original_query_proof_not_cancellation_success() {
    let mut h=host(); h.begin_command([3;16],&command("eye_bag_reference")).unwrap(); h.ended([3;16]);
    assert!(eye_read_request(&h,"read-request").is_ok());
    let result=h.status("read-request"); assert_eq!(result["result"]["outcome_unknown"],true);
    assert!(!settled_read(&result)); assert!(result["result"].get("eye_bag_cancelled").is_none());
}
#[test] fn canceled_terminal_requires_failed_exact_read_and_no_write_evidence() {
    let c=command("eye_bag_reference"); let good=cancelled(&c);
    assert!(eye_bag::receipt(&good)); assert!(PeopleKind::valid(&good,c["document_id"].as_str()));
    for (key,value) in [("success",json!(true)),("outcome_unknown",json!(true)),("eye_bag_cancelled",json!(false)),
        ("doc_state",json!({})),("payload",json!({})),("committed",json!(false))] {
        let mut bad=good.clone(); bad[key]=value; assert!(!eye_bag::receipt(&bad),"{key}");
    }
    let mut bad=good.clone(); bad["eye_bag_request"]["document_revision"]=json!(8);
    let mut h=host();h.begin_command([3;16],&c).unwrap();h.receive([3;16],&bad);
    assert_ne!(h.status("read-request")["result"],good);
}
#[test] fn confirmed_cancel_is_terminal_but_read_success_is_not_labeled_canceled() {
    let mut h=host();let c=command("eye_bag_reference");h.begin_command([3;16],&c).unwrap();
    h.receive([3;16],&cancelled(&c));assert!(settled_read(&h.status("read-request")));
    assert_eq!(h.status("read-request")["result"]["eye_bag_cancelled"],true);
    let status=json!({"phase":"done","result":{"success":true,"outcome_unknown":false}});
    assert!(settled_read(&status));assert!(status["result"].get("eye_bag_cancelled").is_none());
}
#[test] fn unknown_read_reconciles_only_matching_actual_canceled_terminal() {
    let mut h=host();let c=command("eye_bag_reference");h.begin_command([3;16],&c).unwrap();h.failed("read-request","transport uncertain");
    let unknown=h.status("read-request");assert!(!settled_read(&unknown));
    let mut bad=cancelled(&c);bad["eye_bag_request"]["document_revision"]=json!(8);
    h.receive([3;16],&bad);assert_eq!(h.status("read-request"),unknown);
    h.receive([4;16],&cancelled(&c));assert_eq!(h.status("read-request"),unknown);
    h.receive([3;16],&cancelled(&c));assert!(settled_read(&h.status("read-request")));
    let done=h.status("read-request");h.receive([3;16],&bad);assert_eq!(h.status("read-request"),done);
}
#[test] fn unknown_confirmation_never_reconciles_through_read_cancellation() {
    let mut h=host();let mut c=command("eye_bag_confirm");
    c["payload"]=json!({"token":"b".repeat(32),"ack":{"review_sha256":"c".repeat(64),
        "before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64),"support_overlay_sha256":"f".repeat(64)}});
    h.begin_command([3;16],&c).unwrap();h.failed("read-request","unknown write");let old=h.status("read-request");
    h.receive([3;16],&cancelled(&c));assert_eq!(h.status("read-request"),old);
    assert!(eye_read_request(&h,"read-request").is_err());
}
/// Original one-pixel RGB transport fixture, not generated image evidence.
fn png() -> Value {
    use base64::{engine::general_purpose::STANDARD,Engine as _};use sha2::{Digest,Sha256};
    fn chunk(bytes:&mut Vec<u8>,kind:&[u8],data:&[u8]) {
        bytes.extend_from_slice(&(data.len() as u32).to_be_bytes());let start=bytes.len();
        bytes.extend_from_slice(kind);bytes.extend_from_slice(data);let mut crc=0xffff_ffffu32;
        for b in &bytes[start..] {crc^=u32::from(*b);for _ in 0..8 {crc=(crc>>1)^((0u32.wrapping_sub(crc&1))&0xedb8_8320);}}
        bytes.extend_from_slice(&(!crc).to_be_bytes());
    }
    let mut bytes=b"\x89PNG\r\n\x1a\n".to_vec();
    chunk(&mut bytes,b"IHDR",&[0,0,0,1,0,0,0,1,8,2,0,0,0]);
    chunk(&mut bytes,b"IDAT",&[0x78,0x01,0x01,4,0,0xfb,0xff,0,32,64,96,0x01,0x44,0x00,0xc1]);
    chunk(&mut bytes,b"IEND",&[]);
    json!({"mime":"image/png","width":1,"height":1,"sha256":format!("{:x}",Sha256::digest(&bytes)),"base64":STANDARD.encode(bytes)})
}
#[test] fn unknown_read_can_reconcile_real_success_without_claiming_cancellation() {
    let mut h=host();let mut c=command("eye_bag_source_image");let image=png();
    c["payload"]=json!({"token":"b".repeat(32),"side":"left","sha256":image["sha256"]});
    h.begin_command([3;16],&c).unwrap();h.failed("read-request","transport uncertain");
    let mut good=cancelled(&c);good.as_object_mut().unwrap().remove("eye_bag_cancelled");good.as_object_mut().unwrap().remove("error");good["success"]=json!(true);
    good["payload"]=json!({"kind":"eye_bag_source_image","token":"b".repeat(32),"side":"left","snapshot_sha256":"d".repeat(64),"image":image});
    h.receive([3;16],&good);assert_eq!(h.status("read-request")["result"],good);
    assert!(settled_read(&h.status("read-request")));
}
