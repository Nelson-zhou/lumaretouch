//! Display-referred point-curve compiler. Pure Rust, no image/GUI dependency.
//! PCHIP (Fritsch–Butland): shape-preserving within each interval; intentional
//! non-monotone control points are allowed. Outside [0,1], use endpoint tangents.
//! Consumers apply master first, then the corresponding R/G/B curve.

pub const MAX_POINTS: usize = 64;
pub const MIN_SPACING: f64 = 1.0e-5;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Point { pub x: f64, pub y: f64 }

#[derive(Debug, Clone, PartialEq)]
pub struct Segment {
    pub x: f64,
    pub width: f64,
    /// y = a + t*(b + t*(c + t*d)), t=(x-segment.x)/width.
    pub coefficients: [f64; 4],
}

#[derive(Debug, Clone, PartialEq)]
pub struct Curve {
    pub identity: bool,
    pub segments: Vec<Segment>,
    pub lower: [f64; 2], // value at zero, derivative at zero
    pub upper: [f64; 2], // value at one, derivative at one
}

fn endpoint(h0: f64, h1: f64, d0: f64, d1: f64) -> f64 {
    let d = ((2.0*h0+h1)*d0-h0*d1)/(h0+h1);
    if d.signum() != d0.signum() || d0 == 0.0 { return 0.0; }
    if d0.signum() != d1.signum() && d.abs() > 3.0*d0.abs() { return 3.0*d0; }
    d
}

pub fn compile(points: &[Point]) -> Result<Curve, &'static str> {
    if !(2..=MAX_POINTS).contains(&points.len()) { return Err("curve needs 2..64 points"); }
    if points.iter().any(|p| !p.x.is_finite() || !p.y.is_finite() ||
                        !(0.0..=1.0).contains(&p.x) || !(0.0..=1.0).contains(&p.y)) {
        return Err("curve points must be finite and in [0,1]");
    }
    if points[0].x != 0.0 || points[points.len()-1].x != 1.0 {
        return Err("curve endpoints must have x=0 and x=1");
    }
    let n = points.len();
    let mut h = Vec::with_capacity(n-1);
    let mut delta = Vec::with_capacity(n-1);
    for pair in points.windows(2) {
        let width = pair[1].x-pair[0].x;
        if width < MIN_SPACING { return Err("curve x values must increase with minimum spacing"); }
        h.push(width); delta.push((pair[1].y-pair[0].y)/width);
    }
    let mut slope = vec![0.0; n];
    if n == 2 { slope.fill(delta[0]); }
    else {
        slope[0] = endpoint(h[0],h[1],delta[0],delta[1]);
        slope[n-1] = endpoint(h[n-2],h[n-3],delta[n-2],delta[n-3]);
        for i in 1..n-1 {
            let (a,b) = (delta[i-1],delta[i]);
            if a != 0.0 && b != 0.0 && a.signum() == b.signum() {
                let w1 = 2.0*h[i]+h[i-1];
                let w2 = h[i]+2.0*h[i-1];
                slope[i] = (w1+w2)/(w1/a+w2/b);
            }
        }
    }
    let segments = (0..n-1).map(|i| {
        let difference = points[i+1].y-points[i].y;
        let b = h[i]*slope[i];
        let end = h[i]*slope[i+1];
        Segment {x:points[i].x, width:h[i], coefficients:[points[i].y,b,
            3.0*difference-2.0*b-end, b+end-2.0*difference]}
    }).collect();
    Ok(Curve {identity:points.iter().all(|p| p.x==p.y), segments,
              lower:[points[0].y,slope[0]],upper:[points[n-1].y,slope[n-1]]})
}

impl Curve {
    pub fn evaluate(&self, x: f64) -> f64 {
        if self.identity || x.is_nan() { return x; }
        if x < 0.0 { return self.lower[0]+x*self.lower[1]; }
        if x > 1.0 { return self.upper[0]+(x-1.0)*self.upper[1]; }
        let index = self.segments.partition_point(|s| s.x <= x).saturating_sub(1);
        let s = &self.segments[index];
        let t = (x-s.x)/s.width;
        let [a,b,c,d] = s.coefficients;
        a+t*(b+t*(c+t*d))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn curve(values:&[(f64,f64)]) -> Curve {
        compile(&values.iter().map(|&(x,y)|Point{x,y}).collect::<Vec<_>>()).unwrap()
    }
    fn near(a:f64,b:f64) { assert!((a-b).abs()<1e-12,"{a} != {b}"); }
    #[test] fn identity_bypasses_negative_hdr_and_signed_zero() {
        let c=curve(&[(0.0,0.0),(0.2,0.2),(1.0,1.0)]);
        for x in [-10.0,-0.0,0.3,1.0,20.0,f64::INFINITY] {assert_eq!(c.evaluate(x).to_bits(),x.to_bits());}
    }
    #[test] fn two_points_are_linear_with_tangent_extrapolation() {
        let c=curve(&[(0.0,0.2),(1.0,0.8)]);
        for x in [-2.0,0.0,0.4,1.0,3.0] {near(c.evaluate(x),0.2+0.6*x);}
    }
    #[test] fn interpolation_reproduces_control_points() {
        let p=[(0.0,0.1),(0.15,0.4),(0.7,0.2),(1.0,0.9)];let c=curve(&p);
        for (x,y) in p {near(c.evaluate(x),y);}
    }
    #[test] fn every_segment_stays_between_endpoints_even_nonmonotone() {
        let p=[(0.0,0.1),(0.03,0.8),(0.4,0.8),(0.9,0.2),(1.0,0.9)];let c=curve(&p);
        for pair in p.windows(2) {for i in 0..=1000 {
            let y=c.evaluate(pair[0].0+(pair[1].0-pair[0].0)*i as f64/1000.0);
            assert!(y>=pair[0].1.min(pair[1].1)-1e-12 && y<=pair[0].1.max(pair[1].1)+1e-12);
        }}
    }
    #[test] fn adjacent_derivatives_are_continuous() {
        let c=curve(&[(0.0,0.0),(0.1,0.3),(0.5,0.7),(1.0,1.0)]);
        for pair in c.segments.windows(2) {
            let [_,b,c,d]=pair[0].coefficients;
            near((b+2.0*c+3.0*d)/pair[0].width,pair[1].coefficients[1]/pair[1].width);
        }
    }
    #[test] fn three_point_golden_vector_with_flat_endpoint() {
        let c=curve(&[(0.0,0.0),(0.5,1.0),(1.0,1.0)]);
        near(c.evaluate(0.25),0.6875);
        near(c.evaluate(0.75),1.0);
        near(c.evaluate(-0.1),-0.3);
        near(c.evaluate(1.1),1.0);
    }
    #[test] fn invalid_points_are_rejected_not_sorted_or_clamped() {
        for p in [vec![],vec![Point{x:0.0,y:0.0}],
            vec![Point{x:0.0,y:0.0},Point{x:1.0,y:f64::NAN}],
            vec![Point{x:0.1,y:0.0},Point{x:1.0,y:1.0}],
            vec![Point{x:0.0,y:0.0},Point{x:0.0,y:0.5},Point{x:1.0,y:1.0}],
            vec![Point{x:0.0,y:0.0},Point{x:1e-7,y:0.5},Point{x:1.0,y:1.0}],
            vec![Point{x:0.0,y:-0.1},Point{x:1.0,y:1.0}]] {assert!(compile(&p).is_err());}
    }
}
