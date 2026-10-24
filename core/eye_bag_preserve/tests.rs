// SPDX-License-Identifier: GPL-3.0-or-later
//! Authored fixtures only. UNRUN; not evidence of runtime correctness.
use super::*;

fn bits(values: &[f32]) -> Vec<u32> { values.iter().map(|value| value.to_bits()).collect() }

#[test]
fn full_protection_is_source_bit_exact() {
    let source = [-0.0, 0.25, 1.0];
    let mut output = [0.7; 3];
    apply_into(&source, &[0.5, 0.75, 0.0], &[1.0], 1, 1, 1.0, &mut output, || false).unwrap();
    assert_eq!(bits(&output), bits(&source));
}

#[test]
fn zero_delta_preserves_signed_zero() {
    let source = [-0.0, 0.25, 1.0];
    let mut output = [0.7; 3];
    for preserve in [0.0, 0.5, 1.0] {
        apply_into(&source, &[0.0, 0.25, 1.0], &[0.25], 1, 1, preserve, &mut output, || false).unwrap();
        assert_eq!(bits(&output), bits(&source));
    }
}

#[test]
fn no_protection_copies_only_changed_corrected_channels() {
    let source = [-0.0, 0.25, 1.0];
    let corrected = [0.0, 0.75, 0.5];
    let mut output = [0.7; 3];
    for (protection, preserve) in [(1.0, 0.0), (0.0, 1.0)] {
        apply_into(&source, &corrected, &[protection], 1, 1, preserve, &mut output, || false).unwrap();
        assert_eq!(bits(&output), bits(&[-0.0, 0.75, 0.5]));
    }
}

#[test]
fn fractional_coverage_is_convex_not_clamped() {
    let mut output = [0.0; 6];
    apply_into(&[0.0, 0.5, 1.0, 1.0, 0.5, 0.0],
        &[1.0, 0.0, 0.5, 0.0, 1.0, 0.5], &[1.0, 0.5], 2, 1, 0.5,
        &mut output, || false).unwrap();
    assert_eq!(output, [0.5, 0.25, 0.75, 0.25, 0.875, 0.375]);
}

#[test]
fn invalid_hidden_pixels_are_not_accepted() {
    for invalid in [f32::NAN, f32::INFINITY, -0.1, 1.1] {
        let mut output = [0.7; 3];
        let before = bits(&output);
        assert_eq!(apply_into(&[0.2; 3], &[invalid, 0.2, 0.2], &[1.0],
            1, 1, 1.0, &mut output, || false), Err(PIXEL_ERROR));
        assert_eq!(bits(&output), before);
        assert_eq!(apply_into(&[invalid, 0.2, 0.2], &[0.2; 3], &[1.0],
            1, 1, 1.0, &mut output, || false), Err(PIXEL_ERROR));
        assert_eq!(bits(&output), before);
        assert_eq!(apply_into(&[0.2; 3], &[0.3; 3], &[invalid],
            1, 1, 0.0, &mut output, || false), Err(PIXEL_ERROR));
        assert_eq!(bits(&output), before);
    }
}

#[test]
fn invalid_settings_and_lengths_leave_output_untouched() {
    let mut output = [0.7; 3];
    let before = bits(&output);
    for preserve in [f32::NAN, f32::INFINITY, -0.1, 1.1] {
        assert_eq!(apply_into(&[0.2; 3], &[0.3; 3], &[1.0],
            1, 1, preserve, &mut output, || false), Err(SETTINGS_ERROR));
        assert_eq!(bits(&output), before);
    }
    assert_eq!(apply_into(&[0.2; 2], &[0.3; 3], &[1.0],
        1, 1, 1.0, &mut output, || false), Err(ABI_ERROR));
    assert_eq!(bits(&output), before);
    assert_eq!(admit(0, 1), Err(ABI_ERROR));
    assert_eq!(admit(MAX_DIMENSION + 1, 1), Err(ABI_ERROR));
    assert_eq!(admit(8_000, 8_000), Err(RESOURCE_ERROR));
}

#[test]
fn cancellation_before_during_and_after_staging_is_atomic() {
    let source = vec![0.2; 3 * 600];
    let corrected = vec![0.8; 3 * 600];
    let mask = vec![0.5; 600];
    // Three validation polls, a preallocation poll, three staging polls and
    // the last publication poll. Every chosen cancellation leaves output alone.
    for cancel_at in 1..=8 {
        let mut output = vec![0.7; 3 * 600];
        let before = bits(&output);
        let mut polls = 0;
        let result = apply_into(&source, &corrected, &mask, 600, 1, 1.0, &mut output,
            || { polls += 1; polls == cancel_at });
        assert_eq!(result, Err(CANCELLED));
        assert_eq!(bits(&output), before);
    }
}

#[test]
fn cancellation_on_identity_does_not_publish() {
    let mut output = [0.7; 3];
    let before = bits(&output);
    let mut polls = 0;
    assert_eq!(apply_into(&[0.2; 3], &[0.8; 3], &[1.0], 1, 1, 1.0, &mut output,
        || { polls += 1; polls == 2 }), Err(CANCELLED));
    assert_eq!(bits(&output), before);
}

#[test]
fn ffi_rejects_alias_before_constructing_mutable_slice() {
    let mut source = [0.2; 3];
    let corrected = [0.8; 3];
    let protection = [1.0];
    let before = bits(&source);
    let code = unsafe { lrt_eye_bag_preserve_apply_v1(source.as_ptr(), 3,
        corrected.as_ptr(), 3, protection.as_ptr(), 1, 1, 1, 1.0,
        source.as_mut_ptr(), 3, None, std::ptr::null_mut()) };
    assert_eq!(code, ABI_ERROR);
    assert_eq!(bits(&source), before);
}

#[test]
fn ffi_rejects_null_without_touching_output() {
    let mut output = [0.7; 3];
    let before = bits(&output);
    let corrected = [0.8; 3];
    let protection = [1.0];
    let code = unsafe { lrt_eye_bag_preserve_apply_v1(std::ptr::null(), 3,
        corrected.as_ptr(), 3, protection.as_ptr(), 1, 1, 1, 1.0,
        output.as_mut_ptr(), 3, None, std::ptr::null_mut()) };
    assert_eq!(code, ABI_ERROR);
    assert_eq!(bits(&output), before);
}

#[test]
fn ffi_accepts_read_only_input_alias() {
    let source = [-0.0, 0.25, 1.0];
    let protection = [0.5];
    let mut output = [0.7; 3];
    let code = unsafe { lrt_eye_bag_preserve_apply_v1(source.as_ptr(), 3,
        source.as_ptr(), 3, protection.as_ptr(), 1, 1, 1, 1.0,
        output.as_mut_ptr(), 3, None, std::ptr::null_mut()) };
    assert_eq!(code, 0);
    assert_eq!(bits(&output), bits(&source));
}
