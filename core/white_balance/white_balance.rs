//! Corrected white-balance scalar foundation; not wired into production rendering yet.
//! Independently implemented published CIE D equations and linear-sRGB matrix facts.
//! Source anchors and compatibility constraints: README.md and the versioning plan.
//! This is a diagonal white-ratio adjustment, NOT a full Bradford adaptation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error { Temperature, Shift, Tint, White, Sample, Gain }
type Matrix = [[f64; 3]; 3];
const XYZ_TO_RGB: Matrix = [
    [12831.0/3959.0, -329.0/214.0, -1974.0/3959.0],
    [-851781.0/878810.0, 1648619.0/878810.0, 36519.0/878810.0],
    [705.0/12673.0, -2585.0/12673.0, 705.0/667.0],
];
pub const Y_WEIGHTS: [f64; 3] = [87098.0/409605.0, 175762.0/245763.0, 12673.0/175545.0];
const BRADFORD: Matrix = [[0.8951,0.2664,-0.1614],[-0.7502,1.7135,0.0367],[0.0389,-0.0685,1.0296]];
fn dot(a: [f64; 3], b: [f64; 3]) -> f64 { a[0]*b[0]+a[1]*b[1]+a[2]*b[2] }
fn mul(m: Matrix, v: [f64; 3]) -> [f64; 3] { [dot(m[0],v),dot(m[1],v),dot(m[2],v)] }
fn inverse(m: Matrix) -> Matrix {
    let [[a,b,c],[d,e,f],[g,h,i]]=m;
    let det=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g);
    [[(e*i-f*h)/det,(c*h-b*i)/det,(b*f-c*e)/det],
     [(f*g-d*i)/det,(a*i-c*g)/det,(c*d-a*f)/det],
     [(d*h-e*g)/det,(b*g-a*h)/det,(a*e-b*d)/det]]
}
fn positive(v: [f64; 3]) -> bool { v.iter().all(|x| x.is_finite() && *x>0.0) }
/// CIE daylight locus only. Deliberately no guessed blackbody continuation.
pub fn daylight_xy(k: f64) -> Result<[f64; 2], Error> {
    if !k.is_finite() || !(4000.0..=25000.0).contains(&k) { return Err(Error::Temperature); }
    let t=1000.0/k;
    let x=if k<=7000.0 {0.244063+0.09911*t+2.9678*t*t-4.6070*t*t*t}
          else {0.237040+0.24748*t+1.9018*t*t-2.0064*t*t*t};
    Ok([x,-3.0*x*x+2.870*x-0.275])
}
fn white(k: f64, tint: f64) -> Result<[f64; 3], Error> {
    let [x,y]=daylight_xy(k)?;
    let mut cone=mul(BRADFORD,[x/y,1.0,(1.0-x-y)/y]);
    cone[0]*=1.0+0.1*tint; cone[1]*=1.0-0.1*tint;
    let rgb=mul(XYZ_TO_RGB,mul(inverse(BRADFORD),cone));
    if !positive(rgb) { return Err(Error::White); }
    let sum=rgb.iter().sum::<f64>();
    Ok(rgb.map(|v|v/sum))
}
/// Retains the existing positive-temperature=cooler ratio direction and tint scale.
pub fn manual_gains(reference: f64, shift: f64, tint: f64) -> Result<[f64; 3], Error> {
    if !shift.is_finite() || shift.abs()>2000.0 { return Err(Error::Shift); }
    if !tint.is_finite() || tint.abs()>1.0 { return Err(Error::Tint); }
    let source=white(reference,0.0)?;
    let target=white(reference+shift,tint)?;
    let gains=[target[0]/source[0],target[1]/source[1],target[2]/source[2]];
    if !positive(gains) { return Err(Error::Gain); } Ok(gains)
}
/// Input mean is already in the caller's explicitly defined linear sample domain.
/// Excludes EV/previous picks. Returns a replacement, not an accumulated correction.
/// Noise/clipping/coverage and gain-budget policy must be checked by the action owner.
pub fn neutral_gains(mean_linear: [f64; 3], manual: [f64; 3]) -> Result<[f64; 3], Error> {
    if !positive(mean_linear) { return Err(Error::Sample); }
    if !positive(manual) { return Err(Error::Gain); }
    let q=[mean_linear[0]*manual[0],mean_linear[1]*manual[1],mean_linear[2]*manual[2]];
    if !positive(q) { return Err(Error::Sample); }
    if q[0]==q[1] && q[1]==q[2] { return Ok([1.0;3]); }
    let y=dot(Y_WEIGHTS,q);let gains=q.map(|v|y/v);
    if !positive(gains) { return Err(Error::Gain); } Ok(gains)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn near(a:f64,b:f64,tolerance:f64){assert!((a-b).abs()<=tolerance,"{a} != {b}");}
    #[test] fn documented_daylight_anchor_and_independent_high_branch_fixture(){
        // Colour CIE D published example: 6504.38938305 -> [0.3127077...,0.3291128...].
        let p=daylight_xy(6504.38938305).unwrap();
        assert!((0.3127077..0.3127078).contains(&p[0]));assert!((0.3291128..0.3291129).contains(&p[1]));
        let p=daylight_xy(10000.0).unwrap();near(p[0],0.2787996,1e-14);near(p[1],0.29196720111952,1e-14);
    }
    #[test] fn piecewise_daylight_has_only_the_published_small_boundary_discontinuity(){
        let a=daylight_xy(7000.0-1e-6).unwrap();let b=daylight_xy(7000.0+1e-6).unwrap();
        for i in 0..2{assert!((a[i]-b[i]).abs()<1e-6);}
    }
    #[test] fn working_space_matrix_maps_exact_standard_d65_to_neutral_rgb(){
        let rgb=mul(XYZ_TO_RGB,[0.3127/0.3290,1.0,(1.0-0.3127-0.3290)/0.3290]);
        for v in rgb{near(v,1.0,1e-12);}near(Y_WEIGHTS.iter().sum(),1.0,1e-15);
        // Do not substitute daylight-at-6500 for the exact standardized D65 white.
    }
    #[test] fn zero_manual_adjustment_is_exact_and_direction_is_explicit(){
        for k in [4000.0,4500.0,6500.0,7000.0,10000.0,25000.0]{assert_eq!(manual_gains(k,0.0,0.0).unwrap(),[1.0;3]);}
        let cool=manual_gains(6500.0,1000.0,0.0).unwrap();assert!(cool[0]<1.0&&cool[2]>1.0);
        let magenta=manual_gains(6500.0,0.0,1.0).unwrap();assert!(magenta[0]>magenta[1]&&magenta[2]>magenta[1]);
    }
    #[test] fn sampled_full_domain_grid_remains_positive_and_finite(){
        for reference in (4000..=25000).step_by(50){for shift in (-2000..=2000).step_by(100){
            if !(4000..=25000).contains(&(reference+shift)){continue;}
            for tint in [-1.0,-0.75,-0.5,-0.25,0.0,0.25,0.5,0.75,1.0]{
                assert!(positive(manual_gains(reference as f64,shift as f64,tint).unwrap()));
            }
        }}
    }
    #[test] fn invalid_inputs_are_rejected_without_clamping(){
        for k in [3999.0,25001.0,f64::NAN,f64::INFINITY]{assert_eq!(daylight_xy(k),Err(Error::Temperature));}
        assert_eq!(manual_gains(4000.0,-1.0,0.0),Err(Error::Temperature));
        assert_eq!(manual_gains(6500.0,2001.0,0.0),Err(Error::Shift));
        assert_eq!(manual_gains(6500.0,0.0,1.001),Err(Error::Tint));
        assert!(neutral_gains([0.0,0.2,0.3],[1.0;3]).is_err());
        assert!(neutral_gains([f64::NAN,0.2,0.3],[1.0;3]).is_err());
        assert!(neutral_gains([1.0;3],[f64::INFINITY,1.0,1.0]).is_err());
    }
    #[test] fn picked_gains_neutralize_after_manual_and_preserve_sample_y(){
        let mean=[0.12,0.24,0.36];let manual=manual_gains(6500.0,800.0,-0.25).unwrap();
        let p=neutral_gains(mean,manual).unwrap();let q=[mean[0]*manual[0],mean[1]*manual[1],mean[2]*manual[2]];
        let y=dot(Y_WEIGHTS,q);for i in 0..3{near(q[i]*p[i],y,1e-14);}
        assert_eq!(neutral_gains(mean,manual).unwrap(),p);
        assert_eq!(neutral_gains([0.2;3],[1.0;3]).unwrap(),[1.0;3]);
    }
}
