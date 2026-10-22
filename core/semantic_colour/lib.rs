// SPDX-License-Identifier: GPL-3.0-or-later
//! ABI-1 fixed colour recipes. Callers retain ownership and provide valid,
//! aligned, sufficiently large, non-overlapping buffers. No unwind crosses C.
//! Only a successful call writes output; cancellation/error leaves it untouched.
mod colour;
mod fit;
use colour::{Operator, PARAMS};

#[no_mangle]
pub extern "C" fn lrt_semantic_colour_abi() -> u32 { 1 }

/// # Safety
/// r/t contain rn/tn rows of five f64 values. params/stats have capacity for
/// 7*50 / 7*10 f64 values. A cancellation callback must never unwind or free
/// these buffers; it may be called repeatedly until this function returns.
#[no_mangle]
pub unsafe extern "C" fn lrt_sc_fit(
    r: *const f64, rn: usize, t: *const f64, tn: usize, mode: u32,
    cancel: fit::Cancel, params: *mut f64, stats: *mut f64,
) -> i32 {
    if r.is_null() || t.is_null() || params.is_null() || stats.is_null()
        || !(32..=6144).contains(&rn) || !(32..=6144).contains(&tn) || mode > 1 { return 1; }
    std::panic::catch_unwind(|| {
        match fit::fit(std::slice::from_raw_parts(r, rn * 5), std::slice::from_raw_parts(t, tn * 5), mode, cancel) {
            Ok((p, s)) => {
                std::ptr::copy_nonoverlapping(p.as_ptr(), params, p.len());
                std::ptr::copy_nonoverlapping(s.as_ptr(), stats, s.len());
                0
            }
            Err(error) => error,
        }
    }).unwrap_or(99)
}

/// # Safety
/// rgb/out contain n*3 f32 values, params 50 f64, strengths three f64, and a
/// non-null mask n f32. Buffers must be valid and non-overlapping. Pass null for
/// a uniform mask. Overall/tone/colour strengths are each in [0,2].
#[no_mangle]
pub unsafe extern "C" fn lrt_sc_apply(
    rgb: *const f32, n: usize, params: *const f64, strengths: *const f64,
    mask: *const f32, out: *mut f32,
) -> i32 {
    if rgb.is_null() || params.is_null() || strengths.is_null() || out.is_null() || n > 2_000_000 { return 1; }
    std::panic::catch_unwind(|| {
        let parameters = std::slice::from_raw_parts(params, PARAMS);
        let strengths = std::slice::from_raw_parts(strengths, 3);
        if strengths.iter().any(|x| !x.is_finite() || !(0.0..=2.0).contains(x)) { return 1; }
        let operator = match Operator::new(parameters, strengths[1], strengths[2]) {
            Ok(operator) => operator, Err(_) => return 3,
        };
        let input = std::slice::from_raw_parts(rgb, n * 3);
        let weights = if mask.is_null() { None } else { Some(std::slice::from_raw_parts(mask, n)) };
        if weights.map(|m| m.iter().any(|w| !w.is_finite() || !(0.0..=1.0).contains(w))).unwrap_or(false) { return 1; }
        // Crucially use the EFFECTIVE operator after tone/colour strengths.
        // Neither f64 conversion nor a blend may disturb identity/signed zero.
        if strengths[0] == 0.0 || operator.is_neutral()
            || weights.map(|m| m.iter().all(|w| *w == 0.0)).unwrap_or(false) {
            std::ptr::copy_nonoverlapping(input.as_ptr(), out, input.len());
            return 0;
        }
        // Bounded scratch output makes active nonfinite/overflow errors atomic.
        // At the ABI limit this is 24 MB; callers should normally use tiles.
        let mut result = input.to_vec();
        for i in 0..n {
            let weight = weights.map(|m| m[i] as f64).unwrap_or(1.0);
            if weight == 0.0 { continue; }
            let value = [input[i * 3], input[i * 3 + 1], input[i * 3 + 2]];
            if value.iter().any(|x| !x.is_finite()) { return 1; }
            let changed = match operator.render(value, weight * strengths[0]) {
                Ok(changed) => changed, Err(_) => return 3,
            };
            result[i * 3..i * 3 + 3].copy_from_slice(&changed);
        }
        std::ptr::copy_nonoverlapping(result.as_ptr(), out, result.len());
        0
    }).unwrap_or(99)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn apply(input: &[f32], parameters: &[f64; PARAMS], strengths: [f64; 3], mask: Option<&[f32]>) -> (i32, Vec<f32>) {
        let mut out = vec![42.0; input.len()];
        let status = unsafe { lrt_sc_apply(input.as_ptr(), input.len() / 3, parameters.as_ptr(), strengths.as_ptr(),
            mask.map(|m| m.as_ptr()).unwrap_or(std::ptr::null()), out.as_mut_ptr()) };
        (status, out)
    }

    fn same_bits(a: &[f32], b: &[f32]) {
        assert_eq!(a.iter().map(|v| v.to_bits()).collect::<Vec<_>>(), b.iter().map(|v| v.to_bits()).collect::<Vec<_>>());
    }

    #[test]
    fn identity_preserves_extended_signed_bits() {
        let parameters = colour::identity();
        let operator = Operator::new(&parameters, 1.0, 1.0).unwrap();
        for value in [-0.0f64, -2.0, 0.5, 8.0] {
            assert_eq!(operator.apply([value; 3])[0].to_bits(), value.to_bits());
        }
        let input = [-0.0, -2.0, 8.0];
        let (status, result) = apply(&input, &parameters, [1.0; 3], None);
        assert_eq!(status, 0); same_bits(&input, &result);
    }

    #[test]
    fn effective_zero_strength_and_zero_mask_preserve_bits() {
        let mut parameters = colour::identity(); parameters[0] = 0.5; parameters[26] = 12.0;
        let input = [-0.0, -2.0, 8.0];
        for strengths in [[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]] {
            let (status, result) = apply(&input, &parameters, strengths, None);
            assert_eq!(status, 0); same_bits(&input, &result);
        }
        let (status, result) = apply(&input, &parameters, [1.0; 3], Some(&[0.0]));
        assert_eq!(status, 0); same_bits(&input, &result);
    }

    #[test]
    fn cancelled_ev_and_gain_is_an_effective_identity() {
        let mut parameters = colour::identity(); parameters[0] = 1.0;
        parameters[1..4].fill(-1.0);
        let input = [-0.0, -2.0, 8.0];
        let (status, result) = apply(&input, &parameters, [1.0; 3], None);
        assert_eq!(status, 0); same_bits(&input, &result);
    }

    #[test]
    fn generic_operator_changes_blue_not_only_skin() {
        let mut parameters = colour::identity(); parameters[0] = 0.5;
        let operator = Operator::new(&parameters, 1.0, 1.0).unwrap();
        assert!(operator.apply([0.0, 0.0, 0.4])[2] > 0.4);
    }

    #[test]
    fn same_curve_compiler_retains_endpoint_tangent() {
        let mut parameters = colour::identity(); parameters[7] = 0.3;
        let operator = Operator::new(&parameters, 1.0, 1.0).unwrap();
        assert!(operator.apply([1.5; 3])[0].is_finite());
    }

    #[test]
    fn legacy_hsv_is_sdr_and_genuine_blue_band_is_editable() {
        let mut parameters = colour::identity(); parameters[26 + 5 * 3 + 1] = -100.0;
        let operator = Operator::new(&parameters, 1.0, 1.0).unwrap();
        let result = operator.apply([0.0, 0.0, 0.8]);
        assert!((result[0] - 0.8).abs() < 1e-12 && result[0] == result[1] && result[1] == result[2]);
        assert!(operator.apply([-0.1, 0.2, 2.0]).iter().all(|v| (0.0..=1.0).contains(v)));
    }

    #[test]
    fn invalid_mask_and_active_nonfinite_input_do_not_write_output() {
        let mut parameters = colour::identity(); parameters[0] = 0.5;
        let input = [0.2, 0.3, 0.4, 0.5, 0.6, f32::NAN];
        let (status, result) = apply(&input, &parameters, [1.0; 3], None);
        assert_eq!(status, 1); assert_eq!(result, vec![42.0; 6]);
        let (status, result) = apply(&input, &parameters, [1.0; 3], Some(&[1.0, f32::NAN]));
        assert_eq!(status, 1); assert_eq!(result, vec![42.0; 6]);
    }

    #[test]
    fn inactive_nonfinite_pixel_is_copied_not_evaluated() {
        let mut parameters = colour::identity(); parameters[0] = 0.5;
        let input = [f32::from_bits(0x7fc00019), -0.0, f32::INFINITY];
        let (status, result) = apply(&input, &parameters, [1.0; 3], Some(&[0.0]));
        assert_eq!(status, 0); same_bits(&input, &result);
    }

    #[test]
    fn ffi_and_fitter_share_the_same_masked_float32_endpoint() {
        let mut parameters = colour::identity();
        parameters[0] = 0.3; parameters[1] = -0.15; parameters[4] = 12.0; parameters[7] = 0.31;
        let strengths = [1.3, 0.7, 0.6];
        let input = [0.11, 0.37, 0.64];
        let (status, output) = apply(&input, &parameters, strengths, Some(&[0.4]));
        let operator = Operator::new(&parameters, strengths[1], strengths[2]).unwrap();
        let expected = operator.render(input, (0.4f32 as f64) * strengths[0]).unwrap();
        assert_eq!(status, 0); same_bits(&output, &expected);
    }

    #[test]
    fn finite_f64_but_overflowing_f32_output_is_rejected() {
        let mut parameters = colour::identity(); parameters[0] = 2.0;
        let (status, result) = apply(&[f32::MAX; 3], &parameters, [2.0; 3], None);
        assert_eq!(status, 3); assert_eq!(result, vec![42.0; 3]);
    }
}
