// SPDX-License-Identifier: GPL-3.0-or-later
// Authored fixtures UNRUN. They do not load drivers or access camera hardware.
use super::*;

#[test]
fn capability_is_evidence_not_a_boolean_promise() {
    assert!(!Support::Unknown.can_request());
    assert!(!Support::Unsupported.can_request());
    assert!(Support::DriverAdvertised.can_request());
    assert!(Support::Verified.can_request());
}

#[test]
fn cancellation_is_shared_and_sticky() {
    let cancel = CancellationToken::default();
    let copy = cancel.clone();
    assert!(!copy.is_cancelled());
    cancel.cancel();
    assert!(copy.is_cancelled());
}

#[test]
fn camera_name_is_never_a_local_path() {
    for name in ["", ".", "..", "../original.raw", "/home/original.raw", "dir\\image.raw", "a\0b"] {
        assert!(CameraObject { folder: "/store/DCIM".into(), name: name.into() }.validate().is_err());
    }
    assert!(CameraObject { folder: "/store/DCIM".into(), name: "IMG_1234.CR3".into() }.validate().is_ok());
    assert!(CameraObject { folder: "relative".into(), name: "IMG.CR3".into() }.validate().is_err());
}

#[cfg(target_os = "linux")]
#[test]
fn only_concrete_detected_usb_addresses_are_eligible() {
    for port in ["usb:", "usb:001", "ptpip:127.0.0.1", "disk:/tmp", "usb:0,1", "usb:1,256", "usb:1,2,3", "usb:1,../2"] {
        assert!(!linux::valid_usb_port(port), "{port}");
    }
    assert!(linux::valid_usb_port("usb:001,027"));
}

#[cfg(target_os = "linux")]
#[test]
fn capture_advertisement_does_not_fabricate_event_support() {
    let caps = linux::capabilities_from_flags(ffi::CAPTURE_IMAGE | ffi::CAPTURE_PREVIEW);
    assert_eq!(caps.remote_capture, Support::DriverAdvertised);
    assert_eq!(caps.preview, Support::DriverAdvertised);
    assert_eq!(caps.events, Support::Unknown);
    assert_eq!(caps.original_download, Support::Unknown);
    assert_eq!(caps.remote_trigger, Support::Unknown);
    assert_eq!(linux::capabilities_from_flags(0).remote_capture, Support::Unknown);
}

#[cfg(target_os = "linux")]
#[test]
fn trigger_advertisement_is_independent_of_capture_and_event_delivery() {
    let caps = linux::capabilities_from_flags(ffi::TRIGGER_CAPTURE);
    assert_eq!(caps.remote_trigger, Support::DriverAdvertised);
    assert_eq!(caps.remote_capture, Support::Unknown);
    assert_eq!(caps.events, Support::Unknown);
    assert_eq!(caps.original_download, Support::Unknown);
    assert_eq!(linux::capabilities_from_flags(0).remote_trigger, Support::Unknown);
    // Type-level fixture: successful trigger has no CameraObject to fabricate.
    let _method: fn(&mut LinuxGphotoDevice, &CancellationToken) -> Result<()> =
        <LinuxGphotoDevice as TetherDevicePort>::trigger_capture;
}

#[cfg(target_os = "linux")]
#[test]
fn dispatched_trigger_failure_does_not_authorize_a_retry() {
    linux::trigger_dispatch_result(0, Ok(0)).unwrap();
    for code in [-1, -10, -53, -110, -112] {
        let error = linux::trigger_dispatch_result(code, ffi::check("remote_trigger", code)).unwrap_err();
        assert!(error.outcome_unknown, "native code {code}");
    }
    let unsupported = linux::trigger_dispatch_result(ffi::NOT_SUPPORTED,
        ffi::check("remote_trigger", ffi::NOT_SUPPORTED)).unwrap_err();
    assert_eq!(unsupported.kind, ErrorKind::Unsupported);
    assert!(!unsupported.outcome_unknown);
}

#[cfg(target_os = "linux")]
#[test]
fn public_abi_layout_matches_supported_linux_c_abi() {
    assert_eq!(std::mem::size_of::<ffi::CameraFilePath>(), 1152);
    assert_eq!(std::mem::size_of::<ffi::CameraAbilities>(), 2504);
    assert_eq!(std::mem::align_of::<ffi::CameraAbilities>(), 4);
    assert_eq!(std::mem::size_of::<ffi::CameraFileHandler>(), 3 * std::mem::size_of::<usize>());
}

#[cfg(target_os = "linux")]
#[test]
fn fixed_camera_paths_fail_closed_on_truncation() {
    assert!(ffi::fixed_text(&[b'a' as libc::c_char; 128], "test").is_err());
    assert_eq!(ffi::fixed_text(&[b'a' as libc::c_char, 0, b'b' as libc::c_char], "test").unwrap(), "a");
}

#[cfg(target_os = "linux")]
#[test]
fn staging_components_cannot_escape_or_collide_via_dot_names() {
    for name in ["", ".", "..", "a/b", "a\\b", "a\0b", "../raw", "写真\n001.CR3", "a\u{0085}b"] {
        assert!(transfer::validate_local_name(name).is_err());
    }
    assert!(transfer::validate_local_name("session-17_transfer-002.CR3.stage").is_ok());
    assert!(transfer::validate_local_name("春节写真_001.CR3.stage").is_ok());
    assert!(transfer::validate_local_name("客户 张三（精修）.JPG").is_ok());
    assert!(transfer::validate_local_name(".private-stage").is_ok());
    assert!(transfer::validate_local_name(&"照".repeat(85)).is_ok());
    assert!(transfer::validate_local_name(&"照".repeat(86)).is_err());
    assert!(transfer::validate_local_name(&"a".repeat(255)).is_ok());
    assert!(transfer::validate_local_name(&"a".repeat(256)).is_err());
}
