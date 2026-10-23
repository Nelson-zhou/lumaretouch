// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED UNRUN. These are acceptance assertions, not measured results.
use super::*;

const W: usize = 65;
const H: usize = 33;

fn whole() -> Tile { Tile { x: 0, y: 0, width: W, height: H } }
fn settings() -> Settings { Settings { strength: 1.0, ..Settings::default() } }
fn step(low: f32, high: f32) -> Vec<f32> {
    (0..W * H).flat_map(|i| { let v = if i % W < 32 { low } else { high }; [v; 3] }).collect()
}
fn halos(low: f32, high: f32, amplitude: f32) -> (Vec<f32>, Vec<f32>) {
    let guide = step(low, high);
    let mut edited = guide.clone();
    for y in 0..H {
        for (x, delta) in [(30, -amplitude), (31, -amplitude), (32, amplitude), (33, amplitude)] {
            for c in 0..3 { edited[3 * (y * W + x) + c] += delta; }
        }
    }
    (edited, guide)
}
fn render(edited: &[f32], guide: &[f32], coverage: Option<&[f32]>, options: Settings) -> Vec<f32> {
    render_tile(edited, guide, W, H, coverage, whole(), options, &|| false).unwrap()
}
fn bits_equal(a: &[f32], b: &[f32]) -> bool {
    a.iter().map(|v| v.to_bits()).eq(b.iter().map(|v| v.to_bits()))
}

#[test]
fn neutral_strength_is_bitwise_identity_with_signed_hdr() {
    let edited: Vec<f32> = (0..W * H).flat_map(|_| [-0.0, -2.0, 12.0]).collect();
    let guide = vec![f32::NAN; edited.len()]; // Neutral path does not read guide data.
    let out = render(&edited, &guide, None, Settings { strength: 0.0, ..settings() });
    assert!(bits_equal(&edited, &out));
}

#[test]
fn unchanged_original_and_thin_features_are_preserved() {
    let mut source = step(0.2, 0.8);
    for y in 0..H {
        for x in [18, 28, 35, 46] {
            for c in 0..3 { source[3 * (y * W + x) + c] = if x < 32 { 0.02 } else { 1.2 }; }
        }
    }
    assert!(bits_equal(&source, &render(&source, &source, None, settings())));
}

#[test]
fn additive_global_edit_is_not_reverted() {
    let guide = step(-0.4, 1.3);
    let edited: Vec<f32> = guide.iter().map(|v| *v + 0.25).collect();
    assert!(bits_equal(&edited, &render(&edited, &guide, None, settings())));
}

#[test]
fn grayscale_affine_grade_does_not_trigger_halo_repair() {
    let guide = step(0.2, 0.8);
    let edited: Vec<f32> = guide.iter().map(|v| *v * 1.2 + 0.1).collect();
    assert!(bits_equal(&edited, &render(&edited, &guide, None, settings())));
}

#[test]
fn black_and_white_edit_lobes_move_toward_reference_without_crossing() {
    let (edited, guide) = halos(0.2, 0.8, 0.1);
    let out = render(&edited, &guide, None, settings());
    let black = 3 * (16 * W + 31);
    let white = 3 * (16 * W + 33);
    assert!(out[black] > edited[black] && out[black] <= guide[black] + 1.0e-6);
    assert!(out[white] < edited[white] && out[white] >= guide[white] - 1.0e-6);
}

#[test]
fn zero_manual_coverage_never_forces_or_changes_pixels() {
    let (edited, guide) = halos(0.2, 0.8, 0.1);
    let mask = vec![0.0; W * H];
    assert!(bits_equal(&edited, &render(&edited, &guide, Some(&mask), settings())));
}

#[test]
fn strength_and_coverage_attenuate_the_same_detected_repair() {
    let (edited, guide) = halos(0.2, 0.8, 0.1);
    let full = render(&edited, &guide, None, settings());
    let half = render(&edited, &guide, None, Settings { strength: 0.5, ..settings() });
    let mask = vec![0.5; W * H];
    let covered = render(&edited, &guide, Some(&mask), settings());
    assert!(bits_equal(&half, &covered));
    for i in 0..edited.len() { assert!((half[i] - 0.5 * (edited[i] + full[i])).abs() < 2.0e-7); }
}

#[test]
fn global_coordinates_make_tile_partitions_identical() {
    let (edited, guide) = halos(0.2, 0.8, 0.1);
    let full = render(&edited, &guide, None, settings());
    let left = render_tile(&edited, &guide, W, H, None,
        Tile { x: 0, y: 0, width: 32, height: H }, settings(), &|| false).unwrap();
    let right = render_tile(&edited, &guide, W, H, None,
        Tile { x: 32, y: 0, width: W - 32, height: H }, settings(), &|| false).unwrap();
    for y in 0..H {
        assert!(bits_equal(&full[3 * y * W..3 * (y * W + 32)], &left[3 * y * 32..3 * (y + 1) * 32]));
        assert!(bits_equal(&full[3 * (y * W + 32)..3 * (y + 1) * W],
            &right[3 * y * (W - 32)..3 * (y + 1) * (W - 32)]));
    }
}

#[test]
fn hdr_and_negative_values_remain_extended_range() {
    for (low, high) in [(-4.0, -1.0), (2.0, 5.0)] {
        let (edited, guide) = halos(low, high, 0.4);
        let out = render(&edited, &guide, None, settings());
        let i = 3 * (16 * W + 31);
        assert!(out[i] > edited[i] && out[i] <= guide[i] + 1.0e-5);
        assert!(out.iter().all(|v| v.is_finite()));
        if high < 0.0 { assert!(out.iter().all(|v| *v < 0.0)); }
        if low > 1.0 { assert!(out.iter().all(|v| *v > 1.0)); }
    }
}

#[test]
fn single_pixel_noise_has_no_tangential_support() {
    let guide = step(0.2, 0.8);
    let mut edited = guide.clone();
    for c in 0..3 { edited[3 * (16 * W + 31) + c] -= 0.1; }
    assert!(bits_equal(&edited, &render(&edited, &guide, None, settings())));
}

#[test]
fn pure_red_fringe_is_not_alias_for_chromatic_defringe() {
    let guide = step(0.2, 0.8);
    let mut edited = guide.clone();
    for y in 0..H { edited[3 * (y * W + 31)] += 0.3; }
    assert!(bits_equal(&edited, &render(&edited, &guide, None, settings())));
}

#[test]
fn invalid_settings_and_missing_guide_rejected() {
    let source = step(0.2, 0.8);
    assert_eq!(render_tile(&source, &[], W, H, None, whole(), settings(), &|| false).unwrap_err(), ABI_ERROR);
    assert_eq!(render_tile(&source, &source, W, H, None, whole(),
        Settings { scale: 0.0, ..settings() }, &|| false).unwrap_err(), SETTINGS_ERROR);
    assert_eq!(lrt_fringe_required_halo(2.0, 1.0), 15);
    assert_eq!(lrt_fringe_required_halo(32.0, 8.0), 1793);
    assert_eq!(lrt_fringe_required_halo(2.0, f32::NAN), 0);
}

#[test]
fn cancelled_work_returns_no_tile() {
    let source = step(0.2, 0.8);
    assert_eq!(render_tile(&source, &source, W, H, None, whole(), settings(), &|| true).unwrap_err(), CANCELLED);
}

unsafe fn ffi(edited: &[f32], guide: &[f32], out: *mut f32,
    cancel: Option<extern "C" fn(*mut c_void) -> i32>) -> i32 {
    lrt_fringe_repair_tile(edited.as_ptr(), edited.len(), guide.as_ptr(), guide.len(), W, H,
        ptr::null(), 0, 0, 0, W, H, 1.0, 2.0, 1.0, 0.02, out, edited.len(), cancel, ptr::null_mut())
}

#[test]
fn ffi_pixel_failure_and_cancel_leave_sentinel_untouched() {
    let (mut edited, guide) = halos(0.2, 0.8, 0.1);
    edited[0] = f32::NAN;
    let mut out = vec![-17.25; edited.len()];
    let before = out.clone();
    assert_eq!(unsafe { ffi(&edited, &guide, out.as_mut_ptr(), None) }, PIXEL_ERROR);
    assert!(bits_equal(&out, &before));
    extern "C" fn cancelled(_: *mut c_void) -> i32 { 1 }
    assert_eq!(unsafe { ffi(&guide, &guide, out.as_mut_ptr(), Some(cancelled)) }, CANCELLED);
    assert!(bits_equal(&out, &before));
}

#[test]
fn ffi_rejects_output_alias_before_mutation() {
    let (mut edited, guide) = halos(0.2, 0.8, 0.1);
    let pointer = edited.as_mut_ptr();
    let before = edited.clone();
    assert_eq!(unsafe { ffi(&edited, &guide, pointer, None) }, ABI_ERROR);
    assert!(bits_equal(&edited, &before));
}

#[test]
fn validation_rejects_nonfinite_rgb_and_invalid_coverage() {
    let bad = [0.0, f32::INFINITY, 0.0];
    assert_eq!(unsafe { lrt_fringe_validate_rgb(bad.as_ptr(), 3, 1, 1) }, PIXEL_ERROR);
    let mask = [-0.01];
    assert_eq!(unsafe { lrt_fringe_validate_coverage(mask.as_ptr(), 1, 1, 1) }, PIXEL_ERROR);
}
