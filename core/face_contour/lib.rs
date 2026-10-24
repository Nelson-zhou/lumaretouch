// SPDX-License-Identifier: GPL-3.0-or-later
//! Original bounded 2D face-contour control displacements. AUTHORED / UNRUN.
//! No TPS solver, RGB sampler, model, anatomy inference or copied commercial code.

use std::{mem, panic, slice};

pub const MAX_CONTROLS: usize = 256;
pub const REGION_GAIN: f64 = 0.035;
pub const MAX_DISPLACEMENT: f64 = 0.08;
pub const FRAME_TOLERANCE: f64 = 1.0e-6;
pub const ABI_ERROR: i32 = 1;
pub const VALUE_ERROR: i32 = 2;
pub const FRAME_ERROR: i32 = 3;
pub const BOUND_ERROR: i32 = 4;
pub const PANIC_ERROR: i32 = 5;

fn span(pointer: *const f64, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f64>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f64>() != 0
        || bytes > isize::MAX as usize
    {
        return Err(ABI_ERROR);
    }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}

fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

fn validate_frame(frame: &[f64]) -> Result<(), i32> {
    let right_norm = frame[0].hypot(frame[1]);
    let up_norm = frame[2].hypot(frame[3]);
    if !right_norm.is_finite() || !up_norm.is_finite()
        || (right_norm - 1.0).abs() > FRAME_TOLERANCE
        || (up_norm - 1.0).abs() > FRAME_TOLERANCE
        || (frame[0] * frame[2] + frame[1] * frame[3]).abs() > FRAME_TOLERANCE
        || frame[6] <= 0.0
    {
        return Err(FRAME_ERROR);
    }
    Ok(())
}

fn evaluate(
    points: &[f64], roles: &[f64], sides: &[f64], frame: &[f64], values: &[f64],
    scratch: &mut [f64; MAX_CONTROLS * 2],
) -> Result<(), i32> {
    if points.iter().chain(roles).chain(sides).chain(frame).chain(values)
        .any(|value| !value.is_finite())
        || roles.iter().any(|value| !(0.0..=1.0).contains(value))
        || sides.iter().any(|value| *value != 1.0 && *value != -1.0)
        || values.iter().any(|value| !(-1.0..=1.0).contains(value))
    {
        return Err(VALUE_ERROR);
    }
    validate_frame(frame)?;
    for i in 0..sides.len() {
        // Subject left is +head-right (MediaPipe LEFT / viewer right), not
        // the left edge of the displayed image. Host verifies this identity.
        let side_index = if sides[i] == 1.0 { 0 } else { 1 };
        let mut lateral_fraction = 0.0;
        let mut absolute_fraction = 0.0;
        for region in 0..3 {
            let contribution = REGION_GAIN * roles[3 * i + region]
                * values[2 * region + side_index];
            absolute_fraction += contribution.abs();
            // Positive temple/jaw expand; positive cheekbone narrows.
            lateral_fraction += if region == 1 { -contribution } else { contribution };
        }
        // Refuse before publishing; opposing requests cannot conceal an
        // over-budget absolute regional sum. Never clamp or reduce the gain.
        if !absolute_fraction.is_finite() || absolute_fraction > MAX_DISPLACEMENT {
            return Err(BOUND_ERROR);
        }
        if lateral_fraction == 0.0 {
            // Preserve exact positive zero for neutral and zero-role anchors.
            continue;
        }
        let lateral = sides[i] * lateral_fraction * frame[6];
        let dx = lateral * frame[0];
        let dy = lateral * frame[1];
        if !dx.is_finite() || !dy.is_finite()
            || dx.hypot(dy) > MAX_DISPLACEMENT * frame[6]
        {
            return Err(BOUND_ERROR);
        }
        scratch[2 * i] = dx;
        scratch[2 * i + 1] = dy;
    }
    Ok(())
}

#[no_mangle]
pub extern "C" fn lrt_face_contour_abi() -> u32 { 1 }

/// Private ABI 1. All lengths count f64 elements, never bytes.
/// points[N,2], roles[N,3]=(temple,cheekbone,jaw), sides[N]=+1/-1;
/// frame=[right_x,right_y,up_x,up_y,center_x,center_y,width];
/// values=[temple_left,temple_right,cheekbone_left,cheekbone_right,jaw_left,jaw_right].
/// output[N,2] is a FORWARD source-control displacement, not a pullback field.
/// The host separately fits its existing normalized TPS and samples RGB once.
/// On a nonzero status output is untouched. On success every output is finite.
/// # Safety
/// Caller supplies live aligned allocations of the declared lengths and keeps
/// every input immutable throughout this call. Output must be exclusively
/// writable and overlap no input. Read-only inputs may overlap each other.
/// Address checks cannot establish actual allocation bounds, lifetime, anatomy
/// or provenance. Dangling/inaccessible pointers remain caller violations.
/// Panic containment does not protect against foreign faults or process abort.
#[no_mangle]
pub unsafe extern "C" fn lrt_face_contour_controls_v1(
    points: *const f64, points_len: usize, roles: *const f64, roles_len: usize,
    sides: *const f64, sides_len: usize, frame: *const f64, frame_len: usize,
    values: *const f64, values_len: usize, count: usize,
    output: *mut f64, output_len: usize,
) -> i32 {
    let result = panic::catch_unwind(|| -> Result<(), i32> {
        if count == 0 || count > MAX_CONTROLS { return Err(ABI_ERROR); }
        let coordinates = count.checked_mul(2).ok_or(ABI_ERROR)?;
        let weights = count.checked_mul(3).ok_or(ABI_ERROR)?;
        if points_len != coordinates || roles_len != weights || sides_len != count
            || frame_len != 7 || values_len != 6 || output_len != coordinates
        {
            return Err(ABI_ERROR);
        }
        let output_span = span(output, output_len)?;
        for (pointer, length) in [
            (points, points_len), (roles, roles_len), (sides, sides_len),
            (frame, frame_len), (values, values_len),
        ] {
            if overlaps(span(pointer, length)?, output_span) { return Err(ABI_ERROR); }
        }
        // Length/pointer/alias checks precede slice construction; computation
        // precedes the single output copy. Fixed 4 KiB scratch, no heap work.
        let p = slice::from_raw_parts(points, points_len);
        let r = slice::from_raw_parts(roles, roles_len);
        let s = slice::from_raw_parts(sides, sides_len);
        let f = slice::from_raw_parts(frame, frame_len);
        let v = slice::from_raw_parts(values, values_len);
        let mut scratch = [0.0; MAX_CONTROLS * 2];
        evaluate(p, r, s, f, v, &mut scratch)?;
        slice::from_raw_parts_mut(output, output_len).copy_from_slice(&scratch[..output_len]);
        Ok(())
    });
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
