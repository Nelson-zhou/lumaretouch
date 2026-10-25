// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. These are specifications, not evidence of compilation or quality.
use super::*;

fn pixel(y: f64, u: f64, v: f64) -> [f32; 3] {
    let green = y/(0.2126*u.exp()+0.7152+0.0722*v.exp());
    [green*u.exp(), green, green*v.exp()].map(encode)
}
fn constant(width: usize, height: usize, y: f64, u: f64, v: f64) -> (Vec<f32>, Vec<f32>) {
    ((0..width*height).flat_map(|_| pixel(y, u, v)).collect(), vec![1.0; width*height])
}
fn fixture_fit() -> Fit {
    let (r, rc) = constant(12, 10, 0.23, 0.35, -0.25);
    let (t, tc) = constant(17, 9, 0.15, 0.15, -0.40);
    fit_reference(&r, &rc, 12, 10, &t, &tc, 17, 9,
        [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA], || false).unwrap()
}
fn bits(a: &[f32], b: &[f32]) -> bool {
    a.len() == b.len() && a.iter().zip(b).all(|(x,y)| x.to_bits() == y.to_bits())
}
fn applied(current: &[f32], mask: &[f32], width: usize, height: usize, fit: &Fit) -> Vec<f32> {
    let mut output = vec![9.0; current.len()];
    apply_into(current, Some(mask), width, height, Some(fit.transform()), 1.0,
        &mut output, || false).unwrap();
    output
}

#[test]
fn independent_roi_sizes_fit_actual_colour_and_brightness_without_correspondence() {
    let fit = fixture_fit();
    let t = fit.transform();
    assert_eq!(t[0], 1.0);
    assert!((t[1]-(0.23_f64/0.15).ln()).abs() < 2e-6);
    assert!((t[2]-0.20).abs() < 2e-6);
    assert!((t[3]-0.15).abs() < 2e-6);
    let d = fit.diagnostics();
    assert_eq!(d[1], 120.0); assert_eq!(d[2], 153.0);
    assert!(d[5] >= 119.999); assert!(d[6] >= 152.999);
    assert_eq!(d[22], 0.0);
    let source = pixel(0.15, 0.15, -0.40);
    let out = applied(&source, &[1.0], 1, 1, &fit);
    let reference = pixel(0.23, 0.35, -0.25);
    assert!(out.iter().zip(reference).all(|(a,b)| (*a-b).abs() < 2e-6));
}

#[test]
fn current_stage_not_source_replay_and_interior_shading_ratio_is_retained() {
    let fit = fixture_fit();
    let mut current = Vec::new();
    current.extend(pixel(0.10, 0.05, -0.30));
    current.extend(pixel(0.20, 0.05, -0.30));
    let output = applied(&current, &[1.0; 2], 2, 1, &fit);
    let y0 = luminance([output[0], output[1], output[2]].map(decode));
    let y1 = luminance([output[3], output[4], output[5]].map(decode));
    assert!((y0-0.10*0.23/0.15).abs() < 2e-6);
    assert!((y1/y0-2.0).abs() < 2e-5);
    let corrected = [output[0], output[1], output[2]].map(decode);
    assert!(((corrected[0]/corrected[1]).ln()-0.25).abs() < 3e-6);
    assert!(((corrected[2]/corrected[1]).ln()+0.15).abs() < 3e-6);
}

#[test]
fn neutral_missing_evidence_and_zero_coverage_preserve_exact_bits() {
    let current = [-0.0, 0.0, 1.0, 0.1234567, 0.25, 0.75];
    let mut out = [8.0; 6];
    apply_into(&current, None, 2, 1, None, -0.0, &mut out, || false).unwrap();
    assert!(bits(&current, &out));
    let fit = fixture_fit();
    let out = applied(&current, &[0.0; 2], 2, 1, &fit);
    assert!(bits(&current, &out));
    let (r, rc) = constant(10, 10, 0.2, 0.3, -0.3);
    let fit = fit_reference(&r, &rc, 10, 10, &r, &rc, 10, 10,
        [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA], || false).unwrap();
    assert_eq!(fit.transform(), &[1.0, 0.0, 0.0, 0.0]);
    assert!(bits(&r, &applied(&r, &rc, 10, 10, &fit)));
}

#[test]
fn no_reliable_reference_or_target_never_fabricates_neutral_success() {
    let (r, rc) = constant(10, 10, 0.2, 0.3, -0.3);
    let absent = vec![0.0; 100];
    let limits = [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA];
    assert_eq!(fit_reference(&r, &absent, 10, 10, &r, &rc, 10, 10, limits, || false).unwrap_err(), REFERENCE_ERROR);
    assert_eq!(fit_reference(&r, &rc, 10, 10, &r, &absent, 10, 10, limits, || false).unwrap_err(), TARGET_ERROR);
    for value in [0.0, 1.0] {
        let unreliable = vec![value; 300];
        assert_eq!(fit_reference(&unreliable, &rc, 10, 10, &r, &rc, 10, 10,
            limits, || false).unwrap_err(), REFERENCE_ERROR);
    }
    assert_eq!(fit_reference(&r, &absent, 10, 10, &r, &rc, 10, 10,
        [0.0, 0.0], || false).unwrap_err(), REFERENCE_ERROR);
}

#[test]
fn evidence_checks_weight_mass_not_only_nominal_pixel_count() {
    let (r, _) = constant(20, 20, 0.2, 0.3, -0.3);
    let tiny = vec![0.01; 400];
    assert_eq!(fit_reference(&r, &tiny, 20, 20, &r, &tiny, 20, 20,
        [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA], || false).unwrap_err(), REFERENCE_ERROR);
    let mut concentrated = vec![0.001; 400];
    concentrated[..40].fill(1.0);
    assert_eq!(fit_reference(&r, &concentrated, 20, 20, &r, &concentrated, 20, 20,
        [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA], || false).unwrap_err(), REFERENCE_ERROR);
}

#[test]
fn bounded_offsets_are_separate_and_report_raw_request() {
    let (r, rc) = constant(12, 12, 0.30, 0.65, 0.10);
    let (t, tc) = constant(12, 12, 0.10, -0.20, -0.45);
    let fit = fit_reference(&r, &rc, 12, 12, &t, &tc, 12, 12, [0.12, 0.08], || false).unwrap();
    assert!((fit.transform()[1]-0.12).abs() < 1e-12);
    assert!((fit.transform()[2].hypot(fit.transform()[3])-0.08).abs() < 1e-12);
    assert_eq!((fit.diagnostics()[22] as u32)&3, 3);
    assert!(fit.diagnostics()[19] > 0.12);
    assert!(fit.diagnostics()[20].hypot(fit.diagnostics()[21]) > 0.08);
}

#[test]
fn robust_fit_rejects_minority_contamination_without_flattening_distribution() {
    let (reference, mask) = constant(20, 20, 0.23, 0.35, -0.25);
    let (clean, _) = constant(20, 20, 0.15, 0.15, -0.4);
    let mut contaminated = clean.clone();
    for i in 0..80 { contaminated[3*i..3*i+3].copy_from_slice(&pixel(0.45, -0.5, 0.5)); }
    let limits = [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA];
    let a = fit_reference(&reference, &mask, 20, 20, &clean, &mask, 20, 20, limits, || false).unwrap();
    let b = fit_reference(&reference, &mask, 20, 20, &contaminated, &mask, 20, 20, limits, || false).unwrap();
    for i in 1..4 { assert!((a.transform()[i]-b.transform()[i]).abs() < 3e-6); }
    assert_eq!(b.diagnostics()[2], 320.0);
    assert!(b.diagnostics()[23] >= 0.79 && b.diagnostics()[23] <= 0.81);
}

#[test]
fn excessive_population_dispersion_refuses_instead_of_equalizing_histograms() {
    let mut rgb = Vec::new();
    for i in 0..600 {
        rgb.extend(pixel(if i%3 == 0 { 0.055 } else if i%3 == 1 { 0.2 } else { 0.6 }, 0.1, -0.1));
    }
    let mask = vec![1.0; 600];
    assert_eq!(fit_reference(&rgb, &mask, 30, 20, &rgb, &mask, 30, 20,
        [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA], || false).unwrap_err(), DISPERSION_ERROR);
}

#[test]
fn two_level_streaming_median_tracks_an_exact_test_only_weighted_oracle() {
    let mut rgb = Vec::new();
    let mut mask = Vec::new();
    for i in 0..1025 {
        let k = (i*73)%1025;
        rgb.extend(pixel(0.08+0.2*k as f64/1024.0, 0.1+0.4*k as f64/1024.0, -0.4));
        mask.push(if i%3 == 0 { 0.25 } else { 1.0 });
    }
    let samples: Vec<_> = (0..mask.len()).filter_map(|i| observation(&rgb, &mask, i)).collect();
    let total: f64 = samples.iter().map(|s| s.weight).sum();
    let (mut low, mut high) = ([f64::INFINITY; 3], [f64::NEG_INFINITY; 3]);
    for s in &samples { for axis in 0..3 { low[axis] = low[axis].min(s.value[axis]); high[axis] = high[axis].max(s.value[axis]); } }
    let actual = median3(&rgb, &mask, total, low, high, None, None, &mut || false).unwrap();
    for axis in 0..3 {
        let mut values: Vec<_> = samples.iter().map(|s| (s.value[axis], s.weight)).collect();
        values.sort_by(|a,b| a.0.partial_cmp(&b.0).unwrap());
        let mut cumulative = 0.0;
        let mut expected = values[values.len()-1].0;
        for &(value, weight) in &values {
            cumulative += weight;
            if cumulative >= total/2.0 { expected = value; break; }
        }
        let bound = (high[axis]-low[axis])/(2.0*(HISTOGRAM_BINS*HISTOGRAM_BINS) as f64)+1e-12;
        assert!((actual[axis]-expected).abs() <= bound);
    }
}

#[test]
fn clustered_values_exercise_second_histogram_level_and_fractional_weights() {
    let mut rgb = Vec::new();
    let mut coverage = Vec::new();
    for i in 0..1024 {
        let y = if i < 200 { 0.06 } else if i >= 824 { 0.60 }
            else { 0.20*(1.0+(i-200) as f64*1e-7) };
        rgb.extend(pixel(y, 0.20, -0.20));
        coverage.push(if i%3 == 0 { 0.25 } else if i%3 == 1 { 0.5 } else { 1.0 });
    }
    let samples: Vec<_> = (0..coverage.len()).filter_map(|i| observation(&rgb, &coverage, i)).collect();
    let total: f64 = samples.iter().map(|s| s.weight).sum();
    let (mut low, mut high) = ([f64::INFINITY; 3], [f64::NEG_INFINITY; 3]);
    for s in &samples { for axis in 0..3 { low[axis] = low[axis].min(s.value[axis]); high[axis] = high[axis].max(s.value[axis]); } }
    let bin_of = |value: f64| ((value-low[0])/(high[0]-low[0])*HISTOGRAM_BINS as f64) as usize;
    assert_eq!(bin_of(samples[200].value[0]), bin_of(samples[823].value[0]));
    let actual = median3(&rgb, &coverage, total, low, high, None, None, &mut || false).unwrap();
    let mut values: Vec<_> = samples.iter().map(|s| (s.value[0], s.weight)).collect();
    values.sort_by(|a,b| a.0.partial_cmp(&b.0).unwrap());
    let (mut cumulative, mut expected) = (0.0, values[values.len()-1].0);
    for &(value, weight) in &values {
        cumulative += weight;
        if cumulative >= total/2.0 { expected = value; break; }
    }
    let bound = (high[0]-low[0])/(2.0*(HISTOGRAM_BINS*HISTOGRAM_BINS) as f64)+1e-12;
    assert!((actual[0]-expected).abs() <= bound);
}

#[test]
fn exactly_balanced_binary_weights_select_the_lower_median_side() {
    let mut rgb = Vec::new();
    for i in 0..512 { rgb.extend(pixel(if i < 256 { 0.15 } else { 0.30 }, 0.0, 0.0)); }
    let coverage = vec![0.5; 512];
    let a = observation(&rgb, &coverage, 0).unwrap();
    let b = observation(&rgb, &coverage, 256).unwrap();
    let mut low = [0.0; 3]; let mut high = [0.0; 3];
    for axis in 0..3 { low[axis] = a.value[axis].min(b.value[axis]); high[axis] = a.value[axis].max(b.value[axis]); }
    let median = median3(&rgb, &coverage, 256.0, low, high, None, None, &mut || false).unwrap();
    assert_eq!(median, a.value);
}

#[test]
fn full_frame_and_arbitrary_tiles_share_identical_application_bits() {
    let fit = fixture_fit();
    let mut rgb = Vec::new();
    let mut mask = Vec::new();
    for i in 0..1000 {
        rgb.extend(pixel(0.10+0.10*(i%31) as f64/30.0, 0.1, -0.3));
        mask.push(if i%7 == 0 { 0.0 } else { (i%5) as f32/4.0 });
    }
    let expected = applied(&rgb, &mask, 100, 10, &fit);
    let mut tiled = Vec::new();
    for start in (0..1000).step_by(137) {
        let end = (start+137).min(1000);
        tiled.extend(applied(&rgb[3*start..3*end], &mask[start..end], end-start, 1, &fit));
    }
    assert!(bits(&expected, &tiled));
}

#[test]
fn gamut_boundary_correction_is_one_shared_vector_coefficient() {
    let encoded = [0.94, 0.45, 0.35];
    let transform = [1.0, MAX_LOG_LUMINANCE, 0.35, 0.0];
    let current = encoded.map(decode);
    let strength = reliability(encoded, current);
    let colored = [current[0]*(strength*transform[2]).exp(), current[1], current[2]];
    let gain = luminance(current)*(strength*transform[1]).exp()/luminance(colored);
    let desired = colored.map(|v| v*gain);
    assert!(desired[0] > 1.0);
    let result = corrected(encoded, &transform, 1.0).unwrap().map(decode);
    let coefficients = [0,1,2].map(|c| (result[c]-current[c])/(desired[c]-current[c]));
    assert!(coefficients[0] > 0.0 && coefficients[0] < 1.0);
    assert!((coefficients[0]-coefficients[1]).abs() < 5e-6);
    assert!((coefficients[0]-coefficients[2]).abs() < 5e-6);
    assert!(result.iter().all(|v| (0.0..=1.0).contains(v)));
}

#[test]
fn unreliable_current_endpoints_remain_bit_exact_and_bad_values_refuse() {
    let fit = fixture_fit();
    let current = [-0.0, 0.0, 0.0, 1.0, 1.0, 1.0];
    assert!(bits(&current, &applied(&current, &[1.0; 2], 2, 1, &fit)));
    let bad = [f32::NAN, 0.0, 0.0];
    let mut output = [8.0; 3];
    assert_eq!(apply_into(&bad, None, 1, 1, None, 0.0, &mut output, || false), Err(PIXEL_ERROR));
    assert_eq!(output, [8.0; 3]);
    let rgb = pixel(0.2, 0.2, -0.2);
    assert_eq!(apply_into(&rgb, Some(&[1.0]), 1, 1, Some(&[1.0, 9.0, 0.0, 0.0]), 1.0,
        &mut output, || false), Err(TRANSFORM_ERROR));
    assert_eq!(output, [8.0; 3]);
}

#[test]
fn every_source_value_validates_even_outside_permission() {
    let (mut rgb, mut mask) = constant(12, 10, 0.2, 0.3, -0.3);
    mask[0] = 0.0;
    rgb[0] = f32::INFINITY;
    assert_eq!(fit_reference(&rgb, &mask, 12, 10, &rgb, &mask, 12, 10,
        [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA], || false).unwrap_err(), PIXEL_ERROR);
    rgb[0] = 0.0;
    mask[0] = f32::NAN;
    assert_eq!(fit_reference(&rgb, &mask, 12, 10, &rgb, &mask, 12, 10,
        [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA], || false).unwrap_err(), PIXEL_ERROR);
}

#[test]
fn reviewed_soft_coverage_scales_the_log_transform_not_source_pixels() {
    let fit = fixture_fit();
    let current = pixel(0.15, 0.15, -0.4);
    let output = applied(&current, &[0.25], 1, 1, &fit);
    let linear = [output[0], output[1], output[2]].map(decode);
    assert!((luminance(linear)-0.15*(0.25*fit.transform()[1]).exp()).abs() < 2e-6);
    assert!(((linear[0]/linear[1]).ln()-(0.15+0.25*fit.transform()[2])).abs() < 3e-6);
}

#[test]
fn resources_are_admitted_before_work_and_fit_scratch_is_constant() {
    assert_eq!(fit_memory_bytes(100, 100, 200, 100).unwrap(), 16*30_000+FIT_FIXED_SCRATCH_BYTES);
    assert_eq!(fit_memory_bytes(8000, 4000, 1, 1), Err(RESOURCE_ERROR));
    assert_eq!(apply_memory_bytes(1024, 1024).unwrap(), 40*1_048_576+4096);
    assert_eq!(apply_memory_bytes(1025, 1024), Err(RESOURCE_ERROR));
    assert_eq!(apply_memory_bytes(0, 1), Err(ABI_ERROR));
    assert_eq!(mem::size_of::<Bin>()*3*HISTOGRAM_BINS, 147_456);
}

extern "C" fn cancel_now(_: *mut c_void) -> i32 { 1 }
struct CancelAfter { calls: usize, limit: usize }
extern "C" fn cancel_after(context: *mut c_void) -> i32 {
    let state = unsafe { &mut *(context as *mut CancelAfter) };
    state.calls += 1;
    if state.calls > state.limit { 1 } else { 0 }
}
#[test]
fn ffi_error_cancellation_aliasing_and_neutral_publication_contract() {
    let (rgb, mask) = constant(12, 10, 0.2, 0.3, -0.3);
    let limits = [MAX_LOG_LUMINANCE, MAX_LOG_CHROMA];
    let mut transform = [7.0; 4];
    let mut diagnostics = [8.0; 24];
    let status = unsafe { lrt_skin_reference_match_fit_v1(rgb.as_ptr(), rgb.len(), mask.as_ptr(), mask.len(),
        12, 10, rgb.as_ptr(), rgb.len(), mask.as_ptr(), mask.len(), 12, 10,
        limits.as_ptr(), 2, transform.as_mut_ptr(), 4, diagnostics.as_mut_ptr(), 24,
        Some(cancel_now), ptr::null_mut()) };
    assert_eq!(status, CANCELLED); assert_eq!(transform, [7.0; 4]); assert_eq!(diagnostics, [8.0; 24]);
    let mut output = vec![6.0; rgb.len()];
    let status = unsafe { lrt_skin_reference_match_apply_v1(rgb.as_ptr(), rgb.len(), ptr::null(), 0,
        12, 10, ptr::null(), 0, 0.0, output.as_mut_ptr(), output.len(), None, ptr::null_mut()) };
    assert_eq!(status, 0); assert!(bits(&rgb, &output));
    let status = unsafe { lrt_skin_reference_match_apply_v1(rgb.as_ptr(), rgb.len(), ptr::null(), 0,
        12, 10, ptr::null(), 0, 0.0, rgb.as_ptr() as *mut f32, rgb.len(), None, ptr::null_mut()) };
    assert_eq!(status, ABI_ERROR);
    let mut overlapping = [9.0; 28];
    let status = unsafe { lrt_skin_reference_match_fit_v1(rgb.as_ptr(), rgb.len(), mask.as_ptr(), mask.len(),
        12, 10, rgb.as_ptr(), rgb.len(), mask.as_ptr(), mask.len(), 12, 10,
        limits.as_ptr(), 2, overlapping.as_mut_ptr(), 4, overlapping.as_mut_ptr().add(2), 24,
        None, ptr::null_mut()) };
    assert_eq!(status, ABI_ERROR); assert_eq!(overlapping, [9.0; 28]);
    let status = unsafe { lrt_skin_reference_match_fit_v1(rgb.as_ptr(), rgb.len(), mask.as_ptr(), mask.len(),
        12, 10, rgb.as_ptr(), rgb.len(), mask.as_ptr(), mask.len(), 12, 10,
        limits.as_ptr(), 2, transform.as_mut_ptr(), 4, diagnostics.as_mut_ptr(), 24, None, ptr::null_mut()) };
    assert_eq!(status, 0); assert_eq!(transform, [1.0, 0.0, 0.0, 0.0]);
    assert_eq!(diagnostics[0], 1.0); assert_eq!(diagnostics[1], 120.0);
    transform.fill(7.0); diagnostics.fill(8.0);
    let mut cancel = CancelAfter { calls: 0, limit: 90 };
    let status = unsafe { lrt_skin_reference_match_fit_v1(rgb.as_ptr(), rgb.len(), mask.as_ptr(), mask.len(),
        12, 10, rgb.as_ptr(), rgb.len(), mask.as_ptr(), mask.len(), 12, 10,
        limits.as_ptr(), 2, transform.as_mut_ptr(), 4, diagnostics.as_mut_ptr(), 24,
        Some(cancel_after), (&mut cancel as *mut CancelAfter).cast()) };
    assert_eq!(status, CANCELLED); assert_eq!(transform, [7.0; 4]); assert_eq!(diagnostics, [8.0; 24]);
    output.fill(6.0);
    let status = unsafe { lrt_skin_reference_match_apply_v1(rgb.as_ptr(), rgb.len(), output.as_ptr(), mask.len(),
        12, 10, [1.0, 0.1, 0.0, 0.0].as_ptr(), 4, 1.0,
        output.as_mut_ptr(), output.len(), None, ptr::null_mut()) };
    assert_eq!(status, ABI_ERROR); assert!(output.iter().all(|&v| v == 6.0));
    let mut shared = [1.0_f64, 0.1, 0.1, 0.0, 8.0];
    let before = shared;
    let status = unsafe { lrt_skin_reference_match_apply_v1(rgb.as_ptr(), 3, mask.as_ptr(), 1,
        1, 1, shared.as_ptr(), 4, 1.0, shared.as_mut_ptr().cast(), 3, None, ptr::null_mut()) };
    assert_eq!(status, ABI_ERROR); assert_eq!(shared, before);
}

#[test]
fn late_apply_cancellation_preserves_sentinel_output() {
    let fit = fixture_fit();
    let (rgb, mask) = constant(50, 40, 0.15, 0.2, -0.2);
    let mut output = vec![7.0; rgb.len()];
    let mut calls = 0;
    let result = apply_into(&rgb, Some(&mask), 50, 40, Some(fit.transform()), 1.0, &mut output,
        || { calls += 1; calls > 12 });
    assert_eq!(result, Err(CANCELLED));
    assert!(output.iter().all(|&v| v == 7.0));
}
