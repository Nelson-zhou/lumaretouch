//! AUTHORED / UNRUN. Schema/receipt fixtures, not target-photo pixel acceptance.
use super::*;
use serde_json::json;
use crate::receipt_host::ReceiptKind;
use crate::preset_host::{PresetHost, PresetKind};

fn sample_report() -> Value {
    json!({"version":1,"source_sha256":"a".repeat(64),"report_sha256":"b".repeat(64),"filename":"sample.xmp","byte_length":512,
        "process_version":"11.0","camera_raw_version":"15.0","can_import":true,
        "properties":[{"name":"ProcessVersion","status":"unsupported","value":"11.0","reason":"No Adobe emulation"},
            {"name":"Exposure2012","status":"adaptable","value":"1.25","reason":"Native EV only"},
            {"name":"WhiteBalance","status":"unsupported","value":"As Shot","reason":"No inferred gains"}],
        "adaptations":[{"id":"exposure","title":"Native EV","module":"lnx.exposure.v1","reason":"Explicit selection"}],
        "warnings":["Not Adobe rendering compatibility"]})
}
fn sample_ack() -> Value {
    json!({"source_sha256":"a".repeat(64),"report_sha256":"b".repeat(64),"mode":MODE,"selected":["exposure"]})
}
fn sample_summary() -> Value {
    json!({"version":1,"source_sha256":"a".repeat(64),"filename":"sample.xmp","selected":["exposure"],
        "report":sample_report(),"read_only_summary":true})
}
fn sample_preview() -> Value {
    json!({"mime":"image/png","width":1,"height":1,"sha256":"1".repeat(64),
        "base64":"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII="})
}
fn sample_transfer() -> Value {
    json!({"version":1,"document_id":"photo","revision":"7","xmp_sha256":"a".repeat(64),
        "source_proof":{"asset_sha256":"c".repeat(64),"original_sha256":"c".repeat(64),"creative_source":null},
        "before_sha256":"d".repeat(64),"candidate_sha256":"e".repeat(64),
        "before_people_sha256":"f".repeat(64),"candidate_people_sha256":"f".repeat(64),
        "source_size":[100,100],"before_output_size":[100,100],"after_output_size":[100,100],
        "before":sample_preview(),"after":sample_preview()})
}
fn sample_preflight() -> Value {
    json!({"protocol":1,"request_id":"r","action":"preflight","success":true,"outcome_unknown":false,
        "id":"xmp-preset","document_id":"photo","revision":"7","preflight_token":"0".repeat(32),
        "module_scope":["lnx.exposure.v1"],"applies":{"lnx.exposure.v1":{"ev":1.25}},
        "xmp_report":sample_report(),"xmp_transfer":sample_transfer()})
}

#[test]
fn unsupported_report_remains_readable_but_not_importable() {
    let mut value = sample_report(); assert!(report(&value));
    value["process_version"] = json!("future"); value["can_import"] = json!(false); value["adaptations"] = json!([]);
    assert!(report(&value)); value["can_import"] = json!(true); assert!(!report(&value));
}
#[test]
fn legitimate_large_unsupported_payload_is_not_misreported_as_malformed() {
    let mut value = sample_report();
    value["properties"][2]["value"] = json!({"kind":"structure","fields":{"LookTable":"🎨".repeat(65536)}});
    value["properties"][2]["name"] = json!("n".repeat(1026));
    assert!(report(&value));
    value["properties"][2]["value"] = json!("x".repeat(65537)); assert!(!report(&value));
}
#[test]
fn public_report_rejects_raw_bytes_and_oversized_or_wrong_identity() {
    for (key, replacement) in [("source_base64", json!("PHhtcD4=")), ("source_sha256", json!("A".repeat(64))),
        ("filename", json!("../original.xmp")), ("byte_length", json!(1048577))] {
        let mut value = sample_report(); value[key] = replacement; assert!(!report(&value), "{key}");
    }
}
#[test]
fn import_acknowledgment_cannot_enable_unsupported_or_duplicate_groups() {
    assert!(import_ack(&sample_ack()));
    for selected in [json!([]), json!(["exposure","exposure"]), json!(["white_balance"]), json!(["profile"])] {
        let mut value = sample_ack(); value["selected"] = selected; assert!(!import_ack(&value));
    }
    let mut value = sample_ack(); value["mode"] = json!("adobe-compatible"); assert!(!import_ack(&value));
}
#[test]
fn public_summary_has_no_original_bytes_and_only_selected_modules() {
    let modules = json!({"lnx.exposure.v1":{"ev":1.25}}); assert!(summary(&sample_summary(), &modules));
    let mut value = sample_summary(); value["source_base64"] = json!("PHhtcD4="); assert!(!summary(&value, &modules));
    assert!(!summary(&sample_summary(), &json!({"lnx.exposure.v1":{"ev":1.25},"lnx.white_balance.v1":{}})));
    assert!(!summary(&sample_summary(), &json!({"lnx.exposure.v1":{"ev":5.01}})));
}
#[test]
fn native_curves_require_all_four_explicit_arrays_and_supported_recipe_shape() {
    let mut compatibility = sample_report();
    compatibility["adaptations"] = json!([{"id":"point_curves","title":"Four curves","module":"lnx.curves.v1","reason":"Explicit arrays"}]);
    let mut modules = json!({"lnx.curves.v1":{"recipe":{"version":1,"space":"srgb-display","interpolation":"pchip","boundary":"linear","enabled":true,
        "master":[[0,0],[1,1]],"red":[[0,0],[1,1]],"green":[[0,0],[1,1]],"blue":[[0,0],[1,1]]}}});
    assert!(adapted_modules(&modules, &compatibility));
    let original = modules.clone();
    for key in ["master","red","green","blue"] {
        modules = original.clone(); modules["lnx.curves.v1"]["recipe"].as_object_mut().unwrap().remove(key);
        assert!(!adapted_modules(&modules, &compatibility));
    }
    modules = original.clone(); modules["lnx.curves.v1"]["recipe"]["master"] = json!([[0,0],[0,1]]);
    assert!(!adapted_modules(&modules, &compatibility));
    modules = original; modules["lnx.curves.v1"]["recipe"]["version"] = json!(3); assert!(!adapted_modules(&modules, &compatibility));
}
#[test]
fn inspection_requires_no_photo_but_is_correlated_and_has_clean_known_failures() {
    assert!(command(&json!({"action":"xmp_inspect","path":"/sample.xmp","request_id":"read"})).is_ok());
    assert!(command(&json!({"action":"xmp_inspect","path":"/sample.xmp","request_id":"read","document_id":"photo"})).is_err());
    assert!(PresetKind::valid_request("xmp_inspect", None));
    assert!(!PresetKind::valid_request("xmp_inspect", Some("photo")));
    assert!(PresetKind::valid(&json!({"protocol":1,"action":"xmp_inspect","success":false,"outcome_unknown":false,"error":"Expat runtime too old"}), None));
}
#[test]
fn legacy_json_stays_unchanged_but_xmp_import_requires_acknowledgment() {
    assert!(command(&json!({"action":"import","path":"/ordinary.json","force":true})).is_ok());
    assert!(command(&json!({"action":"import","path":"/sample.XMP","request_id":"r"})).is_err());
    let mut value = json!({"action":"import","path":"/sample.xmp","request_id":"r","xmp_ack":sample_ack()});
    assert!(command(&value).is_ok()); value["force"] = json!(true); assert!(command(&value).is_err());
    value["force"] = json!(false); value["path"] = json!("/portable-xmp.json"); assert!(command(&value).is_ok());
}
#[test]
fn preflight_requires_both_actual_png_headers_and_exact_target_identity() {
    assert!(PresetKind::valid(&sample_preflight(), Some("photo")));
    for key in ["xmp_report","xmp_transfer"] {
        let mut value = sample_preflight(); value.as_object_mut().unwrap().remove(key); assert!(!PresetKind::valid(&value, Some("photo")));
    }
    for (key, replacement) in [("document_id",json!("other")),("revision",json!("8")),("xmp_sha256",json!("0".repeat(64))),
        ("before_people_sha256",json!("")),("candidate_people_sha256",json!(""))] {
        let mut value = sample_preflight(); value["xmp_transfer"][key] = replacement; assert!(!PresetKind::valid(&value, Some("photo")), "{key}");
    }
    for side in ["before", "after"] {
        let mut value = sample_preflight(); value["xmp_transfer"][side]["width"] = json!(2); assert!(!PresetKind::valid(&value, Some("photo")));
        value = sample_preflight(); value["xmp_transfer"][side]["base64"] = json!("iVBORw=="); assert!(!PresetKind::valid(&value, Some("photo")));
    }
}
#[test]
fn malformed_base64_padding_and_oversize_payloads_are_refused() {
    assert!(png_header(sample_preview()["base64"].as_str().unwrap()).is_some());
    for value in ["iVBORw==AAAA", "iVBORx==", "====", "iVBORw=", "https://example.invalid/pixel.png"] { assert!(png_header(value).is_none()); }
    assert!(png_header(&"A".repeat(1398108)).is_none());
}
#[test]
fn review_ack_requires_four_exact_hashes_and_a_frozen_application() {
    let ack = json!({"source_sha256":"a".repeat(64),"report_sha256":"b".repeat(64),"before_sha256":"1".repeat(64),"after_sha256":"2".repeat(64)});
    assert!(review_ack(&ack));
    let mut command_value = json!({"action":"apply","request_id":"apply-r","document_id":"photo","preflight_token":"0".repeat(32),"xmp_review_ack":ack});
    assert!(command(&command_value).is_ok());
    command_value.as_object_mut().unwrap().remove("preflight_token"); assert!(command(&command_value).is_err());
    let mut altered = ack; altered["source_base64"] = json!("PHhtcD4="); assert!(!review_ack(&altered));
}
#[test]
fn inspection_mailbox_keeps_first_terminal_receipt_and_never_reexecutes_query() {
    let mut host = PresetHost::default(); host.reset([1;16]); host.ready([1;16], true);
    host.begin([1;16], "read", "xmp_inspect").unwrap();
    let receipt = json!({"protocol":1,"request_id":"read","action":"xmp_inspect","success":true,"outcome_unknown":false,
        "path":"/sample.xmp","xmp_report":sample_report()});
    host.receive([1;16], &receipt); assert_eq!(host.status("read")["result"], receipt);
    host.ended([1;16]); assert_eq!(host.status("read")["result"], receipt);
    assert!(host.begin([1;16], "read", "xmp_inspect").is_err());
}
