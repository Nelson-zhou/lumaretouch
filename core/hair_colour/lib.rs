// SPDX-License-Identifier: GPL-3.0-or-later
// Original, dependency-free hair colour and measured-highlight operator.
// Palette values and effect coefficients below are original project choices,
// not values or an implementation recovered from a commercial product.

use std::mem::{align_of, size_of};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::slice;

const MAX_PIXELS: usize = 64_000_000;
const STYLE_COUNT: usize = 13;
const INVALID_ARGUMENT: i32 = 1;
const INVALID_RESULT: i32 = 3;
const ALLOCATION_FAILURE: i32 = 4;

// Original encoded-sRGB colour intents. Only their chromaticity is used;
// these are not replacement pixel values and do not prescribe lightness.
const ORIGINAL_PALETTE: [[f64; 3]; STYLE_COUNT] = [
    [0.52, 0.31, 0.16], // 0 蜜茶棕
    [0.40, 0.22, 0.13], // 1 栗棕
    [0.80, 0.27, 0.08], // 2 落日橘
    [0.31, 0.28, 0.22], // 3 冷茶棕
    [0.42, 0.40, 0.27], // 4 苦亚麻
    [0.075, 0.072, 0.068], // 5 自然黑
    [0.47, 0.18, 0.37], // 6 玫瑰紫
    [0.10, 0.14, 0.24], // 7 蓝黑
    [0.31, 0.20, 0.56], // 8 鸢尾蓝紫
    [0.55, 0.26, 0.34], // 9 树莓粉棕
    [0.65, 0.14, 0.10], // 10 枫叶红
    [0.29, 0.36, 0.20], // 11 苔绿
    [0.65, 0.46, 0.59], // 12 薄藤粉
];

#[no_mangle]
pub extern "C" fn lrt_hair_colour_abi() -> u32 {
    1
}

fn decode(value: f64) -> f64 {
    if value <= 0.04045 {
        value / 12.92
    } else {
        ((value + 0.055) / 1.055).powf(2.4)
    }
}

fn encode(value: f64) -> f64 {
    if value <= 0.0031308 {
        12.92 * value
    } else {
        1.055 * value.powf(1.0 / 2.4) - 0.055
    }
}

fn luma(rgb: [f64; 3]) -> f64 {
    0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
}

fn smoothstep(lo: f64, hi: f64, value: f64) -> f64 {
    let t = ((value - lo) / (hi - lo)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

fn clip_guard(y: f64) -> f64 {
    smoothstep(0.001, 0.012, y) * (1.0 - smoothstep(0.90, 0.995, y))
}

// Contract chroma toward the neutral axis at the SAME linear luminance.
// Independent per-channel clipping would change hue and luminance instead.
fn contract_gamut(y: f64, chroma: [f64; 3]) -> [f64; 3] {
    let mut scale = 1.0f64;
    for c in chroma {
        if c > 0.0 {
            scale = scale.min((1.0 - y) / c);
        } else if c < 0.0 {
            scale = scale.min(-y / c);
        }
    }
    scale = scale.clamp(0.0, 1.0);
    // Clamp only the floating-point boundary residue after contraction.
    chroma.map(|c| (y + scale * c).clamp(0.0, 1.0))
}

fn zeros<T: Copy + Default>(len: usize) -> Result<Vec<T>, i32> {
    let mut result = Vec::new();
    result.try_reserve_exact(len).map_err(|_| ALLOCATION_FAILURE)?;
    result.resize(len, T::default());
    Ok(result)
}

#[derive(Clone, Copy)]
struct Span {
    start: usize,
    end: usize,
}

fn checked_span(pointer: *const f32, len: usize) -> Result<Span, i32> {
    let start = pointer as usize;
    let bytes = len.checked_mul(size_of::<f32>()).ok_or(INVALID_ARGUMENT)?;
    if pointer.is_null() || start % align_of::<f32>() != 0 || bytes > isize::MAX as usize {
        return Err(INVALID_ARGUMENT);
    }
    let end = start.checked_add(bytes).ok_or(INVALID_ARGUMENT)?;
    Ok(Span { start, end })
}

fn overlaps(a: Span, b: Span) -> bool {
    a.start < b.end && b.start < a.end
}

// O(N) masked separable box mean; all sums use f64. The caller provides one
// full-source scratch buffer, reused for local and broad passes. There is no
// tile/global image mean, and zero-support background never enters a sum.
fn masked_mean(
    luminance: &[f32],
    support: &[f32],
    width: usize,
    height: usize,
    radius: usize,
    scratch: &mut [[f64; 2]],
    result: &mut [f32],
) {
    for row in 0..height {
        let base = row * width;
        let mut sum = 0.0f64;
        let mut weight = 0.0f64;
        for x in 0..=radius.min(width - 1) {
            let w = support[base + x] as f64;
            sum += luminance[base + x] as f64 * w;
            weight += w;
        }
        for x in 0..width {
            scratch[base + x] = [sum, weight];
            if x >= radius {
                let old = base + x - radius;
                let w = support[old] as f64;
                sum -= luminance[old] as f64 * w;
                weight -= w;
            }
            let next = x + radius + 1;
            if next < width {
                let w = support[base + next] as f64;
                sum += luminance[base + next] as f64 * w;
                weight += w;
            }
        }
    }
    for x in 0..width {
        let mut sum = 0.0f64;
        let mut weight = 0.0f64;
        for row in 0..=radius.min(height - 1) {
            sum += scratch[row * width + x][0];
            weight += scratch[row * width + x][1];
        }
        for row in 0..height {
            let i = row * width + x;
            // Insignificant effective support is not enough to infer a local
            // highlight. Falling back to source makes positive contrast zero.
            result[i] = if weight > 1.0e-12 {
                (sum / weight).clamp(0.0, 1.0) as f32
            } else {
                luminance[i]
            };
            if row >= radius {
                let old = (row - radius) * width + x;
                sum -= scratch[old][0];
                weight -= scratch[old][1];
            }
            let next = row + radius + 1;
            if next < height {
                sum += scratch[next * width + x][0];
                weight += scratch[next * width + x][1];
            }
        }
    }
}

fn measured_highlights(
    rgb: &[f32],
    support: &[f32],
    width: usize,
    height: usize,
    evidence: &mut [f32],
) -> Result<(), i32> {
    let n = support.len();
    let mut luminance = zeros::<f32>(n)?;
    for (i, pixel) in rgb.chunks_exact(3).enumerate() {
        luminance[i] = luma([
            decode(pixel[0] as f64), decode(pixel[1] as f64), decode(pixel[2] as f64),
        ]) as f32;
    }
    let mut means = zeros::<f32>(n)?;
    let mut scratch = zeros::<[f64; 2]>(n)?;
    let short_side = width.min(height) as f64;
    let local_radius = (short_side * 0.0025).round().clamp(1.0, 12.0) as usize;
    let broad_radius = (short_side * 0.018).round().clamp(3.0, 96.0) as usize;

    masked_mean(&luminance, support, width, height, local_radius, &mut scratch, &mut means);
    for i in 0..n {
        if support[i] != 0.0 {
            let local_contrast = luminance[i] as f64 - means[i] as f64;
            evidence[i] = smoothstep(0.0015, 0.045, local_contrast) as f32;
        }
    }
    masked_mean(&luminance, support, width, height, broad_radius, &mut scratch, &mut means);
    for i in 0..n {
        let y = luminance[i] as f64;
        let mean = means[i] as f64;
        let measured = evidence[i] as f64
            * smoothstep(0.003, 0.12, y - mean)
            * smoothstep(1.08, 1.75, y / (mean + 0.01))
            * smoothstep(0.035, 0.28, y)
            * clip_guard(y);
        if !measured.is_finite() || !(0.0..=1.0).contains(&measured) {
            return Err(INVALID_RESULT);
        }
        evidence[i] = measured as f32;
    }
    Ok(())
}

fn prepare(
    rgb: &[f32],
    support: &[f32],
    width: usize,
    height: usize,
    style: usize,
    strength: f64,
    gloss: f64,
) -> Result<(Vec<f32>, Vec<f32>), i32> {
    // Check every sample even for neutral controls or zero support. No invalid
    // input is hidden by a bypass; no output has been touched at this point.
    if rgb.iter().chain(support.iter()).any(|v| !v.is_finite() || !(0.0..=1.0).contains(v)) {
        return Err(INVALID_ARGUMENT);
    }
    let n = support.len();
    let mut delta = zeros::<f32>(rgb.len())?;
    let mut highlights = zeros::<f32>(n)?;
    if support.iter().all(|v| *v == 0.0) {
        return Ok((delta, highlights));
    }
    // The diagnostic is amount/style independent, including when gloss is 0.
    measured_highlights(rgb, support, width, height, &mut highlights)?;
    let palette = ORIGINAL_PALETTE[style].map(decode);
    let palette_y = luma(palette);
    let palette_chroma = palette.map(|c| c / palette_y - 1.0);
    for i in 0..n {
        let m = support[i] as f64;
        let evidence = highlights[i] as f64;
        highlights[i] = (m * evidence) as f32;
        if m == 0.0 || (strength == 0.0 && gloss == 0.0) {
            continue;
        }
        let base = i * 3;
        let source = [
            decode(rgb[base] as f64),
            decode(rgb[base + 1] as f64),
            decode(rgb[base + 2] as f64),
        ];
        let y = luma(source);
        let tint = 0.82 * strength * clip_guard(y);
        // Natural black is the sole palette allowed to lower luminance. This
        // point mapping is monotone, never lifts blacks and protects clipping.
        let target_y = if style == 5 {
            y - 0.40 * strength * (y - 0.001).max(0.0)
                * (1.0 - smoothstep(0.92, 0.995, y))
        } else {
            y
        };
        let gloss_gain = 0.16 * gloss * evidence;
        if tint == 0.0 && target_y == y && gloss_gain == 0.0 {
            continue;
        }
        let luminance_scale = if y > 0.0 { target_y / y } else { 0.0 };
        let mut chroma = [0.0; 3];
        for c in 0..3 {
            chroma[c] = (1.0 - tint) * (source[c] - y) * luminance_scale
                + tint * target_y * palette_chroma[c];
        }
        let mut proposed = contract_gamut(target_y, chroma);
        for c in 0..3 {
            // Only measured pre-existing highlights can move toward white.
            // No filtering, smoothing or synthetic texture is applied to RGB.
            proposed[c] += gloss_gain * (1.0 - proposed[c]);
            let mixed = source[c] + m * (proposed[c] - source[c]);
            let encoded = encode(mixed.clamp(0.0, 1.0)).clamp(0.0, 1.0);
            let change = (encoded as f32 - rgb[base + c])
                .clamp(-rgb[base + c], 1.0 - rgb[base + c]);
            let reconstructed = rgb[base + c] + change;
            if !encoded.is_finite() || !change.is_finite()
                || !(0.0..=1.0).contains(&reconstructed)
            {
                return Err(INVALID_RESULT);
            }
            delta[base + c] = change;
        }
    }
    Ok((delta, highlights))
}

/// Apply once to the complete immutable source, not independently to tiles.
///
/// RGB is encoded sRGB f32 [0,1], interleaved RGB. Support is an explicitly
/// supplied N-element, source-aligned hair/person intersection in [0,1]. The
/// outputs are 3*N encoded-RGB additive deltas and N measured highlight weights.
/// See README.md for status codes and the precise colour/highlight contract.
///
/// # Safety
/// Every pointer must address a live, appropriately aligned allocation with
/// at least the documented capacity for the duration of this call. Output
/// spans must not overlap inputs or each other. The ABI checks nulls, numeric
/// spans/alignment and overlap, but cannot establish arbitrary pointer validity,
/// actual allocation size, mask semantics or freedom from concurrent mutation.
#[no_mangle]
pub unsafe extern "C" fn lrt_hair_colour_apply(
    rgb: *const f32,
    support: *const f32,
    width: usize,
    height: usize,
    style: u32,
    strength: f32,
    gloss: f32,
    delta: *mut f32,
    highlights: *mut f32,
) -> i32 {
    catch_unwind(AssertUnwindSafe(|| -> i32 {
        let checked = || -> Result<(usize, usize), i32> {
            let n = width.checked_mul(height).ok_or(INVALID_ARGUMENT)?;
            if width == 0 || height == 0 || n > MAX_PIXELS || style as usize >= STYLE_COUNT
                || [strength, gloss].iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
            {
                return Err(INVALID_ARGUMENT);
            }
            let rgb_len = n.checked_mul(3).ok_or(INVALID_ARGUMENT)?;
            let rgb_span = checked_span(rgb, rgb_len)?;
            let support_span = checked_span(support, n)?;
            let delta_span = checked_span(delta as *const f32, rgb_len)?;
            let highlight_span = checked_span(highlights as *const f32, n)?;
            if overlaps(delta_span, rgb_span) || overlaps(delta_span, support_span)
                || overlaps(highlight_span, rgb_span) || overlaps(highlight_span, support_span)
                || overlaps(delta_span, highlight_span)
            {
                return Err(INVALID_ARGUMENT);
            }
            Ok((n, rgb_len))
        };
        let (n, rgb_len) = match checked() {
            Ok(shape) => shape,
            Err(status) => return status,
        };
        let source = slice::from_raw_parts(rgb, rgb_len);
        let weights = slice::from_raw_parts(support, n);
        let (prepared_delta, prepared_highlights) = match prepare(
            source, weights, width, height, style as usize, strength as f64, gloss as f64,
        ) {
            Ok(prepared) => prepared,
            Err(status) => return status,
        };
        // Nothing fallible, allocating or computational remains after the first
        // commit. All recoverable errors leave BOTH caller outputs untouched.
        std::ptr::copy_nonoverlapping(prepared_delta.as_ptr(), delta, rgb_len);
        std::ptr::copy_nonoverlapping(prepared_highlights.as_ptr(), highlights, n);
        0
    })).unwrap_or(99)
}

// Source-only fixtures. These have NOT been compiled or run as part of this
// implementation; local execution/photographic acceptance belongs to Qoder.
#[cfg(test)]
mod tests {
    use super::*;

    fn apply(rgb: &[f32], support: &[f32], width: usize, height: usize,
             style: u32, strength: f32, gloss: f32) -> (i32, Vec<f32>, Vec<f32>) {
        let mut delta = vec![17.0; rgb.len()];
        let mut highlights = vec![19.0; support.len()];
        let status = unsafe {
            lrt_hair_colour_apply(rgb.as_ptr(), support.as_ptr(), width, height,
                                  style, strength, gloss, delta.as_mut_ptr(), highlights.as_mut_ptr())
        };
        (status, delta, highlights)
    }

    fn linear_luma(pixel: &[f32]) -> f64 {
        luma([decode(pixel[0] as f64), decode(pixel[1] as f64), decode(pixel[2] as f64)])
    }

    #[test]
    fn neutral_and_zero_mask_have_exact_zero_delta() {
        let source = [0.0, 0.1, 0.2, 0.3, 0.5, 1.0];
        let (status, delta, _) = apply(&source, &[1.0, 1.0], 2, 1, 0, 0.0, 0.0);
        assert_eq!(status, 0);
        assert!(delta.iter().all(|v| v.to_bits() == 0.0f32.to_bits()));
        let (status, delta, highlights) = apply(&source, &[0.0, 0.0], 2, 1, 12, 1.0, 1.0);
        assert_eq!(status, 0);
        assert_eq!(delta, vec![0.0; source.len()]);
        assert_eq!(highlights, vec![0.0; 2]);
    }

    #[test]
    fn flat_supported_hair_has_no_gloss_even_at_mask_edges() {
        let source = vec![0.45; 9 * 7 * 3];
        let support: Vec<f32> = (0..63).map(|i| if i % 5 == 0 { 0.0 } else { 0.4 }).collect();
        let (status, delta, highlights) = apply(&source, &support, 9, 7, 0, 0.0, 1.0);
        assert_eq!(status, 0);
        assert!(delta.iter().all(|v| *v == 0.0));
        assert!(highlights.iter().all(|v| *v == 0.0));
    }

    #[test]
    fn gloss_follows_existing_highlights_not_background_or_dark_regions() {
        let width = 9;
        let mut source = vec![0.20; width * width * 3];
        let mut support = vec![1.0; width * width];
        let centre = 4 * width + 4;
        source[centre * 3..centre * 3 + 3].fill(0.72);
        support[0] = 0.0;
        source[0..3].fill(1.0);
        let (status, delta, highlights) = apply(&source, &support, width, width, 3, 0.0, 1.0);
        assert_eq!(status, 0);
        assert!(highlights[centre] > 0.0 && delta[centre * 3] > 0.0);
        assert_eq!(highlights[0], 0.0);
        assert_eq!(&delta[0..3], &[0.0; 3]);
        assert_eq!(highlights[centre + 1], 0.0);
        assert_eq!(&delta[(centre + 1) * 3..(centre + 2) * 3], &[0.0; 3]);
        let (_, _, no_gloss_diagnostic) = apply(&source, &support, width, width, 12, 0.8, 0.0);
        assert_eq!(highlights, no_gloss_diagnostic);
    }

    #[test]
    fn background_cannot_change_supported_measurements() {
        let mut source = vec![0.25; 7 * 7 * 3];
        let mut support = vec![0.0; 7 * 7];
        for row in 2..5 {
            for x in 2..5 { support[row * 7 + x] = 1.0; }
        }
        source[(3 * 7 + 3) * 3..(3 * 7 + 3) * 3 + 3].fill(0.7);
        let (_, before, evidence) = apply(&source, &support, 7, 7, 8, 0.5, 1.0);
        for i in 0..49 {
            if support[i] == 0.0 { source[i * 3..i * 3 + 3].fill(1.0); }
        }
        let (status, after, next_evidence) = apply(&source, &support, 7, 7, 8, 0.5, 1.0);
        assert_eq!(status, 0);
        assert_eq!(before, after);
        assert_eq!(evidence, next_evidence);
    }

    #[test]
    fn all_thirteen_styles_are_bounded_and_nonblack_preserves_luminance() {
        let source = [0.40, 0.31, 0.22, 0.16, 0.23, 0.32];
        for style in 0..13 {
            let (status, delta, highlights) = apply(&source, &[1.0, 0.35], 2, 1, style, 1.0, 0.0);
            assert_eq!(status, 0);
            assert!(highlights.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)));
            let result: Vec<f32> = source.iter().zip(delta).map(|(v, d)| v + d).collect();
            assert!(result.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)));
            assert!(source.iter().zip(&result).any(|(a, b)| a != b));
            for i in 0..2 {
                let before = linear_luma(&source[i * 3..i * 3 + 3]);
                let after = linear_luma(&result[i * 3..i * 3 + 3]);
                if style == 5 { assert!(after < before); }
                else { assert!((after - before).abs() < 2.0e-7); }
            }
        }
    }

    #[test]
    fn natural_black_luminance_mapping_is_monotone_and_never_lifts() {
        let mut source = Vec::new();
        for i in 0..257 { source.extend_from_slice(&[i as f32 / 256.0; 3]); }
        let (status, delta, _) = apply(&source, &vec![1.0; 257], 257, 1, 5, 1.0, 0.0);
        assert_eq!(status, 0);
        let result: Vec<f32> = source.iter().zip(delta).map(|(v, d)| v + d).collect();
        let mut previous = -1.0;
        for i in 0..257 {
            let before = linear_luma(&source[i * 3..i * 3 + 3]);
            let after = linear_luma(&result[i * 3..i * 3 + 3]);
            assert!(after + 2.0e-7 >= previous && after <= before + 2.0e-7);
            previous = after;
        }
    }

    #[test]
    fn fully_clipped_dark_and_light_have_no_synthetic_detail_or_gloss() {
        let source = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0];
        for style in 0..13 {
            let (status, delta, highlights) = apply(&source, &[1.0; 2], 2, 1, style, 1.0, 1.0);
            assert_eq!(status, 0);
            assert_eq!(delta, vec![0.0; 6]);
            assert_eq!(highlights, vec![0.0; 2]);
        }
    }

    #[test]
    fn invalid_samples_and_controls_leave_both_outputs_atomic() {
        for bad in [f32::NAN, f32::INFINITY, -0.01, 1.01] {
            let (status, delta, highlights) = apply(&[0.2, 0.3, bad], &[0.0], 1, 1, 0, 0.0, 0.0);
            assert_eq!(status, INVALID_ARGUMENT);
            assert_eq!(delta, vec![17.0; 3]);
            assert_eq!(highlights, vec![19.0]);
            let (status, delta, highlights) = apply(&[0.2; 3], &[bad], 1, 1, 0, 1.0, 1.0);
            assert_eq!(status, INVALID_ARGUMENT);
            assert_eq!(delta, vec![17.0; 3]);
            assert_eq!(highlights, vec![19.0]);
        }
        for (style, strength, gloss) in [(13, 1.0, 1.0), (0, f32::NAN, 0.0), (0, 0.0, 1.1)] {
            let (status, delta, highlights) = apply(&[0.2; 3], &[1.0], 1, 1, style, strength, gloss);
            assert_eq!(status, INVALID_ARGUMENT);
            assert_eq!(delta, vec![17.0; 3]);
            assert_eq!(highlights, vec![19.0]);
        }
    }

    #[test]
    fn missing_support_and_invalid_geometry_are_not_unmasked_fallbacks() {
        let source = [0.3; 3];
        let support = [1.0];
        let mut delta = [17.0; 3];
        let mut highlights = [19.0];
        for (mask, width, height) in [
            (std::ptr::null(), 1usize, 1usize),
            (support.as_ptr(), 0, 1),
            (support.as_ptr(), usize::MAX, 2),
            (support.as_ptr(), MAX_PIXELS + 1, 1),
        ] {
            let status = unsafe { lrt_hair_colour_apply(source.as_ptr(), mask, width, height, 0,
                1.0, 1.0, delta.as_mut_ptr(), highlights.as_mut_ptr()) };
            assert_eq!(status, INVALID_ARGUMENT);
            assert_eq!(delta, [17.0; 3]);
            assert_eq!(highlights, [19.0]);
        }
    }

    #[test]
    fn overlapping_outputs_are_rejected_before_dereference_or_write() {
        let source = [0.3; 3];
        let support = [1.0];
        let mut out = [17.0; 4];
        let status = unsafe { lrt_hair_colour_apply(source.as_ptr(), support.as_ptr(), 1, 1, 0,
            1.0, 1.0, out.as_mut_ptr(), out.as_mut_ptr().add(1)) };
        assert_eq!(status, INVALID_ARGUMENT);
        assert_eq!(out, [17.0; 4]);
    }
}
