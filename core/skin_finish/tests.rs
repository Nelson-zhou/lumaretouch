// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. These assertions are not numerical or visual pass evidence.
use super::*;

fn bits(values: &[f32]) -> Vec<u32> { values.iter().map(|v| v.to_bits()).collect() }
fn render(source: &[f32], coverage: &[f32], whitening: f32, rosiness: f32) -> Vec<f32> {
    let mut output = vec![42.0; source.len()];
    apply_into(source, coverage, coverage.len(), 1, whitening, rosiness, &mut output,
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
    assert_eq!(bits(&render(&source, &[-0.0, 0.0], 1.0, 1.0)), bits(&source));
    let result = render(&source, &[0.0, 1.0], 1.0, 1.0);
    assert_eq!(bits(&result[..3]), bits(&source[..3]));
    assert_ne!(bits(&result[3..]), bits(&source[3..]));
}

#[test]
fn black_and_white_are_exact_at_all_control_corners() {
    let source = [-0.0, 0.0, -0.0, 1.0, 1.0, 1.0];
    for whitening in [0.0, 0.5, 1.0] { for rosiness in [0.0, 0.5, 1.0] {
        assert_eq!(bits(&render(&source, &[1.0, 1.0], whitening, rosiness)), bits(&source));
    }}
}

#[test]
fn original_formula_has_bounded_lift_cooling_and_red_restraint() {
    let white = finish_lab([50.0, 20.0, 30.0], 1.0, 0.0);
    for (actual, expected) in white.into_iter().zip([54.5, 17.6, 24.9]) {
        assert!((actual - expected).abs() < 1e-12);
    }
    let rose_neutral = finish_lab([50.0, 0.0, 0.0], 0.0, 1.0);
    assert_eq!(rose_neutral, [50.0, 5.0, 1.25]);
    let rose_red = finish_lab([50.0, 20.0, 30.0], 0.0, 1.0);
    assert_eq!(rose_red, [50.0, 22.5, 30.625]);
    let rose_shadow = finish_lab([10.0, 0.0, 0.0], 0.0, 1.0);
    assert!(rose_shadow[1] > 0.0 && rose_shadow[1] < rose_neutral[1]);
    for l in [0.0, 100.0] {
        assert_eq!(finish_lab([l, 20.0, 30.0], 1.0, 1.0), [l, 20.0, 30.0]);
    }
}

#[test]
fn whitening_curve_is_monotone_in_lightness_and_amount() {
    for white in [0.0, 0.1, 0.5, 1.0] {
        let mut previous = -1.0;
        for index in 0..=10_000 {
            let l = index as f64 / 100.0;
            let output = finish_lab([l, 20.0, 30.0], white, 1.0)[0];
            assert!(output > previous);
            assert!(output >= l - 1e-12 && output <= l + 4.5 + 1e-12);
            assert!((0.0..=100.0).contains(&output));
            previous = output;
        }
    }
    for l in [0.01, 1.0, 8.0, 30.0, 50.0, 90.0, 99.99] {
        let mut previous = l;
        for index in 1..=100 {
            let output = finish_lab([l, 20.0, 30.0], index as f32 / 100.0, 0.0)[0];
            assert!(output > previous);
            previous = output;
        }
    }
}

#[test]
fn midgray_controls_have_distinct_lightness_and_chroma_directions() {
    let source = [0.5; 3];
    let before = lab_of(&source);
    let white = lab_of(&render(&source, &[1.0], 1.0, 0.0));
    let rose = lab_of(&render(&source, &[1.0], 0.0, 1.0));
    let l = before[0] / 100.0;
    assert!((white[0] - before[0] - 18.0 * l * (1.0 - l)).abs() < 3e-5);
    assert!(white[2] < before[2]);
    assert!((rose[0] - before[0]).abs() < 3e-5);
    assert!(rose[1] > before[1] && rose[2] > before[2]);
    assert!((rose[2] - before[2] - 0.25 * (rose[1] - before[1])).abs() < 3e-5);
}

#[test]
fn partial_coverage_is_a_linear_light_mix_not_an_encoded_rgb_blend() {
    let source = [0.72, 0.48, 0.32];
    let full = render(&source, &[1.0], 1.0, 1.0);
    let partial = render(&source, &[0.25], 1.0, 1.0);
    for c in 0..3 {
        let expected = 0.75 * decode(f64::from(source[c])) + 0.25 * decode(f64::from(full[c]));
        assert!((decode(f64::from(partial[c])) - expected).abs() < 1e-7);
    }
    assert!(lab_of(&partial)[0] > lab_of(&source)[0]);
    assert!(lab_of(&partial)[0] < lab_of(&full)[0]);
}

#[test]
fn saturated_and_near_endpoint_colours_retain_requested_lightness_in_gamut() {
    let colours = [
        [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        [1.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0],
        [0.00001; 3], [0.99999; 3], [0.002, 0.001, 0.003],
        [f32::from_bits(1); 3], [f32::from_bits(0x3f7fffff); 3],
        [0.96, 0.95, 0.93], [0.65, 0.36, 0.22], [0.2, 0.09, 0.04],
    ];
    for source in colours { for whitening in [0.0, 0.01, 0.5, 1.0] {
        for rosiness in [0.0, 0.5, 1.0] {
            let result = render(&source, &[1.0], whitening, rosiness);
            assert!(result.iter().copied().all(unit));
            let target = finish_lab(lab_of(&source), whitening, rosiness);
            assert!((lab_of(&result)[0] - target[0]).abs() < 3e-5);
        }
    }}
}

#[test]
fn gamut_compression_retains_only_feasible_common_chroma_at_requested_y() {
    let requested = [50.0, 180.0, 120.0];
    let target_y = y_from_lightness(requested[0]);
    assert!(!in_gamut(from_lab_at_y(requested, target_y)));
    let result = compress_chroma(requested, target_y);
    assert!(in_gamut(result));
    let (actual, actual_y) = to_lab(result);
    assert!((actual_y - target_y).abs() < 1e-12);
    let scale_a = actual[1] / requested[1];
    let scale_b = actual[2] / requested[2];
    assert!((0.0..1.0).contains(&scale_a));
    assert!((scale_a - scale_b).abs() < 1e-12);
    assert!((actual[0] - requested[0]).abs() < 1e-10);
}

#[test]
fn same_coverage_gray_detail_order_survives_without_neighbour_reads() {
    let source: Vec<f32> = (0..=1024).flat_map(|i| [i as f32 / 1024.0; 3]).collect();
    for coverage in [0.25, 1.0] {
        let result = render(&source, &vec![coverage; 1025], 1.0, 1.0);
        let mut previous_l = -1.0;
        for pixel in result.chunks_exact(3) {
            let current_l = lab_of(pixel)[0];
            assert!(current_l > previous_l);
            previous_l = current_l;
        }
        let mut changed = source.clone();
        changed[15..18].copy_from_slice(&[1.0, 0.0, 0.0]);
        let second = render(&changed, &vec![coverage; 1025], 1.0, 1.0);
        for i in 0..1025 { if i != 5 {
            assert_eq!(bits(&result[3*i..3*i+3]), bits(&second[3*i..3*i+3]));
        }}
    }
}

#[test]
fn repeated_render_from_same_source_is_deterministic_and_source_unchanged() {
    let source = [0.72, 0.43, 0.28, 0.05, 0.04, 0.03];
    let before = bits(&source);
    let first = render(&source, &[1.0, 0.5], 0.75, 0.25);
    assert_eq!(bits(&first), bits(&render(&source, &[1.0, 0.5], 0.75, 0.25)));
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
    for invalid in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -0.001, 1.01] {
        for (whitening, rosiness) in [(invalid, 0.0), (0.0, invalid)] {
            assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, whitening, rosiness,
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
    let mut coverage_output = [1.0_f32, 42.0, 42.0];
    let storage = [0_u8; 32];
    let address = storage.as_ptr() as usize;
    let misaligned = (address + usize::from(address % mem::align_of::<f32>() == 0)) as *const f32;
    unsafe {
        for pointer in [std::ptr::null(), misaligned] {
            assert_eq!(lrt_skin_finish_apply_v1(pointer, 3, mask.as_ptr(), 1,
                1, 1, 1.0, 1.0, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        }
        assert_eq!(lrt_skin_finish_apply_v1(source.as_ptr(), 3, mask.as_ptr(), 1,
            1, 1, 1.0, 1.0, source.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_finish_apply_v1(source.as_ptr(), 2, mask.as_ptr(), 1,
            1, 1, 1.0, 1.0, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_finish_apply_v1(source.as_ptr(), 3, coverage_output.as_ptr(), 1,
            1, 1, 1.0, 1.0, coverage_output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_finish_apply_v1(source.as_ptr(), 3, std::ptr::null(), 1,
            1, 1, 1.0, 1.0, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_finish_apply_v1(source.as_ptr(), 3, mask.as_ptr(), 1,
            1, 1, 1.0, 1.0, std::ptr::null_mut(), 3, None, std::ptr::null_mut()), ABI_ERROR);
    }
    assert_eq!(output, [42.0; 3]);
    assert_eq!(source, [0.7, 0.6, 0.4]);
    assert_eq!(coverage_output, [1.0, 42.0, 42.0]);
}

#[test]
fn ffi_abi_and_cancellation_callback_contract() {
    extern "C" fn cancel(_context: *mut c_void) -> i32 { 1 }
    let mut output = [42.0; 3];
    assert_eq!(lrt_skin_finish_abi(), 1);
    unsafe {
        assert_eq!(lrt_skin_finish_apply_v1([0.5; 3].as_ptr(), 3, [1.0].as_ptr(), 1,
            1, 1, 1.0, 1.0, output.as_mut_ptr(), 3, Some(cancel), std::ptr::null_mut()), CANCELLED);
    }
    assert_eq!(output, [42.0; 3]);
}
