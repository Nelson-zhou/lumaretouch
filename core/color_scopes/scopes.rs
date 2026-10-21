//! Bounded colour analysis of opaque, display-encoded working-sRGB samples.
//! RGB bins use encoded values; Y bins use linear relative luminance.
//! Lab explicitly uses D65, matching the existing image-quality reference.

pub const BINS: usize = 256;
pub const MAX_SAMPLES: usize = 65_536;

#[derive(Debug)]
pub struct Histogram {
    pub bins: [u64; BINS],
    pub underflow: u64,
    pub overflow: u64,
}
impl Default for Histogram {
    fn default() -> Self { Self { bins: [0; BINS], underflow: 0, overflow: 0 } }
}
impl Histogram {
    fn add(&mut self, value: f64) {
        // Out-of-range values are not silently counted as endpoint occupancy.
        if value < 0.0 { self.underflow += 1; }
        else if value > 1.0 { self.overflow += 1; }
        else { self.bins[((value * BINS as f64) as usize).min(BINS - 1)] += 1; }
    }
}

pub struct Scopes {
    pub rgb: [Histogram; 3],
    pub linear_y: Histogram,
    pub samples: usize,
    pub finite_samples: usize,
    pub nonfinite_samples: usize,
    sum: [f64; 3],
}
impl Scopes {
    pub fn new() -> Self {
        Self { rgb: std::array::from_fn(|_| Histogram::default()),
            linear_y: Histogram::default(), samples: 0, finite_samples: 0,
            nonfinite_samples: 0, sum: [0.0; 3] }
    }
    pub fn add(&mut self, rgb: [f64; 3]) -> Result<(), &'static str> {
        if self.samples == MAX_SAMPLES { return Err("colour sample budget exceeded"); }
        self.samples += 1;
        if !rgb.iter().all(|x| x.is_finite()) {
            self.nonfinite_samples += 1;
            return Ok(());
        }
        let linear = rgb.map(srgb_to_linear);
        let y = 0.21263900587151036 * linear[0] + 0.7151686787677559 * linear[1] + 0.07219231536073371 * linear[2];
        // The wire uses f32, but reject wider callers whose TRC would overflow.
        if !y.is_finite() { self.nonfinite_samples += 1; return Ok(()); }
        self.finite_samples += 1;
        for i in 0..3 { self.rgb[i].add(rgb[i]); self.sum[i] += rgb[i]; }
        self.linear_y.add(y);
        Ok(())
    }
    /// Encoded-sRGB arithmetic mean. This is not a linear-light average.
    pub fn mean_rgb(&self) -> Option<[f64; 3]> {
        (self.finite_samples > 0).then(|| self.sum.map(|v| v / self.finite_samples as f64))
    }
}

pub fn srgb_to_linear(value: f64) -> f64 {
    let a = value.abs();
    if a <= 0.04045 { value / 12.92 }
    else { value.signum() * ((a + 0.055) / 1.055).powf(2.4) }
}

pub fn srgb_to_lab_d65(rgb: [f64; 3]) -> [f64; 3] {
    let c = rgb.map(srgb_to_linear);
    let xyz = [
        0.4124564*c[0] + 0.3575761*c[1] + 0.1804375*c[2],
        0.2126729*c[0] + 0.7151522*c[1] + 0.0721750*c[2],
        0.0193339*c[0] + 0.1191920*c[1] + 0.9503041*c[2],
    ];
    let white = [0.95047, 1.0, 1.08883];
    let f: [f64; 3] = std::array::from_fn(|i| {
        let t = xyz[i] / white[i];
        if t > 216.0/24389.0 { t.cbrt() } else { ((24389.0/27.0)*t + 16.0)/116.0 }
    });
    [116.0*f[1]-16.0, 500.0*(f[0]-f[1]), 200.0*(f[1]-f[2])]
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn endpoints_and_out_of_range_are_separate() {
        let mut s=Scopes::new();
        for v in [-0.1, 0.0, 0.5, 1.0, 1.1] { s.add([v;3]).unwrap(); }
        assert_eq!(s.rgb[0].underflow,1); assert_eq!(s.rgb[0].overflow,1);
        assert_eq!(s.rgb[0].bins[0],1); assert_eq!(s.rgb[0].bins[128],1);
        assert_eq!(s.rgb[0].bins[255],1); assert_eq!(s.rgb[0].bins.iter().sum::<u64>(),3);
    }
    #[test] fn nonfinite_rows_are_reported_not_painted_black() {
        let mut s=Scopes::new(); s.add([f64::NAN,0.,0.]).unwrap();
        s.add([0.,f64::INFINITY,0.]).unwrap();
        assert_eq!(s.nonfinite_samples,2); assert_eq!(s.finite_samples,0);
        assert!(s.mean_rgb().is_none());
    }
    #[test] fn y_is_linear_not_rgb_value_or_encoded_average() {
        let mut s=Scopes::new(); s.add([0.5;3]).unwrap();
        assert_eq!(s.rgb[0].bins[128],1);
        assert_eq!(s.linear_y.bins[(srgb_to_linear(0.5)*256.) as usize],1);
    }
    #[test] fn lab_d65_reference_colours() {
        for (rgb,expected) in [([0.,0.,0.],[0.,0.,0.]),
            ([1.,1.,1.],[100.,0.,0.]),([1.,0.,0.],[53.2408,80.0925,67.2032])] {
            let actual=srgb_to_lab_d65(rgb);
            for i in 0..3 {assert!((actual[i]-expected[i]).abs()<0.001);}
        }
    }
    #[test] fn sample_budget_is_enforced_before_mutation() {
        let mut s=Scopes::new(); for _ in 0..MAX_SAMPLES {s.add([0.;3]).unwrap();}
        assert!(s.add([0.;3]).is_err()); assert_eq!(s.samples,MAX_SAMPLES);
    }
    #[test] fn mean_domain_and_signed_trc_are_explicit() {
        let mut s=Scopes::new();s.add([0.;3]).unwrap();s.add([1.;3]).unwrap();
        assert_eq!(s.mean_rgb(),Some([0.5;3]));
        assert_eq!(srgb_to_linear(-0.5),-srgb_to_linear(0.5));
    }
}
