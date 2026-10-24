// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Synthetic protocol/geometry fixtures are not photo acceptance.
//! No tests, compiler, product imports, model inference or native execution ran.
use super::*;

fn source_hash()->Value{json!("a".repeat(64))}
fn target()->Value{json!({"asset_sha256":source_hash(),"body_instance_id":"body:actual","analysis_revision":2})}
fn owner()->Value{json!({"document_id":"doc:actual","document_epoch":"doc-epoch","document_revision":7,"asset_sha256":source_hash()})}
fn draft()->Value{json!({"version":1,"method":"user-traced-complete-person-silhouette-v1",
 "outline":[[0.46,0.24],[0.54,0.24],[0.60,0.30],[0.60,0.70],[0.54,0.76],[0.46,0.76],[0.40,0.70],[0.40,0.30]],
 "collar_box":[0.10,0.05,0.90,0.95],"confirmations":SUPPORT_FLAGS.iter().map(|key|((*key).to_owned(),json!(true))).collect::<serde_json::Map<_,_>>()})}
fn bound_support()->Value{
 let mut value=draft();value["associated_face_ref"]=json!({"asset_sha256":source_hash(),"face_instance_id":"face:actual","analysis_revision":3});
 value["associated_face_box"]=json!([0.46,0.26,0.54,0.33]);value["associated_face_evidence_sha256"]=json!("b".repeat(64));value
}
fn support_payload()->Value{json!({"data":draft(),"points_sha256":"c".repeat(64),"visible_anchors":(0..33).collect::<Vec<_>>(),"ownership_confirmed":true})}
fn edit_request()->Value{json!({"request_id":"inner:actual","gesture_id":"gesture:actual","document_id":"doc:actual","document_epoch":"doc-epoch","document_revision":7,
 "state_revision":8,"association_revision":2,"people_association_revision":3,"body_ref":target(),"body_graph_sha256":"d".repeat(64),"people_graph_sha256":"e".repeat(64),
 "operation_id":"lnx.body_slim.v1","action":"recipe","payload":{"base":{"version":1,"amount":0},"recipe":{"version":1,"amount":-0.5}}})}
fn current_view()->Value{json!({"binding":owner(),"state_revision":8,"association_revision":2,"people_association_revision":3,
 "body_graph_sha256":"d".repeat(64),"people_graph_sha256":"e".repeat(64),"selected_body_ref":target(),"recipe":{"version":1,"amount":0},"refusals":[],
 "bodies":[{"body_ref":target(),"enabled":true,"operation_enabled":true,"reviewed":true,"support":bound_support(),
 "points_sha256":"c".repeat(64),"source":{"sha256":source_hash(),"width":1001,"height":1601,"orientation":"exif_normalized_once"},
 "association":{"person_id":"person:actual","body_ref":target(),"people_association_revision":3,"confirmation_revision":2},
 "points":(0..33).map(|index|json!({"index":index,"x":0.5,"y":0.5,"z":0,"visibility":0.99,"presence":0.99})).collect::<Vec<_>>()}]})}
fn source_preview()->Value{json!({"mime":"image/png","base64":"synthetic-unrun-only","source_sha256":source_hash(),
 "source_width":1001,"source_height":1601,"decoded_width":1001,"decoded_height":1601,"width":800,"height":1280,
 "mapping":"normalized_full_frame","orientation":"exif_normalized_once"})}
fn record(action:&str)->Record{Record{id:"outer:actual".into(),action:action.into(),epoch:[1;16],binding:None,receipt:Some("inner:actual".into()),result:None,settled:false,bytes:0}}
fn status_result()->Value{json!({"event":"body_slim_result","protocol":1,"request_id":"outer:actual","action":"status","success":true,"outcome_unknown":false,
 "result":{"receipt":{"phase":"done","request_id":"inner:actual","success":false,"outcome_unknown":false,"error":"rejected before publication"},"view_error":"source removed"}})}
fn retained_result()->Value{
 let mut view=current_view();
 view["publication"]=json!({"request_id":"inner:actual","rendered":false,"unapplied_reason":"native core missing"});
 view["last_outcome"]=json!({"version":1,"request_id":"inner:actual","published_frame_id":"frame:7","output_pixel_sha256":"f".repeat(64),
  "rendered":false,"applied":false,"retained_intent":true,"reason":"native core missing","runtime_quality_accepted":false});
 json!({"event":"body_slim_result","protocol":1,"request_id":"outer:actual","action":"edit","success":true,"outcome_unknown":false,
  "result":{"view":view,"model":{},"receipt":{"phase":"done","protocol":1,"request_id":"inner:actual","success":true,"outcome_unknown":false,
  "rendered":false,"unapplied_reason":"native core missing","view":view}}})
}
fn rendered_result()->Value{
 let mut result=retained_result();let receipt=&mut result["result"]["receipt"];
 receipt["rendered"]=json!(true);receipt["unapplied_reason"]=Value::Null;
 receipt["view"]["publication"]=json!({"request_id":"inner:actual","rendered":true,"unapplied_reason":null});
 receipt["view"]["last_outcome"]=json!({"version":1,"request_id":"inner:actual","published_frame_id":"frame:7","output_pixel_sha256":"f".repeat(64),
  "geometry_delta_sha256":"f".repeat(64),"render_revision":7,"runtime_quality_accepted":false,"original_dimensions":[1001,1601],
  "render_dimensions":[1001,1601],"original_resolution":true,"single_source_sample":true,"composition_order":"body-then-face-inverse-v1",
  "body_operation_order":{"version":1,"operation_ids":["lnx.shoulder_shape.v1"]},"fields":[],"output_dtype":"float32"});
 result
}
fn active_result()->Value{
 let mut result=rendered_result();let receipt=&mut result["result"]["receipt"];
 receipt["view"]["recipe"]=json!({"version":1,"amount":-0.5});
 receipt["view"]["last_outcome"]["body_operation_order"]=json!({"version":10,"operation_ids":["lnx.body_slim.v1"]});
 let support=bound_support();
 receipt["view"]["last_outcome"]["fields"]=json!([{"operation_id":"lnx.body_slim.v1","body_ref":target(),"status":"rendered","applied":true,
  "runtime_quality_accepted":false,"requirement_id":"LNX-REF-PC-32473-C-bc54b9eb3c","support_policy":"body-slim-complete-silhouette-review-v1",
  "source_dimensions":[1001,1601],"render_dimensions":[1001,1601],"points_sha256":"c".repeat(64),"requested_recipe":{"version":1,"amount":-0.5},
  "input_binding_sha256":"d".repeat(64),"support_sha256":"e".repeat(64),"measured_silhouette_sha256":"f".repeat(64),
  "associated_face_ref":support["associated_face_ref"],"associated_face_evidence_sha256":support["associated_face_evidence_sha256"],
  "whole_person_horizontal_width":true,"complete_person_width_transport":true,"manual_complete_silhouette_required":true,
  "single_person_only":true,"background_collar_and_internal_gaps_may_move":true,"vertical_displacement":false,"hidden_anatomy_inferred":false,"ai_segmentation":false}]);
 result
}

#[test] fn signed_amount_is_independent_exact_recipe(){
 for amount in [-1.0,-0.5,0.0,0.5,1.0]{assert!(recipe(&json!({"version":1,"amount":amount})));}
 for amount in [json!(-1.001),json!(1.001),json!(true),json!(null),json!("0")]{assert!(!recipe(&json!({"version":1,"amount":amount})));}
 for value in [json!({"version":1,"amount":0,"head":0}),json!({"version":2,"amount":0}),json!({"version":1,"waist":0})]{assert!(!recipe(&value));}
}
#[test] fn exact_current_photo_actions_never_alias_other_families(){
 assert!(valid_request("view",&json!({})));assert!(valid_request("status",&json!({"request_id":"inner:actual"})));
 assert!(valid_request("select",&json!({"binding":owner(),"body_ref":target()})));assert!(valid_request("edit",&edit_request()));
 for action in ["analyse","reanalyse","install","download","execute","preset","batch"]{assert!(!valid_request(action,&json!({})));}
 for operation in ["lnx.head_size.v1","lnx.torso_length.v1","lnx.waist_shape.v1"]{let mut value=edit_request();value["operation_id"]=json!(operation);assert!(!valid_request("edit",&value));}
 let mut foreign=target();foreign["asset_sha256"]=json!("f".repeat(64));assert!(!valid_request("select",&json!({"binding":owner(),"body_ref":foreign})));
}
#[test] fn envelope_fields_types_and_digest_are_not_optional(){
 let original=edit_request();
 for key in original.as_object().unwrap().keys(){let mut value=original.clone();value.as_object_mut().unwrap().remove(key);assert!(!valid_request("edit",&value),"{key}");}
 for key in ["document_revision","state_revision","association_revision","people_association_revision"]{let mut value=original.clone();value[key]=json!(true);assert!(!valid_request("edit",&value));}
 let mut value=original.clone();value["body_ref"]=json!({"asset_sha256":source_hash(),"face_instance_id":"not-a-body","analysis_revision":2});assert!(!valid_request("edit",&value));
 value=original;value["body_graph_sha256"]=json!("A".repeat(64));assert!(!valid_request("edit",&value));
}
#[test] fn contour_and_collar_are_manual_not_head_or_pose_boxes(){
 let original=draft();assert!(support_input(&original,true));assert!(!support(&original));assert!(support(&bound_support()));
 for key in ["outline","collar_box","confirmations"]{let mut value=original.clone();value.as_object_mut().unwrap().remove(key);assert!(!support_input(&value,true));}
 for key in ["head_box","transition_box","pivot","pose_hull","inferred_outline"]{let mut value=original.clone();value[key]=json!([0.4,0.2,0.6,0.8]);assert!(!support_input(&value,true));}
 for flag in SUPPORT_FLAGS{let mut value=original.clone();value["confirmations"][*flag]=json!(false);assert!(!support_input(&value,true));}
 let mut value=original;value["method"]=json!("user-reviewed-complete-head-hair-support");assert!(!support_input(&value,true));
}
#[test] fn exact_simple_polygon_rejects_repeated_crossed_collinear_or_unbounded_vertices(){
 let original=draft();
 for count in [0,4,7,129]{let mut value=original.clone();value["outline"]=json!(vec![[0.4,0.4];count]);assert!(!support_input(&value,true));}
 let mut closed=original.clone();let first=closed["outline"][0].clone();closed["outline"].as_array_mut().unwrap().push(first);assert!(!support_input(&closed,true));
 let mut crossed=original.clone();crossed["outline"].as_array_mut().unwrap().swap(1,2);assert!(!support_input(&crossed,true));
 let mut collinear=original.clone();collinear["outline"][1]=json!([0.53,0.27]);assert!(!support_input(&collinear,true));
 for point in [json!([0.0,0.24]),json!([0.46,1.0]),json!([true,0.24]),json!([0.46]),json!([0.46,0.24,0.2])]{let mut value=original.clone();value["outline"][0]=point;assert!(!support_input(&value,true));}
 for collar in [json!([0.40,0.24,0.60,0.76]),json!([0.60,0.05,0.90,0.95]),json!([0.1,0.95,0.9,0.05])]{let mut value=original.clone();value["collar_box"]=collar;assert!(!support_input(&value,true));}
}
#[test] fn face_binding_is_all_or_nothing_and_cannot_touch_the_polygon(){
 let original=bound_support();assert!(support(&original));
 for key in ["associated_face_ref","associated_face_box","associated_face_evidence_sha256"]{let mut value=original.clone();value.as_object_mut().unwrap().remove(key);assert!(!support_input(&value,true));}
 for face in [json!([0.1,0.1,0.2,0.2]),json!([0.46,0.24,0.54,0.33]),json!([0.4,0.3,0.6,0.7])]{let mut value=original.clone();value["associated_face_box"]=face;assert!(!support(&value));}
 let mut request=edit_request();request["action"]=json!("support_review");request["payload"]=support_payload();request["payload"]["data"]=original;
 assert!(valid_request("edit",&request));request["payload"]["data"]["associated_face_ref"]["asset_sha256"]=json!("f".repeat(64));assert!(!valid_request("edit",&request));
}
#[test] fn concave_face_edge_crossing_cannot_hide_behind_four_inside_corners(){
 let mut value=bound_support();value["outline"]=json!([[0.2,0.2],[0.45,0.2],[0.45,0.5],[0.55,0.5],[0.55,0.2],[0.8,0.2],[0.8,0.8],[0.2,0.8]]);
 value["associated_face_box"]=json!([0.3,0.3,0.7,0.7]);
 let outline=contour(&value["outline"]).unwrap();assert!([[0.3,0.3],[0.7,0.3],[0.7,0.7],[0.3,0.7]].iter().all(|p|inside(&outline,*p)));
 assert!(!support(&value));
}
#[test] fn all_thirty_three_real_anchors_and_exact_ownership_are_required(){
 let original=support_payload();assert!(valid_payload("support_review",&original));
 for anchors in [json!((0..13).collect::<Vec<_>>()),json!((0..25).collect::<Vec<_>>()),json!((1..34).collect::<Vec<_>>()),json!(vec![0;33])]{let mut value=original.clone();value["visible_anchors"]=anchors;assert!(!valid_payload("support_review",&value));}
 let mut value=original;value["ownership_confirmed"]=json!(false);assert!(!valid_payload("support_review",&value));
}
#[test] fn view_allows_unreviewed_recovery_but_never_invents_missing_evidence(){
 let original=current_view();assert!(valid_view(&original));
 let mut unreviewed=original.clone();unreviewed["bodies"][0]["support"]=Value::Null;unreviewed["bodies"][0]["reviewed"]=json!(false);unreviewed["bodies"][0]["association"]=Value::Null;assert!(valid_view(&unreviewed));
 for key in ["support","association"]{let mut value=original.clone();value["bodies"][0].as_object_mut().unwrap().remove(key);assert!(!valid_view(&value));}
 let mut missing=original.clone();missing.as_object_mut().unwrap().remove("selected_body_ref");assert!(!valid_view(&missing));
 let mut duplicate=original.clone();let body=duplicate["bodies"][0].clone();duplicate["bodies"].as_array_mut().unwrap().push(body);assert!(!valid_view(&duplicate));
 let mut foreign=original;foreign["bodies"][0]["association"]["body_ref"]["body_instance_id"]=json!("other-body");assert!(!valid_view(&foreign));
}
#[test] fn source_proof_is_whole_original_or_canonical_align8_not_a_crop(){
 let view=current_view();let original=source_preview();assert!(valid_source(&original,&view));
 for (key,value) in [("source_sha256",json!("f".repeat(64))),("orientation",json!("rotated")),("mapping",json!("cropped")),("source_width",json!(1000)),("width",json!(640)),("decoded_width",json!(496))]{let mut source=original.clone();source[key]=value;assert!(!valid_source(&source,&view),"{key}");}
 let mut scaled=original;scaled["decoded_width"]=json!(496);scaled["decoded_height"]=json!(800);scaled["width"]=json!(496);scaled["height"]=json!(800);assert!(valid_source(&scaled,&view));
}
#[test] fn status_survives_missing_current_source_without_fabricating_a_view(){
 let original=status_result();assert!(valid_result(&original,&record("status")));
 for (key,value) in [("view",json!({})),("model",json!(true)),("receipt",json!({"phase":"done","request_id":"other","success":false,"outcome_unknown":false}))]{let mut response=original.clone();response["result"][key]=value;assert!(!valid_result(&response,&record("status")));}
 let mut response=original.clone();response["result"].as_object_mut().unwrap().remove("receipt");assert!(!valid_result(&response,&record("status")));
 response=original;response["action"]=json!("view");assert!(!valid_result(&response,&record("view")));
}
#[test] fn receipts_cannot_swap_event_outer_action_or_inner_request(){
 let original=status_result();
 for key in ["event","request_id","action"]{let mut value=original.clone();value[key]=json!("unrelated");assert!(!valid_result(&value,&record("status")));}
 let mut value=original;value["result"]["receipt"]["request_id"]=json!("unrelated");assert!(!valid_result(&value,&record("status")));
}
#[test] fn retained_intent_is_not_a_rendered_effect_or_runtime_quality_pass(){
 let original=retained_result();assert!(valid_result(&original,&record("edit")));
 for (path,value) in [("/result/receipt/rendered",json!(true)),("/result/receipt/unapplied_reason",Value::Null),
  ("/result/receipt/view/publication/request_id",json!("other")),("/result/receipt/view/last_outcome/retained_intent",json!(false)),
  ("/result/receipt/view/last_outcome/runtime_quality_accepted",json!(true))]{let mut response=original.clone();*response.pointer_mut(path).unwrap()=value;assert!(!valid_result(&response,&record("edit")),"{path}");}
 let mut missing=original;missing["result"]["receipt"]["view"].as_object_mut().unwrap().remove("last_outcome");assert!(!valid_result(&missing,&record("edit")));
}
#[test] fn rendered_proof_requires_exact_source_frame_revision_and_single_sample(){
 let original=rendered_result();assert!(valid_result(&original,&record("edit")));
 for (path,value) in [("/result/receipt/view/last_outcome/request_id",json!("other")),("/result/receipt/view/last_outcome/render_revision",json!(6)),
  ("/result/receipt/view/last_outcome/original_dimensions",json!([1000,1600])),("/result/receipt/view/last_outcome/render_dimensions",json!([500,500])),
  ("/result/receipt/view/last_outcome/single_source_sample",json!(false)),("/result/receipt/view/last_outcome/runtime_quality_accepted",json!(true)),
  ("/result/receipt/view/last_outcome/geometry_delta_sha256",json!("bad")),("/result/receipt/view/last_outcome/output_dtype",json!("rgb8-proxy"))]{let mut response=original.clone();*response.pointer_mut(path).unwrap()=value;assert!(!valid_result(&response,&record("edit")),"{path}");}
}
#[test] fn active_render_cannot_omit_silhouette_field_or_change_ownership(){
 let original=active_result();assert!(valid_result(&original,&record("edit")));
 for (path,value) in [("/result/receipt/view/last_outcome/fields",json!([])),
  ("/result/receipt/view/last_outcome/fields/0/points_sha256",json!("d".repeat(64))),
  ("/result/receipt/view/last_outcome/fields/0/associated_face_ref/face_instance_id",json!("other-face")),
  ("/result/receipt/view/last_outcome/fields/0/requested_recipe/amount",json!(0.5)),
  ("/result/receipt/view/last_outcome/fields/0/vertical_displacement",json!(true)),
  ("/result/receipt/view/last_outcome/fields/0/ai_segmentation",json!(true)),
  ("/result/receipt/view/bodies/0/association/people_association_revision",json!(2)),
  ("/result/receipt/view/bodies/0/operation_enabled",json!(false))]{let mut response=original.clone();*response.pointer_mut(path).unwrap()=value;assert!(!valid_result(&response,&record("edit")),"{path}");}
 let mut duplicate=original;let proof=duplicate["result"]["receipt"]["view"]["last_outcome"]["fields"][0].clone();duplicate["result"]["receipt"]["view"]["last_outcome"]["fields"].as_array_mut().unwrap().push(proof);assert!(!valid_result(&duplicate,&record("edit")));
}
#[test] fn immutable_signatures_survive_release_and_new_engine_epochs(){
 let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;
 let signature=json!({"action":"view","request_id":"same","request":{}}).to_string();
 host.begin([1;16],"same","view",&json!({}),&signature).unwrap();assert!(host.replay("same",&signature).unwrap());
 assert!(host.replay("same","changed payload").is_err());host.records.clear();host.end([1;16]);host.epoch=[2;16];host.supported=true;
 assert!(host.replay("same",&signature).unwrap());assert!(host.begin([2;16],"same","view",&json!({}),&signature).is_err());
 assert_eq!(host.status("same")["phase"],"unavailable");assert_eq!(host.status("same")["outcome_unknown"],true);
}
#[test] fn ledger_limits_never_make_dropped_identity_replayable(){
 let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;host.signature_bytes=MAX_SIGNATURE_BYTES;
 assert!(host.begin([1;16],"new","view",&json!({}),"new").is_err());assert!(!host.seen.contains_key("new"));
 host.signature_bytes=0;
 for i in 0..4{let id=format!("pending:{i}");host.begin([1;16],&id,"edit",&json!({"request_id":format!("inner:{i}")}),&id).unwrap();}
 assert!(host.begin([1;16],"over-budget","edit",&json!({"request_id":"inner:over"}),"over").is_err());
 assert_eq!(host.records.len(),4);assert_eq!(host.seen.len(),4);
}
#[test] fn unknown_original_edit_remains_pinned_even_after_end_and_late_success(){
 let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;
 host.begin([1;16],"outer:actual","edit",&edit_request(),"original").unwrap();assert!(!releasable(&host.records[0]));
 host.end([1;16]);assert_eq!(host.status("outer:actual")["result"]["outcome_unknown"],true);assert!(!releasable(&host.records[0]));
 host.finish("outer:actual",retained_result());assert_eq!(host.status("outer:actual")["result"]["outcome_unknown"],true);
 host.records[0].settled=true;assert!(releasable(&host.records[0]));
}
#[test] fn startup_requires_exact_ready_epoch_not_native_quality_or_guesswork(){
 let mut host=Mailbox::default();host.epoch=[7;16];assert!(host.begin([7;16],"first","view",&json!({}),"first").is_err());
 host.supported=true;assert!(host.begin([8;16],"second","view",&json!({}),"second").is_err());assert!(host.begin([7;16],"third","view",&json!({}),"third").is_ok());
}
#[test] fn source_document_and_epoch_binding_cannot_be_swapped(){
 let request=edit_request();let record=Record{binding:expected_binding("edit",&request),..record("edit")};let original=current_view();assert!(matches_binding(&original,&record));
 for (key,value) in [("asset_sha256",json!("f".repeat(64))),("document_epoch",json!("other-epoch")),("document_id",json!("other-doc")),("document_revision",json!(6))]{let mut view=original.clone();view["binding"][key]=value;assert!(!matches_binding(&view,&record));}
}
#[test] fn only_view_and_status_are_read_only_and_no_unrelated_route_is_claimed(){
 for action in ["view","status"]{assert!(read_only(&json!({"cmd":"body_slim","action":action})));}
 for action in ["select","edit","analyse","reanalyse","install"]{assert!(!read_only(&json!({"cmd":"body_slim","action":action})));}
 for family in ["head_size","torso_length","waist_shape","leg_length","people"]{assert!(!read_only(&json!({"cmd":family,"action":"view"})));}
}
#[test] fn authoritative_inner_status_alone_can_settle_original_fence(){
 // Sole fixture using this module's global mailbox; other fixtures are local.
 let epoch=[236;16];reset(epoch);ready(epoch,true);
 let original=json!({"cmd":"body_slim","action":"edit","request_id":"body-slim:original"});
 crate::project_recovery_fence::issued(epoch,&original).unwrap();
 {let mut host=mailbox().lock().unwrap();host.begin(epoch,"body-slim:original","edit",&edit_request(),"original").unwrap();host.begin(epoch,"body-slim:status","status",&json!({"request_id":"inner:actual"}),"status").unwrap();}
 assert!(guards_result(epoch,"body-slim:original"));assert!(!guards_result([237;16],"body-slim:original"));
 let mut reply=status_result();reply["request_id"]=json!("body-slim:status");reply["result"]["receipt"]["request_id"]=json!("wrong-inner");
 assert!(!receive([237;16],&reply));assert!(!receive(epoch,&reply));assert!(crate::project_recovery_fence::proof(epoch).is_err());
 {let mut host=mailbox().lock().unwrap();host.begin(epoch,"body-slim:status:2","status",&json!({"request_id":"inner:actual"}),"status:2").unwrap();}
 reply["request_id"]=json!("body-slim:status:2");reply["result"]["receipt"]["request_id"]=json!("inner:actual");
 assert!(receive(epoch,&reply));assert!(crate::project_recovery_fence::proof(epoch).is_ok());assert!(!guards_result(epoch,"body-slim:original"));
 let host=mailbox().lock().unwrap();assert_eq!(host.status("body-slim:original")["phase"],"pending");
 assert!(releasable(host.records.iter().find(|r|r.id=="body-slim:original").unwrap()));
}
