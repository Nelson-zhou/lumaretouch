// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Not compiled, executed or photographic acceptance evidence.
use super::*;

fn bits(values: &[f32]) -> Vec<u32> { values.iter().map(|v| v.to_bits()).collect() }
fn render(source: &[f32], coverage: &[f32], temperature: f32, tint: f32) -> Vec<f32> {
    let mut output = vec![42.0; source.len()];
    apply_into(source, coverage, coverage.len(), 1, temperature, tint, &mut output,
        || false).unwrap();
    output
}
fn lab_of(rgb: &[f32]) -> [f64; 3] {
    to_lab([decode(f64::from(rgb[0])), decode(f64::from(rgb[1])), decode(f64::from(rgb[2]))]).0
}

#[test]
fn neutral_controls_and_zero_coverage_preserve_every_bit() {
    let source = [-0.0, 0.5, 1.0, 0.7, 0.6, 0.4];
    assert_eq!(bits(&render(&source, &[1.0, 0.5], -0.0, 0.0)), bits(&source));
    assert_eq!(bits(&render(&source, &[-0.0, 0.0], 1.0, -1.0)), bits(&source));
    let result = render(&source, &[0.0, 1.0], 1.0, -1.0);
    assert_eq!(bits(&result[..3]), bits(&source[..3]));
    assert_ne!(bits(&result[3..]), bits(&source[3..]));
}

#[test]
fn black_and_white_are_exact_at_all_control_corners() {
    let source = [-0.0, 0.0, -0.0, 1.0, 1.0, 1.0];
    for temperature in [-1.0, 0.0, 1.0] { for tint in [-1.0, 0.0, 1.0] {
        assert_eq!(bits(&render(&source, &[1.0, 1.0], temperature, tint)), bits(&source));
    }}
}

#[test]
fn independent_midgray_axes_have_documented_sign_and_original_scale() {
    let source = [0.5; 3];
    let before = lab_of(&source);
    for sign in [-1.0, 1.0] {
        let warm = lab_of(&render(&source, &[1.0], sign, 0.0));
        let tint = lab_of(&render(&source, &[1.0], 0.0, sign));
        assert!((warm[0] - before[0]).abs() < 2e-5);
        assert!((tint[0] - before[0]).abs() < 2e-5);
        assert!((warm[1] - before[1]).abs() < 2e-5);
        assert!((tint[2] - before[2]).abs() < 2e-5);
        assert!((warm[2] - before[2] - 8.0 * f64::from(sign)).abs() < 3e-5);
        assert!((tint[1] - before[1] - 6.0 * f64::from(sign)).abs() < 3e-5);
    }
}

#[test]
fn partial_coverage_is_a_linear_light_mix_not_an_encoded_rgb_blend() {
    let source = [0.72, 0.48, 0.32];
    let full = render(&source, &[1.0], -1.0, 1.0);
    let partial = render(&source, &[0.25], -1.0, 1.0);
    for c in 0..3 {
        let expected = 0.75 * decode(f64::from(source[c])) + 0.25 * decode(f64::from(full[c]));
        assert!((decode(f64::from(partial[c])) - expected).abs() < 1e-7);
    }
    assert!((lab_of(&partial)[0] - lab_of(&source)[0]).abs() < 2e-5);
}

#[test]
fn saturated_and_near_endpoint_colours_remain_in_gamut_at_constant_l() {
    let colours = [
        [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        [1.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0],
        [0.00001; 3], [0.99999; 3], [0.002, 0.001, 0.003],
        [0.96, 0.95, 0.93], [0.65, 0.36, 0.22],
    ];
    for source in colours { for temperature in [-1.0, -0.01, 0.01, 1.0] {
        for tint in [-1.0, 0.0, 1.0] {
            let result = render(&source, &[1.0], temperature, tint);
            assert!(result.iter().copied().all(unit));
            assert!((lab_of(&result)[0] - lab_of(&source)[0]).abs() < 3e-5);
        }
    }}
}

#[test]
fn gamut_compression_scales_both_lab_chroma_axes_together() {
    let source = [1.0, 0.0, 0.0];
    let before = lab_of(&source);
    let requested = [before[0], before[1] + 6.0, before[2] + 8.0];
    let y = to_lab(source.map(|v| decode(f64::from(v)))).1;
    assert!(!in_gamut(from_lab_at_y(requested, y)));
    let result = render(&source, &[1.0], 1.0, 1.0);
    let after = lab_of(&result);
    let scale_a = after[1] / requested[1];
    let scale_b = after[2] / requested[2];
    assert!((0.0..1.0).contains(&scale_a));
    assert!((scale_a - scale_b).abs() < 2e-6);
    assert!((after[0] - before[0]).abs() < 2e-5);
}

#[test]
fn texture_lightness_is_preserved_without_neighbour_reads() {
    let source: Vec<f32> = (0..32).flat_map(|i| {
        let value = 0.2 + i as f32 * 0.015 + if i % 2 == 0 { 0.002 } else { -0.002 };
        [value + 0.06, value, value - 0.04]
    }).collect();
    let result = render(&source, &[1.0; 32], 1.0, -0.5);
    for i in 0..32 {
        assert!((lab_of(&result[3*i..3*i+3])[0] - lab_of(&source[3*i..3*i+3])[0]).abs() < 2e-5);
    }
    let mut changed = source.clone();
    changed[15..18].copy_from_slice(&[1.0, 0.0, 0.0]);
    let second = render(&changed, &[1.0; 32], 1.0, -0.5);
    for i in 0..32 { if i != 5 {
        assert_eq!(bits(&result[3*i..3*i+3]), bits(&second[3*i..3*i+3]));
    }}
}

#[test]
fn repeated_render_from_same_source_is_deterministic_and_source_unchanged() {
    let source = [0.72, 0.43, 0.28, 0.05, 0.04, 0.03];
    let before = bits(&source);
    let first = render(&source, &[1.0, 0.5], 0.75, -0.25);
    assert_eq!(bits(&first), bits(&render(&source, &[1.0, 0.5], 0.75, -0.25)));
    assert_eq!(before, bits(&source));
}

#[test]
fn invalid_input_even_outside_or_neutral_is_rejected_before_writing() {
    for invalid in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -0.01, 1.01] {
        let mut output = [42.0; 3];
        assert_eq!(apply_into(&[0.5, 0.5, invalid], &[0.0], 1, 1, 0.0, 0.0,
            &mut output, || false), Err(PIXEL_ERROR));
        assert_eq!(apply_into(&[0.5; 3], &[invalid], 1, 1, 0.0, 0.0,
            &mut output, || false), Err(PIXEL_ERROR));
        assert_eq!(output, [42.0; 3]);
    }
    for invalid in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -1.01, 1.01] {
        for (temperature, tint) in [(invalid, 0.0), (0.0, invalid)] {
            assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, temperature, tint,
                &mut [42.0; 3], || false), Err(SETTINGS_ERROR));
        }
    }
}

#[test]
fn dimensions_work_and_lengths_are_checked() {
    assert_eq!(admit(0, 1), Err(ABI_ERROR));
    assert_eq!(admit(usize::MAX, usize::MAX), Err(ABI_ERROR));
    assert_eq!(admit(MAX_DIMENSION + 1, 1), Err(ABI_ERROR));
    assert_eq!(admit(8000, 8001), Err(RESOURCE_ERROR));
    assert_eq!(admit(8000, 8000), Ok(MAX_PIXELS));
    assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, 0.5, 0.0,
        &mut [42.0; 2], || false), Err(ABI_ERROR));
}

#[test]
fn cancellation_before_writes_and_mid_render_is_explicit() {
    let mut output = [42.0; 3];
    assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, 1.0, 1.0,
        &mut output, || true), Err(CANCELLED));
    assert_eq!(output, [42.0; 3]);
    let source = vec![0.5; 3 * 3 * POLL_PIXELS];
    let mask = vec![1.0; 3 * POLL_PIXELS];
    let mut output = vec![42.0; source.len()];
    let mut polls = 0;
    assert_eq!(apply_into(&source, &mask, mask.len(), 1, 1.0, 1.0, &mut output,
        || { polls += 1; polls >= 6 }), Err(CANCELLED));
    assert!(output.iter().any(|&v| v != 42.0));
    assert!(output.iter().any(|&v| v == 42.0));
}

#[test]
fn ffi_rejects_null_misalignment_overlap_and_bad_lengths_before_dereference() {
    let mut source = [0.7, 0.6, 0.4];
    let mask = [1.0];
    let mut output = [42.0; 3];
    let storage = [0_u8; 32];
    let address = storage.as_ptr() as usize;
    let misaligned = (address + usize::from(address % mem::align_of::<f32>() == 0)) as *const f32;
    unsafe {
        for pointer in [std::ptr::null(), misaligned] {
            assert_eq!(lrt_skin_colour_apply_v1(pointer, 3, mask.as_ptr(), 1,
                1, 1, 1.0, 1.0, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        }
        assert_eq!(lrt_skin_colour_apply_v1(source.as_ptr(), 3, mask.as_ptr(), 1,
            1, 1, 1.0, 1.0, source.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_colour_apply_v1(source.as_ptr(), 2, mask.as_ptr(), 1,
            1, 1, 1.0, 1.0, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
    }
    assert_eq!(output, [42.0; 3]);
    assert_eq!(source, [0.7, 0.6, 0.4]);
}

#[test]
fn ffi_abi_and_cancellation_callback_contract() {
    extern "C" fn cancel(_context: *mut c_void) -> i32 { 1 }
    let mut output = [42.0; 3];
    assert_eq!(lrt_skin_colour_abi(), 1);
    unsafe {
        assert_eq!(lrt_skin_colour_apply_v1([0.5; 3].as_ptr(), 3, [1.0].as_ptr(), 1,
            1, 1, 1.0, 1.0, output.as_mut_ptr(), 3, Some(cancel), std::ptr::null_mut()), CANCELLED);
    }
    assert_eq!(output, [42.0; 3]);
}
