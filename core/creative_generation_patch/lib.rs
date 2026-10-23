// SPDX-License-Identifier: GPL-3.0-or-later
//! Original numerical boundary for actual externally generated pixels. ABI 1.
//! No model, inference, placeholder candidate, resizing or automatic detection.
//! Authored fixtures UNRUN. See README.md for caller ownership requirements.
use std::{mem, slice};

pub const SIDE: usize = 768;
pub const PIXELS: usize = SIDE * SIDE;
pub const MAX_SOURCE_PIXELS: usize = 32_000_000;
const MAX_DIMENSION: usize = 65_536;
const MAX_BYTES: usize = 1_073_741_824;
const POLL: usize = 4096;
const ABI: i32 = 1;
const PIXEL: i32 = 2;
const CANCELLED: i32 = 3;
const RESOURCE: i32 = 4;
const EMPTY: i32 = 5;
type Cancel = Option<extern "C" fn() -> i32>;
type Span = (usize, usize);

fn poll(cancel: Cancel) -> Result<(), i32> {
    if cancel.map_or(false, |f| f() != 0) { Err(CANCELLED) } else { Ok(()) }
}
fn unit(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn encode(v: f32) -> f32 {
    let v = v as f64;
    (if v <= 0.0031308 { 12.92 * v } else { 1.055 * v.powf(1.0 / 2.4) - 0.055 }) as f32
}
fn decode(v: f32) -> f32 {
    let v = v as f64;
    (if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }) as f32
}
// This checks arithmetic/alignment, NOT allocation validity. See Safety below.
fn span(p: *const f32, n: usize) -> Result<Span, i32> {
    let a = p as usize;
    let bytes = n.checked_mul(mem::size_of::<f32>()).ok_or(ABI)?;
    if p.is_null() || a % mem::align_of::<f32>() != 0 || bytes > isize::MAX as usize {
        return Err(ABI);
    }
    Ok((a, a.checked_add(bytes).ok_or(ABI)?))
}
fn disjoint(inputs: &[Span], outputs: &[Span]) -> Result<(), i32> {
    let overlaps = |a: Span, b: Span| a.0 < b.1 && b.0 < a.1;
    for (i, &out) in outputs.iter().enumerate() {
        if inputs.iter().any(|&input| overlaps(input, out))
            || outputs[..i].iter().any(|&other| overlaps(other, out)) { return Err(ABI); }
    }
    Ok(())
}
fn roi(w: usize, h: usize, x: usize, y: usize, rw: usize, rh: usize) -> Result<usize, i32> {
    if w == 0 || h == 0 || w > MAX_DIMENSION || h > MAX_DIMENSION
        || rw == 0 || rh == 0 || rw > SIDE || rh > SIDE
        || x.checked_add(rw).ok_or(ABI)? > w || y.checked_add(rh).ok_or(ABI)? > h {
        return Err(ABI);
    }
    let n = w.checked_mul(h).ok_or(RESOURCE)?;
    let bytes = n.checked_mul(6).and_then(|v| v.checked_add(5 * PIXELS))
        .and_then(|v| v.checked_mul(4)).ok_or(RESOURCE)?;
    if n > MAX_SOURCE_PIXELS || bytes > MAX_BYTES { return Err(RESOURCE); }
    Ok(n)
}

#[no_mangle]
pub extern "C" fn lrt_creative_generation_patch_abi() -> u32 { 1 }

/// Prepare contiguous HWC RGB and single-channel masks; all lengths are f32 counts.
/// # Safety
/// Caller owns accessible, aligned extents for the call; inputs remain immutable,
/// outputs are exclusively writable, callback never unwinds/reenters/mutates them.
/// On ANY nonzero return discard ALL outputs, even if partially written.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_generation_prepare_v1(
    source: *const f32, source_len: usize, width: usize, height: usize,
    selection: *const f32, selection_len: usize, protection: *const f32, protection_len: usize,
    x: usize, y: usize, roi_width: usize, roi_height: usize,
    rgb: *mut f32, rgb_len: usize, mask: *mut f32, mask_len: usize,
    eligible: *mut f32, eligible_len: usize, cancel: Cancel,
) -> i32 {
    let result = (|| -> Result<(), i32> {
        poll(cancel)?;
        let n = roi(width, height, x, y, roi_width, roi_height)?;
        if source_len != n * 4 || selection_len != n || protection_len != n
            || rgb_len != PIXELS * 3 || mask_len != PIXELS || eligible_len != PIXELS { return Err(ABI); }
        disjoint(&[span(source, source_len)?, span(selection, n)?, span(protection, n)?],
                 &[span(rgb, rgb_len)?, span(mask, mask_len)?, span(eligible, eligible_len)?])?;
        let src = slice::from_raw_parts(source, source_len);
        let sel = slice::from_raw_parts(selection, n);
        let protect = slice::from_raw_parts(protection, n);
        // Reject unsupported data even outside the ROI; no implicit HDR/alpha clipping.
        for i in 0..n {
            if i % POLL == 0 { poll(cancel)?; }
            if src[4*i+3] != 1.0 || !src[4*i..4*i+3].iter().copied().all(unit)
                || !unit(sel[i]) || !unit(protect[i]) { return Err(PIXEL); }
            // An explicit context crop must not silently discard selected edits.
            let px = i % width;
            let py = i / width;
            if sel[i] > 0.0 && protect[i] == 0.0
                && (px < x || px >= x + roi_width || py < y || py >= y + roi_height) {
                return Err(PIXEL);
            }
        }
        let out = slice::from_raw_parts_mut(rgb, rgb_len);
        let binary = slice::from_raw_parts_mut(mask, mask_len);
        let coverage = slice::from_raw_parts_mut(eligible, eligible_len);
        let mut any = false;
        for py in 0..SIDE {
            poll(cancel)?;
            for px in 0..SIDE {
                let i = py * SIDE + px;
                let s = (y + py.min(roi_height - 1)) * width + x + px.min(roi_width - 1);
                for c in 0..3 { out[3*i+c] = encode(src[4*s+c]); }
                let e = if px < roi_width && py < roi_height && protect[s] == 0.0 { sel[s] } else { 0.0 };
                coverage[i] = if e > 0.0 { e } else { 0.0 };
                binary[i] = if e > 0.0 { any = true; 1.0 } else { 0.0 };
            }
        }
        poll(cancel)?;
        if !any { return Err(EMPTY); }
        Ok(())
    })();
    result.err().unwrap_or(0)
}

/// Convert actual model RGB into a separately compositable premultiplied patch.
/// `eligible` must be the immutable prepare result from this exact source/ROI/job.
/// `fusion` cannot exceed it; positive source protection consequently stays excluded.
/// # Safety
/// Same allocation, immutability, callback and failure-discard obligations as prepare.
/// The caller authenticates provenance; arbitrary caller-supplied eligibility is NOT proof.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_generation_fuse_v1(
    generated: *const f32, generated_len: usize,
    eligible: *const f32, eligible_len: usize, fusion: *const f32, fusion_len: usize,
    roi_width: usize, roi_height: usize, density: f32,
    rgba: *mut f32, rgba_len: usize, cancel: Cancel,
) -> i32 {
    let result = (|| -> Result<(), i32> {
        poll(cancel)?;
        if roi_width == 0 || roi_height == 0 || roi_width > SIDE || roi_height > SIDE
            || generated_len != PIXELS * 3 || eligible_len != PIXELS || fusion_len != PIXELS
            || rgba_len != PIXELS * 4 || !unit(density) { return Err(ABI); }
        disjoint(&[span(generated, generated_len)?, span(eligible, eligible_len)?, span(fusion, fusion_len)?],
                 &[span(rgba, rgba_len)?])?;
        let rgb = slice::from_raw_parts(generated, generated_len);
        let cap = slice::from_raw_parts(eligible, eligible_len);
        let edit = slice::from_raw_parts(fusion, fusion_len);
        // Validate before producing anything. A model value outside SDR is an error.
        for i in 0..PIXELS {
            if i % POLL == 0 { poll(cancel)?; }
            if !rgb[3*i..3*i+3].iter().copied().all(unit) || !unit(cap[i]) || !unit(edit[i])
                || edit[i] > cap[i] { return Err(PIXEL); }
            if (i % SIDE >= roi_width || i / SIDE >= roi_height) && (cap[i] != 0.0 || edit[i] != 0.0) {
                return Err(PIXEL);
            }
        }
        let out = slice::from_raw_parts_mut(rgba, rgba_len);
        for i in 0..PIXELS {
            if i % POLL == 0 { poll(cancel)?; }
            let a = edit[i] * density;
            if a == 0.0 { out[4*i..4*i+4].fill(0.0); }
            else {
                for c in 0..3 { out[4*i+c] = decode(rgb[3*i+c]) * a; }
                out[4*i+3] = a;
            }
        }
        poll(cancel)
    })();
    result.err().unwrap_or(0)
}

#[cfg(test)]
mod tests {
    // AUTHORED / UNRUN. These are not numerical or runtime acceptance evidence.
    use super::*;
    #[test]
    fn transfer_precision_and_endpoints() {
        assert_eq!(encode(0.0), 0.0); assert_eq!(decode(0.0), 0.0);
        assert_eq!(encode(1.0), 1.0); assert_eq!(decode(1.0), 1.0);
        assert!((decode(0.5) - 0.21404114).abs() < 1e-7);
        assert_ne!(encode(32768.0 / 65535.0), encode(32769.0 / 65535.0));
    }
    extern "C" fn stop() -> i32 { 1 }
    #[test]
    fn roi_bounds_and_cancellation() {
        assert_eq!(roi(10, 10, 9, 0, 2, 1), Err(ABI));
        assert_eq!(roi(10, 10, usize::MAX, 0, 1, 1), Err(ABI));
        assert_eq!(roi(10, 10, 0, 0, 0, 1), Err(ABI));
        assert_eq!(poll(Some(stop)), Err(CANCELLED));
        assert!(span(std::ptr::null(), 1).is_err());
        assert!(disjoint(&[(10, 20)], &[(12, 18)]).is_err());
    }
    #[test]
    fn source_refusals_and_empty_selection() {
        let mut rgb = vec![0.0; PIXELS*3]; let mut mask = vec![0.0; PIXELS];
        let mut cap = vec![0.0; PIXELS];
        let mut call = |source: &[f32; 4], selection: f32, protection: f32| unsafe {
            lrt_creative_generation_prepare_v1(source.as_ptr(), 4, 1, 1,
                [selection].as_ptr(), 1, [protection].as_ptr(), 1, 0, 0, 1, 1,
                rgb.as_mut_ptr(), rgb.len(), mask.as_mut_ptr(), mask.len(),
                cap.as_mut_ptr(), cap.len(), None)
        };
        assert_eq!(call(&[0.2, 0.3, 0.4, 0.99], 1.0, 0.0), PIXEL);
        assert_eq!(call(&[1.01, 0.3, 0.4, 1.0], 1.0, 0.0), PIXEL);
        assert_eq!(call(&[f32::NAN, 0.3, 0.4, 1.0], 1.0, 0.0), PIXEL);
        assert_eq!(call(&[0.2, 0.3, 0.4, 1.0], f32::INFINITY, 0.0), PIXEL);
        assert_eq!(call(&[0.2, 0.3, 0.4, 1.0], 0.0, 0.0), EMPTY);
        assert_eq!(call(&[0.2, 0.3, 0.4, 1.0], 1.0, f32::MIN_POSITIVE), EMPTY);
    }
    #[test]
    fn model_padding_and_nan_are_not_silently_clipped() {
        let mut rgb = vec![0.5; PIXELS*3]; let mut cap = vec![0.0; PIXELS];
        let mut out = vec![9.0; PIXELS*4];
        cap[0] = 1.0;
        rgb[3*PIXELS-1] = f32::NAN;
        assert_eq!(unsafe { lrt_creative_generation_fuse_v1(rgb.as_ptr(), rgb.len(), cap.as_ptr(), cap.len(),
            cap.as_ptr(), cap.len(), 1, 1, 1.0, out.as_mut_ptr(), out.len(), None) }, PIXEL);
        assert!(out.iter().all(|v| *v == 9.0));
        rgb[3*PIXELS-1] = 0.5; cap[1] = 0.1;
        assert_eq!(unsafe { lrt_creative_generation_fuse_v1(rgb.as_ptr(), rgb.len(), cap.as_ptr(), cap.len(),
            cap.as_ptr(), cap.len(), 1, 1, 1.0, out.as_mut_ptr(), out.len(), None) }, PIXEL);
    }
    #[test]
    fn protected_padding_and_neutral_fusion() {
        let source = [0.25, 0.5, 0.75, 1.0, 0.1, 0.2, 0.3, 1.0];
        let mut rgb = vec![0.0; PIXELS*3]; let mut mask = vec![0.0; PIXELS];
        let mut cap = vec![0.0; PIXELS]; let mut out = vec![9.0; PIXELS*4];
        let status = unsafe { lrt_creative_generation_prepare_v1(source.as_ptr(), 8, 2, 1,
            [0.5, 1.0].as_ptr(), 2, [0.0, 0.001].as_ptr(), 2, 0, 0, 2, 1,
            rgb.as_mut_ptr(), rgb.len(), mask.as_mut_ptr(), mask.len(), cap.as_mut_ptr(), cap.len(), None) };
        assert_eq!(status, 0); assert_eq!(cap[0], 0.5); assert_eq!(mask[0], 1.0);
        assert_eq!(cap[1], 0.0); assert_eq!(cap[SIDE], 0.0);
        assert_eq!(rgb[6], rgb[3]); // Edge padding, no resampling.
        let fuse = |density, out: &mut Vec<f32>| unsafe { lrt_creative_generation_fuse_v1(
            rgb.as_ptr(), rgb.len(), cap.as_ptr(), cap.len(), cap.as_ptr(), cap.len(), 2, 1,
            density, out.as_mut_ptr(), out.len(), None) };
        assert_eq!(fuse(0.0, &mut out), 0); assert!(out.iter().all(|v| v.to_bits() == 0));
        assert_eq!(fuse(1.0, &mut out), 0); assert_eq!(out[3], 0.5);
        assert!(out[4..].iter().all(|v| *v == 0.0));
        let mut expanded = cap.clone(); expanded[1] = 0.1;
        assert_eq!(unsafe { lrt_creative_generation_fuse_v1(rgb.as_ptr(), rgb.len(), cap.as_ptr(), cap.len(),
            expanded.as_ptr(), expanded.len(), 2, 1, 1.0, out.as_mut_ptr(), out.len(), None) }, PIXEL);
    }
}
