// SPDX-License-Identifier: GPL-3.0-or-later
//! One optional hint rule, not a people census or a closed-eye classifier.
//! The adapter verifies source/model provenance before setting `verified=1`.
//! No selection, flags, score, focus metric, file I/O or inference authority.

pub const ABI: u32 = 1;
pub const DETECTION_LIMIT: u32 = 32;
// Return codes: 0 disabled, 1 unknown, 2 below/equal, 3 omit, -1 invalid.
#[no_mangle]
pub extern "C" fn lrt_pick_group_eye_abi() -> u32 { ABI }

#[no_mangle]
pub extern "C" fn lrt_pick_group_eye_evaluate_v1(
    more_than: u32, verified: u32, detected: u32, limit: u32,
) -> i32 {
    if more_than >= DETECTION_LIMIT || verified > 1 { return -1; }
    if more_than == 0 { return 0; } // explicit disabled sentinel, never count 0
    if verified == 0 { return 1; }
    if limit != DETECTION_LIMIT || detected == 0 || detected > limit { return 1; }
    // At the detector cap this still proves > N detected faces, not total people.
    if detected > more_than { 3 } else { 2 }
}

#[cfg(test)]
#[path = "tests_unrun.rs"]
mod tests;
