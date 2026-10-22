// SPDX-License-Identifier: GPL-3.0-or-later
//! Shared point evaluator for fitting AND production. An original, explicitly
//! late colour operator, not writes into noncommuting manual pipeline stages.
#[path = "../curves/curve.rs"]
pub mod curve;

pub const PARAMS: usize = 50;
pub const KNOTS: [f64; 5] = [0.0, 0.25, 0.5, 0.75, 1.0];
pub const CENTRES: [f64; 8] = [0.0, 30.0, 60.0, 120.0, 180.0, 240.0, 280.0, 320.0];

pub fn identity() -> [f64; PARAMS] {
    let mut p = [0.0; PARAMS];
    for c in 0..4 { p[6 + c * 5..11 + c * 5].copy_from_slice(&KNOTS); }
    p
}

pub fn validate(p: &[f64]) -> bool {
    if p.len() != PARAMS || p.iter().any(|v| !v.is_finite()) { return false; }
    p[..4].iter().all(|v| v.abs() <= 2.0)
        && p[4..6].iter().all(|v| v.abs() <= 100.0)
        && p[6..26].iter().all(|v| (0.0..=1.0).contains(v))
        && p[26..].iter().enumerate().all(|(i, v)| v.abs() <= if i % 3 == 0 { 60.0 } else { 100.0 })
}

pub struct Operator {
    p: [f64; PARAMS],
    curves: Vec<curve::Curve>,
    gains: [f64; 3],
    hsv_active: bool,
    neutral: bool,
}

impl Operator {
    pub fn new(values: &[f64], tone: f64, colour: f64) -> Result<Self, &'static str> {
        if !validate(values) || !tone.is_finite() || !colour.is_finite()
            || !(0.0..=2.0).contains(&tone) || !(0.0..=2.0).contains(&colour) {
            return Err("invalid recipe");
        }
        let mut p = identity();
        p[0] = values[0] * tone;
        for i in 1..4 { p[i] = values[i] * colour; }
        p[4] = values[4] * colour;
        p[5] = values[5] * tone;
        for c in 0..4 {
            for k in 0..5 {
                let strength = if c == 0 { tone } else { colour };
                p[6 + c * 5 + k] = (KNOTS[k] + (values[6 + c * 5 + k] - KNOTS[k]) * strength).clamp(0.0, 1.0);
            }
        }
        for i in 26..PARAMS { p[i] = values[i] * colour; }
        let curves = (0..4).map(|c| curve::compile(&(0..5).map(|k| curve::Point {
            x: KNOTS[k], y: p[6 + c * 5 + k],
        }).collect::<Vec<_>>())).collect::<Result<Vec<_>, _>>()?;
        // Compile constant gains once, rather than raising 2 to a power per
        // channel per pixel. A cancelled EV/gain sum has a true bypass too.
        let gains = [p[0] + p[1], p[0] + p[2], p[0] + p[3]].map(|v| 2.0f64.powf(v));
        let hsv_active = p[26..].iter().any(|v| *v != 0.0);
        let neutral = gains.iter().all(|v| *v == 1.0) && p[4] == 0.0 && p[5] == 0.0
            && curves.iter().all(|c| c.identity) && !hsv_active;
        Ok(Self { p, curves, gains, hsv_active, neutral })
    }

    pub fn is_neutral(&self) -> bool { self.neutral }

    /// The shared production float32 endpoint, also used by the fitter. This
    /// includes the overall/mask residual blend and its rounding boundary.
    pub fn render(&self, rgb: [f32; 3], amount: f64) -> Result<[f32; 3], ()> {
        if self.neutral || amount == 0.0 { return Ok(rgb); }
        let value = rgb.map(|v| v as f64);
        if value.iter().any(|v| !v.is_finite()) || !amount.is_finite() { return Err(()); }
        let changed = self.apply(value);
        let mut out = rgb;
        for c in 0..3 {
            let output = value[c] + (changed[c] - value[c]) * amount;
            if !output.is_finite() || output.abs() > f32::MAX as f64 { return Err(()); }
            out[c] = output as f32;
        }
        Ok(out)
    }

    pub fn apply(&self, rgb: [f64; 3]) -> [f64; 3] {
        if self.neutral { return rgb; }
        let mut out = rgb;
        for c in 0..3 {
            if self.gains[c] != 1.0 {
                out[c] = curve::srgb_encode(curve::srgb_decode(out[c]) * self.gains[c]);
            }
        }
        // Extended-float contrast and encoded-luma saturation deliberately do
        // not inherit legacy tone.py's SDR clipping. This stage is versioned.
        if self.p[5] != 0.0 {
            for v in &mut out { *v = (*v - 0.5) * (1.0 + self.p[5] / 100.0) + 0.5; }
        }
        if self.p[4] != 0.0 {
            let y = out[0] * 0.2126 + out[1] * 0.7152 + out[2] * 0.0722;
            for v in &mut out { *v = y + (*v - y) * (1.0 + self.p[4] / 100.0); }
        }
        for c in 0..3 { out[c] = self.curves[c + 1].evaluate(self.curves[0].evaluate(out[c])); }
        if self.hsv_active { out = hsv_bands(out, &self.p[26..]); }
        out
    }
}

// Legacy SDR HSV-band semantics, not HDR HSL. Identity bypass retains negative,
// HDR and signed-zero bits. This generic operator has no orange/skin gate;
// low-chroma protection here is the legacy HSV saturation gate, not a skin mask.
pub fn hsv_bands(rgb: [f64; 3], p: &[f64]) -> [f64; 3] {
    let base = rgb.map(|v| v.clamp(0.0, 1.0));
    let max = base.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let min = base.iter().copied().fold(f64::INFINITY, f64::min);
    let difference = max - min;
    let saturation = if max > 0.0 { difference / max } else { 0.0 };
    if saturation == 0.0 { return base; }
    let hue = (if max == base[0] { (base[1] - base[2]) / difference }
        else if max == base[1] { (base[2] - base[0]) / difference + 2.0 }
        else { (base[0] - base[1]) / difference + 4.0 }).rem_euclid(6.0) / 6.0;
    let mut adjustments = [0.0; 3];
    for (i, centre) in CENTRES.iter().enumerate() {
        let delta = (hue * 360.0 - centre).abs();
        let t = (1.0 - delta.min(360.0 - delta) / 45.0).clamp(0.0, 1.0);
        let weight = t * t * (3.0 - 2.0 * t) * (saturation / 0.06).clamp(0.0, 1.0);
        for c in 0..3 { adjustments[c] += weight * p[i * 3 + c]; }
    }
    let hue = (hue + adjustments[0].clamp(-60.0, 60.0) / 360.0).rem_euclid(1.0);
    let saturation = (saturation * (1.0 + adjustments[1].clamp(-100.0, 100.0) / 100.0)).clamp(0.0, 1.0);
    let value = (max * (1.0 + adjustments[2].clamp(-100.0, 100.0) / 100.0)).clamp(0.0, 1.0);
    let i = (hue * 6.0).floor() as usize;
    let f = hue * 6.0 - i as f64;
    let (p, q, t) = (value * (1.0 - saturation), value * (1.0 - saturation * f), value * (1.0 - saturation * (1.0 - f)));
    match i % 6 {
        0 => [value, t, p], 1 => [q, value, p], 2 => [p, value, t],
        3 => [p, q, value], 4 => [t, p, value], _ => [value, p, q],
    }
}

pub fn lab(rgb: [f64; 3]) -> [f64; 3] {
    let [r, g, b] = rgb.map(curve::srgb_decode);
    let l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b).cbrt();
    let m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b).cbrt();
    let s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b).cbrt();
    [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
     1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
     0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s]
}

pub fn distance(a: [f64; 3], b: [f64; 3]) -> f64 {
    (0..3).map(|i| (a[i] - b[i]).powi(2)).sum()
}
