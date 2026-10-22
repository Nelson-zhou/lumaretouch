use super::*;
const CAPTURE: &str = "0123456789abcdef0123456789abcdef";
const RECIPE: &str = "11111111111111111111111111111111";
fn host() -> ColorPickerCaptureHost {
    let mut host = ColorPickerCaptureHost::default(); host.reset([1;16]); host.ready([1;16], true); host
}
fn begin(host: &mut ColorPickerCaptureHost) -> String {
    host.begin([1;16], CAPTURE.into(), "123".into(), 4, "curve".into(), "red".into()).unwrap()
}
fn event(ticket: &str) -> Value {
    json!({"event":"color_picker_capture", "action":"arm", "capture_id":CAPTURE,"ticket":ticket,"success":true,
        "descriptor":{"version":1,"capture_id":CAPTURE,"ticket":ticket,"document_id":"123","generation":"7","seq":"1",
            "epoch":hex([1;16]),"shm_instance":"22222222222222222222222222222222","width":2,"height":2,
            "presentation_width":2,"presentation_height":2,"recipe_document_id":RECIPE,"recipe_revision":"0",
            "domain":"color-action-input","quality":"proxy-float-input","profile":"working-srgb","full_source":[20,20],
            "picker_action":"curve","picker_channel":"red","source_stage":"curve-red-input",
            "projection":{"version":"crop-rotate-fixed-proxy-v1","source_proxy":[2,2],"rect":[0.,0.,1.,1.],
                "integer_crop":[0,0,2,2],"rotation":0.,"quarter_turn":0,"rotated":[2,2],"target":[2,2],
                "resize":"bilinear","align_corners":false,"antialias":false}}})
}
fn eligible(host: &mut ColorPickerCaptureHost, ticket: &str) -> Proof {
    host.armed_event([1;16], &event(ticket), 4);
    let identity = host.begin_copy(CAPTURE, ticket).unwrap();
    host.finish_copy(&identity, None).unwrap(); host.confirm_copied(&identity).unwrap();
    host.presented(CAPTURE, ticket, "123").unwrap()
}
#[test]
fn targeted_stage_action_channel_and_all_proof_fields_fail_closed() {
    for (key, wrong) in [("picker_action",json!("hsl")),("picker_channel",json!("blue")),
        ("source_stage",json!("proxy-output")),("domain",json!("wb-input")),("quality",json!("proxy-linear-input")),
        ("epoch",json!(hex([2;16]))),("generation",json!("07")),("recipe_document_id",json!("invalid")),
        ("recipe_revision",json!("00")),("presentation_width",json!(0)),("width",json!(0))] {
        let mut host = host(); let ticket = begin(&mut host); let mut value = event(&ticket);
        value["descriptor"][key] = wrong; host.armed_event([1;16], &value, 4);
        assert_eq!(host.status_for(CAPTURE, &ticket)["phase"], "error", "{key}");
        assert!(host.begin_copy(CAPTURE, &ticket).is_err());
    }
}
#[test]
fn late_duplicate_arm_and_old_epoch_cannot_replace_a_new_ticket() {
    let mut host = host(); let old = begin(&mut host); let fresh = begin(&mut host);
    assert_ne!(old, fresh);
    host.armed_event([1;16], &event(&old), 4);
    host.armed_event([2;16], &event(&fresh), 4);
    assert_eq!(host.status_for(CAPTURE, &fresh)["phase"], "arming");
    host.armed_event([1;16], &event(&fresh), 4);
    assert_eq!(host.status_for(CAPTURE, &fresh)["phase"], "ready");
    let mut duplicate = event(&fresh); duplicate["descriptor"]["generation"] = json!("8");
    host.armed_event([1;16], &duplicate, 4);
    assert_eq!(host.status_for(CAPTURE, &fresh)["descriptor"]["generation"], "7");
    assert!(host.cancel(CAPTURE, Some(&old), "123").is_none());
    host.reset([2;16]); host.ready([1;16], true);
    assert!(host.begin([1;16], CAPTURE.into(), "123".into(), 4, "curve".into(), "red".into()).is_err());
}
#[test]
fn copy_then_presentation_are_required_and_redemption_is_one_shot() {
    let mut host = host(); let ticket = begin(&mut host);
    host.armed_event([1;16], &event(&ticket), 4);
    assert!(host.presented(CAPTURE, &ticket, "123").is_err());
    assert!(host.eligible_proof([1;16], CAPTURE, &ticket).is_err());
    let identity = host.begin_copy(CAPTURE, &ticket).unwrap();
    assert!(host.presented(CAPTURE, &ticket, "123").is_err());
    host.finish_copy(&identity, None).unwrap(); host.confirm_copied(&identity).unwrap();
    assert!(host.presented(CAPTURE, &ticket, "124").is_err());
    host.presented(CAPTURE, &ticket, "123").unwrap();
    assert!(host.eligible_proof([2;16], CAPTURE, &ticket).is_err());
    assert_eq!(host.redeem([1;16], CAPTURE, &ticket).unwrap().identity, identity);
    assert!(host.redeem([1;16], CAPTURE, &ticket).is_err());
    assert!(host.presented(CAPTURE, &ticket, "123").is_err());
}
#[test]
fn cancellation_does_not_release_an_inflight_copy_lease() {
    let mut host = host(); let ticket = begin(&mut host); host.armed_event([1;16], &event(&ticket), 4);
    let old = host.begin_copy(CAPTURE, &ticket).unwrap();
    host.cancel(CAPTURE, Some(&ticket), "123");
    let fresh = begin(&mut host); host.armed_event([1;16], &event(&fresh), 4);
    assert!(host.begin_copy(CAPTURE, &fresh).is_err());
    assert!(host.finish_copy(&old, None).is_err());
    let next = host.begin_copy(CAPTURE, &fresh).unwrap();
    assert!(host.finish_copy(&old, None).is_err());
    assert!(host.begin_copy(CAPTURE, &fresh).is_err());
    host.finish_copy(&next, None).unwrap();
    assert!(host.confirm_copied(&old).is_err()); host.confirm_copied(&next).unwrap();
}
#[test]
fn committed_receipt_survives_capture_cancellation_and_retains_full_binding() {
    let mut capture = host(); let ticket = begin(&mut capture); let proof = eligible(&mut capture, &ticket);
    let command = json!({"request_id":"commit", "document_id":"123","capture_id":CAPTURE,"ticket":ticket,
        "generation":proof.identity.generation.to_string(),"recipe_document_id":RECIPE,"recipe_revision":"0",
        "action":"curve","channel":"red","region":{"x":0,"y":0,"width":1,"height":1},"delta":0.1});
    let bound = crate::color_picker_host::binding(&command).unwrap();
    let mut receipts = crate::color_picker_host::ColorPickerHost::default();
    receipts.reset([1;16]); receipts.ready([1;16], true);
    receipts.begin_bound([1;16], "commit", "curve", Some(&bound)).unwrap();
    capture.redeem([1;16], CAPTURE, &ticket).unwrap(); capture.cancel(CAPTURE, Some(&ticket), "123");
    assert_eq!(receipts.status("commit")["phase"], "pending");
    receipts.ended([1;16]);
    let result = receipts.status("commit");
    assert_eq!(result["result"]["outcome_unknown"], true);
    assert_eq!(result["result"]["capture_id"], CAPTURE);
    assert_eq!(result["result"]["channel"], "red");
}
