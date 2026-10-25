// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. These assertions are future acceptance, not passed results.
use super::*;

const WIDTH: u32 = 16;
const HEIGHT: u32 = 8;
fn fixture() -> (Vec<f32>, Vec<f32>, Vec<f32>, Vec<f32>) {
    let mut rgb = Vec::new();
    let mut roots = Vec::new();
    let mut tips = Vec::new();
    for y in 0..HEIGHT {
        for _x in 0..WIDTH {
            rgb.extend_from_slice(if y < HEIGHT / 2 { &[0.55, 0.30, 0.18] } else { &[0.20, 0.38, 0.50] });
            roots.push(if y < HEIGHT / 2 { 1.0 } else { 0.0 });
            tips.push(if y >= HEIGHT / 2 { 1.0 } else { 0.0 });
        }
    }
    (rgb, vec![1.0; (WIDTH * HEIGHT) as usize], roots, tips)
}
fn measured(amount: f32) -> ReferenceV1 {
    let (rgb, hair, roots, tips) = fixture();
    let mut reference = ReferenceV1::default();
    let code = unsafe { lrt_hair_unification_measure_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, roots.as_ptr(), roots.len() as u64,
        tips.as_ptr(), tips.len() as u64, WIDTH, HEIGHT, amount,
        ptr::null(), &mut reference, None, ptr::null_mut()) };
    assert_eq!(code, OK);
    reference
}
fn applied(rgb: &[f32], hair: &[f32], amount: f32, reference: &ReferenceV1) -> Vec<f32> {
    let mut output = vec![-12.0; rgb.len()];
    let code = unsafe { lrt_hair_unification_compose_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, 0, 0, WIDTH, HEIGHT, amount,
        reference, ptr::null(), output.as_mut_ptr(), output.len() as u64, None, ptr::null_mut()) };
    assert_eq!(code, OK);
    output
}
fn bits_equal(a: &[f32], b: &[f32]) -> bool {
    a.iter().map(|x| x.to_bits()).eq(b.iter().map(|x| x.to_bits()))
}
#[test]
fn c_layout_and_direction_are_explicit() {
    assert_eq!(mem::size_of::<ReferenceV1>(), 104);
    assert_eq!(mem::size_of::<LimitsV1>(), 32);
    let roots = measured(1.0);
    let tips = measured(-1.0);
    assert_eq!(roots.direction, 1);
    assert_eq!(tips.direction, -1);
    assert!(roots.chroma_ratio[0] > tips.chroma_ratio[0]);
    assert!(roots.chroma_ratio[2] < tips.chroma_ratio[2]);
    assert!(luminance(roots.chroma_ratio).abs() < 1.0e-12);
}
#[test]
fn neutral_is_bit_exact_without_evidence_and_preserves_nan_payload() {
    let rgb = vec![f32::from_bits(0x7fc00042), -0.0, 12.0];
    let mut output = vec![0.0; 3];
    let code = unsafe { lrt_hair_unification_compose_v1(rgb.as_ptr(), 3, ptr::null(), 0,
        0, 0, 1, 1, -0.0, ptr::null(), ptr::null(), output.as_mut_ptr(), 3, None, ptr::null_mut()) };
    assert_eq!(code, OK);
    assert!(bits_equal(&rgb, &output));
}
#[test]
fn current_luminance_not_measurement_luminance_is_preserved() {
    let reference = measured(1.0);
    let (mut rgb, hair, _, _) = fixture();
    for (i, p) in rgb.chunks_exact_mut(3).enumerate() {
        let scale = 0.60 + (i % 7) as f32 * 0.05;
        for channel in p { *channel *= scale; }
    }
    let output = applied(&rgb, &hair, 0.75, &reference);
    for i in 0..hair.len() {
        assert!((luminance(linear_pixel(&rgb, i)) - luminance(linear_pixel(&output, i))).abs() < 2.0e-7);
    }
}
#[test]
fn selected_reference_and_uncovered_pixels_are_bit_exact_when_excluded() {
    let (rgb, mut target, roots, _) = fixture();
    for i in 0..target.len() { if roots[i] > 0.0 { target[i] = 0.0; } }
    target[target_len() - 1] = 0.0;
    let output = applied(&rgb, &target, 1.0, &measured(1.0));
    for i in 0..target.len() {
        if target[i] == 0.0 { assert!(bits_equal(&rgb[3 * i..3 * i + 3], &output[3 * i..3 * i + 3])); }
    }
}
fn target_len() -> usize { (WIDTH * HEIGHT) as usize }
#[test]
fn dark_and_white_pixels_are_exactly_protected() {
    let (mut rgb, hair, _, _) = fixture();
    rgb[0..3].copy_from_slice(&[0.0, -0.0, 0.0]);
    rgb[3..6].copy_from_slice(&[1.0, 1.0, 1.0]);
    let output = applied(&rgb, &hair, 1.0, &measured(1.0));
    assert!(bits_equal(&rgb[..6], &output[..6]));
}
#[test]
fn amount_sign_mismatch_fails_without_output_write() {
    let (rgb, hair, _, _) = fixture();
    let reference = measured(1.0);
    let mut output = vec![-12.0; rgb.len()];
    let before = output.clone();
    let code = unsafe { lrt_hair_unification_compose_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, 0, 0, WIDTH, HEIGHT, -1.0,
        &reference, ptr::null(), output.as_mut_ptr(), output.len() as u64, None, ptr::null_mut()) };
    assert_eq!(code, ABI_ERROR);
    assert!(bits_equal(&output, &before));
}
#[test]
fn empty_dark_and_low_support_references_refuse() {
    let (rgb, hair, mut roots, tips) = fixture();
    let mut output = ReferenceV1 { direction: 47, ..ReferenceV1::default() };
    for mode in 0..3 {
        roots.fill(0.0);
        if mode == 1 { roots[0] = 1.0; }
        if mode == 2 { for v in &mut roots[..64] { *v = 1.0; } }
        let input = if mode == 2 { vec![0.0; rgb.len()] } else { rgb.clone() };
        let code = unsafe { lrt_hair_unification_measure_v1(input.as_ptr(), input.len() as u64,
            hair.as_ptr(), hair.len() as u64, roots.as_ptr(), roots.len() as u64,
            tips.as_ptr(), tips.len() as u64, WIDTH, HEIGHT, 1.0,
            ptr::null(), &mut output, None, ptr::null_mut()) };
        assert_eq!(code, UNRELIABLE_REFERENCE);
        assert_eq!(output.direction, 47);
    }
}
#[test]
fn overlapping_root_and_tip_marks_refuse_as_ambiguous() {
    let (rgb, hair, roots, mut tips) = fixture();
    tips[0] = 0.1;
    let mut output = ReferenceV1::default();
    let code = unsafe { lrt_hair_unification_measure_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, roots.as_ptr(), roots.len() as u64,
        tips.as_ptr(), tips.len() as u64, WIDTH, HEIGHT, 1.0,
        ptr::null(), &mut output, None, ptr::null_mut()) };
    assert_eq!(code, AMBIGUOUS_REFERENCE);
}
#[test]
fn incompatible_bimodal_reference_is_not_silently_averaged() {
    let (mut rgb, hair, roots, tips) = fixture();
    for i in 0..32 { rgb[3 * i..3 * i + 3].copy_from_slice(&[0.10, 0.35, 0.65]); }
    let mut output = ReferenceV1::default();
    let code = unsafe { lrt_hair_unification_measure_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, roots.as_ptr(), roots.len() as u64,
        tips.as_ptr(), tips.len() as u64, WIDTH, HEIGHT, 1.0,
        ptr::null(), &mut output, None, ptr::null_mut()) };
    assert_eq!(code, UNRELIABLE_REFERENCE);
}
#[test]
fn late_bad_pixel_keeps_every_output_byte_unchanged() {
    let (mut rgb, hair, _, _) = fixture();
    let last = rgb.len() - 1;
    rgb[last] = f32::NAN;
    let mut output = vec![0.123; rgb.len()];
    let before = output.clone();
    let code = unsafe { lrt_hair_unification_compose_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, 0, 0, WIDTH, HEIGHT, 1.0,
        &measured(1.0), ptr::null(), output.as_mut_ptr(), output.len() as u64, None, ptr::null_mut()) };
    assert_eq!(code, VALUE_ERROR);
    assert!(bits_equal(&output, &before));
}
#[test]
fn in_place_alias_is_rejected_even_when_neutral() {
    let mut rgb = vec![0.5; 3];
    let code = unsafe { lrt_hair_unification_compose_v1(rgb.as_ptr(), 3, ptr::null(), 0,
        0, 0, 1, 1, 0.0, ptr::null(), ptr::null(), rgb.as_mut_ptr(), 3, None, ptr::null_mut()) };
    assert_eq!(code, ABI_ERROR);
}
unsafe extern "C" fn cancel_now(_context: *mut c_void) -> u32 { 1 }
#[test]
fn cancellation_and_budget_refusal_do_not_commit() {
    let (rgb, hair, _, _) = fixture();
    let reference = measured(1.0);
    let mut output = vec![0.123; rgb.len()];
    let before = output.clone();
    let code = unsafe { lrt_hair_unification_compose_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, 0, 0, WIDTH, HEIGHT, 1.0,
        &reference, ptr::null(), output.as_mut_ptr(), output.len() as u64, Some(cancel_now), ptr::null_mut()) };
    assert_eq!(code, CANCELLED);
    let limits = LimitsV1 { max_work_units: 1, ..LimitsV1::default() };
    let code = unsafe { lrt_hair_unification_compose_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, 0, 0, WIDTH, HEIGHT, 1.0,
        &reference, &limits, output.as_mut_ptr(), output.len() as u64, None, ptr::null_mut()) };
    assert_eq!(code, LIMIT_ERROR);
    assert!(bits_equal(&output, &before));
}
#[test]
fn composing_rows_matches_whole_tile_bit_for_bit() {
    let (rgb, hair, _, _) = fixture();
    let reference = measured(-1.0);
    let whole = applied(&rgb, &hair, -0.85, &reference);
    let mut assembled = vec![0.0; rgb.len()];
    for row in 0..HEIGHT as usize {
        let start = row * WIDTH as usize;
        let mut tile = vec![0.0; WIDTH as usize * 3];
        let code = unsafe { lrt_hair_unification_compose_v1(rgb[3 * start..].as_ptr(), WIDTH as u64 * 3,
            hair[start..].as_ptr(), WIDTH as u64, 0, row as u32, WIDTH, 1, -0.85,
            &reference, ptr::null(), tile.as_mut_ptr(), tile.len() as u64, None, ptr::null_mut()) };
        assert_eq!(code, OK);
        assembled[3 * start..3 * start + tile.len()].copy_from_slice(&tile);
    }
    assert!(bits_equal(&whole, &assembled));
}
#[test]
fn gamut_target_contracts_the_common_chroma_vector_without_channel_clipping() {
    let q = [2.0, -0.5, -(W[0] * 2.0 - W[1] * 0.5) / W[2]];
    for y in [0.01, 0.25, 0.50, 0.90] {
        let target = gamut_target(y, q).unwrap();
        assert!(target.iter().all(|v| (0.0..=1.0).contains(v)));
        assert!((luminance(target) - y).abs() < 1.0e-12);
        let a = (target[0] - y) / q[0];
        let b = (target[1] - y) / q[1];
        assert!((a - b).abs() < 1.0e-12);
    }
}

#[test]
fn explicit_full_grid_matches_legacy_bit_for_bit() {
    let (rgb, hair, _, _) = fixture();
    let reference = measured(1.0);
    let legacy = applied(&rgb, &hair, 0.7, &reference);
    let mut explicit = vec![0.0; rgb.len()];
    let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, WIDTH, HEIGHT, 0, 0, WIDTH, HEIGHT, 0.7,
        &reference, ptr::null(), explicit.as_mut_ptr(), explicit.len() as u64, None, ptr::null_mut()) };
    assert_eq!(code, OK);
    assert!(bits_equal(&legacy, &explicit));
}

#[test]
fn explicit_preview_uses_genuine_full_source_reference_without_rewriting_it() {
    let reference = measured_preview_source(-1.0);
    let source_width = reference.source_width;
    let source_height = reference.source_height;
    let selected_pixels = reference.selected_pixels;
    let reliable_pixels = reference.reliable_pixels;
    let chroma = reference.chroma_ratio;
    // These are already-prepared CURRENT-stage preview pixels. This fixture
    // exercises the ABI; the core does not resize the source to make them.
    let rgb: Vec<f32> = (0..88 * 40).flat_map(|_| [0.3, 0.4, 0.2]).collect();
    let target = vec![1.0; 88 * 40];
    let mut preview = vec![0.0; rgb.len()];
    let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb.as_ptr(), rgb.len() as u64,
        target.as_ptr(), target.len() as u64, 88, 40, 0, 0, 88, 40, -0.7,
        &reference, ptr::null(), preview.as_mut_ptr(), preview.len() as u64, None, ptr::null_mut()) };
    assert_eq!(code, OK);
    for i in 0..target.len() {
        assert!((luminance(linear_pixel(&rgb, i)) - luminance(linear_pixel(&preview, i))).abs() < 2.0e-7);
    }
    assert_eq!((reference.source_width, reference.source_height), (source_width, source_height));
    assert_eq!((reference.selected_pixels, reference.reliable_pixels), (selected_pixels, reliable_pixels));
    assert_eq!(reference.chroma_ratio, chroma);
}

fn measured_preview_source(amount: f32) -> ReferenceV1 {
    // Genuine 128x64 full-source measurement. At budget 4096, canonical
    // proxy_size's floor-to-8 dimensions are 88x40, not a one-pixel rounding.
    let rgb: Vec<f32> = (0..128 * 64).flat_map(|i| {
        if i < 128 * 32 { [0.55, 0.30, 0.18] } else { [0.20, 0.38, 0.50] }
    }).collect();
    let hair = vec![1.0_f32; 128 * 64];
    let roots: Vec<f32> = (0..128 * 64).map(|i| if i < 128 * 32 { 1.0 } else { 0.0 }).collect();
    let tips: Vec<f32> = roots.iter().map(|v| 1.0 - *v).collect();
    let mut reference = ReferenceV1::default();
    let code = unsafe { lrt_hair_unification_measure_v1(rgb.as_ptr(), rgb.len() as u64,
        hair.as_ptr(), hair.len() as u64, roots.as_ptr(), roots.len() as u64,
        tips.as_ptr(), tips.len() as u64, 128, 64, amount,
        ptr::null(), &mut reference, None, ptr::null_mut()) };
    assert_eq!(code, OK);
    reference
}

#[test]
fn explicit_projection_matches_downward_align8_not_one_pixel_tolerance() {
    let reference = measured_preview_source(1.0);
    assert!(validate_grid_projection(128, 64, &reference).is_ok());
    assert!(validate_grid_projection(88, 40, &reference).is_ok());
    assert_eq!(validate_grid_projection(87, 40, &reference), Err(ABI_ERROR));
    assert_eq!(validate_grid_projection(136, 64, &reference), Err(ABI_ERROR));
    assert_eq!(validate_grid_projection(88, 8, &reference), Err(ABI_ERROR));
    assert_eq!(validate_grid_projection(96, 40, &reference), Err(ABI_ERROR)); // open interval boundary
    assert_eq!(validate_grid_projection(0, 40, &reference), Err(ABI_ERROR));
    // Shape-only unit records exercise the projection predicate; they are NOT
    // measured references and must never be passed to the active compose ABI.
    let shape = ReferenceV1 { source_width: 6000, source_height: 4000, ..ReferenceV1::default() };
    assert!(validate_grid_projection(3464, 2304, &shape).is_ok());
    assert_eq!(validate_grid_projection(3464, 1600, &shape), Err(ABI_ERROR));
    let unaligned_full = ReferenceV1 { source_width: 6001, source_height: 4003, ..ReferenceV1::default() };
    assert!(validate_grid_projection(6001, 4003, &unaligned_full).is_ok());
    let tiny = ReferenceV1 { source_width: 4, source_height: 2000, ..ReferenceV1::default() };
    assert_eq!(validate_grid_projection(8, 512, &tiny), Err(ABI_ERROR));
}

#[test]
fn explicit_neutral_ignores_reference_but_requires_tile_inside_declared_grid() {
    let rgb = vec![f32::from_bits(0x7fc00042), -0.0, 12.0];
    let mut output = vec![0.123; 3];
    let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb.as_ptr(), 3, ptr::null(), 0,
        8, 4, 7, 3, 1, 1, 0.0, ptr::null(), ptr::null(),
        output.as_mut_ptr(), 3, None, ptr::null_mut()) };
    assert_eq!(code, OK);
    assert!(bits_equal(&rgb, &output));
    let before = output.clone();
    let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb.as_ptr(), 3, ptr::null(), 0,
        8, 4, 8, 3, 1, 1, 0.0, ptr::null(), ptr::null(),
        output.as_mut_ptr(), 3, None, ptr::null_mut()) };
    assert_eq!(code, ABI_ERROR);
    assert!(bits_equal(&before, &output));
}

#[test]
fn explicit_bad_grid_cancellation_and_alias_never_publish() {
    let reference = measured_preview_source(1.0);
    let mut rgb = vec![0.3; 3];
    let target = [1.0_f32];
    let mut output = vec![0.123; 3];
    let before = output.clone();
    let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb.as_ptr(), 3, target.as_ptr(), 1,
        88, 8, 0, 0, 1, 1, 1.0, &reference, ptr::null(),
        output.as_mut_ptr(), 3, None, ptr::null_mut()) };
    assert_eq!(code, ABI_ERROR);
    assert!(bits_equal(&before, &output));
    let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb.as_ptr(), 3, target.as_ptr(), 1,
        88, 40, 0, 0, 1, 1, 1.0, &reference, ptr::null(),
        output.as_mut_ptr(), 3, Some(cancel_now), ptr::null_mut()) };
    assert_eq!(code, CANCELLED);
    assert!(bits_equal(&before, &output));
    let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb.as_ptr(), 3, ptr::null(), 0,
        8, 4, 0, 0, 1, 1, 0.0, ptr::null(), ptr::null(),
        rgb.as_mut_ptr(), 3, None, ptr::null_mut()) };
    assert_eq!(code, ABI_ERROR);
}

#[test]
fn explicit_preview_row_tiles_match_whole_preview() {
    let reference = measured_preview_source(-1.0);
    let rgb: Vec<f32> = (0..88 * 40).flat_map(|i| [0.2 + (i % 4) as f32 * 0.04, 0.3, 0.4]).collect();
    let target = vec![1.0; 88 * 40];
    let mut whole = vec![0.0; rgb.len()];
    let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb.as_ptr(), rgb.len() as u64,
        target.as_ptr(), target.len() as u64, 88, 40, 0, 0, 88, 40, -0.8,
        &reference, ptr::null(), whole.as_mut_ptr(), whole.len() as u64, None, ptr::null_mut()) };
    assert_eq!(code, OK);
    let mut assembled = vec![0.0; rgb.len()];
    for row in 0..40_usize {
        let mut tile = vec![0.0; 264];
        let code = unsafe { lrt_hair_unification_compose_grid_v1(rgb[264 * row..].as_ptr(), 264,
            target[88 * row..].as_ptr(), 88, 88, 40, 0, row as u32, 88, 1, -0.8,
            &reference, ptr::null(), tile.as_mut_ptr(), 264, None, ptr::null_mut()) };
        assert_eq!(code, OK);
        assembled[264 * row..264 * row + 264].copy_from_slice(&tile);
    }
    assert!(bits_equal(&whole, &assembled));
}
