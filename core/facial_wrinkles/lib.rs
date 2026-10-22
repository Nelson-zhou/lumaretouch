// SPDX-License-Identifier: GPL-3.0-or-later
// Original LumaRetouch overlap composition. No RapidRetouch algorithm copied.
// Wrinkle estimation remains the attributed, pinned Python/OpenCV algorithm.
use std::slice;

#[no_mangle]
pub extern "C" fn lrt_wrinkles_abi() -> u32 { 1 }

/// Merge one source-derived lightness proposal into a shared maximum envelope.
/// All arrays are separate allocations owned by the caller. Validate the whole
/// input before writing: rejected calls never leave a partial correction.
/// This is deliberately max, NOT sum or repeated relighting. Overlap cannot
/// amplify a crease beyond the strongest independently requested proposal.
#[no_mangle]
pub unsafe extern "C" fn lrt_wrinkles_merge(
    proposal: *const f32, support: *const f32, amount: f32,
    output: *mut f32, count: usize,
) -> i32 {
    if count == 0 || count > 32_000_000 || proposal.is_null() || support.is_null()
        || output.is_null() || !amount.is_finite() || !(0.0..=1.0).contains(&amount) {
        return 1;
    }
    let lift = slice::from_raw_parts(proposal, count);
    let mask = slice::from_raw_parts(support, count);
    let out = slice::from_raw_parts_mut(output, count);
    if lift.iter().any(|v| !v.is_finite() || *v < 0.0)
        || mask.iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
        || out.iter().any(|v| !v.is_finite() || *v < 0.0 || *v > 12.0) { return 2; }
    if amount == 0.0 { return 0; }
    for i in 0..count {
        if mask[i] > 0.0 {
            out[i] = out[i].max((lift[i] * mask[i] * amount).min(12.0));
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn overlap_is_not_additive_and_zero_is_exact() {
        let lift = [2.0_f32, 4.0, 8.0];
        let mask = [1.0_f32, 0.5, 0.0];
        let mut out = [0.0_f32; 3];
        unsafe {
            assert_eq!(lrt_wrinkles_merge(lift.as_ptr(), mask.as_ptr(), 1.0, out.as_mut_ptr(), 3), 0);
            assert_eq!(lrt_wrinkles_merge(lift.as_ptr(), mask.as_ptr(), 1.0, out.as_mut_ptr(), 3), 0);
        }
        assert_eq!(out, [2.0, 2.0, 0.0]);
    }
    #[test]
    fn invalid_input_is_atomic() {
        let lift = [1.0_f32, f32::NAN]; let mask = [1.0_f32; 2]; let mut out = [0.0_f32; 2];
        unsafe { assert_eq!(lrt_wrinkles_merge(lift.as_ptr(), mask.as_ptr(), 1.0, out.as_mut_ptr(), 2), 2); }
        assert_eq!(out, [0.0; 2]);
    }
}
