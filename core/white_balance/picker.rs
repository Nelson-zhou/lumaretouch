//! Bounded, versioned neutral-region policy. Inputs are projected linear samples,
//! not display RGB; producer provenance and source-risk projection remain required.
use super::white_balance::{neutral_gains, Y_WEIGHTS};
pub const POLICY: &str = "proxy-linear-neutral-v1";
pub const MAX_SAMPLES: usize = 121;
pub const COVERAGE_EPS: f64 = 1e-6;
pub const MIN_Y: f64 = 0.005;
pub const MIN_CHANNEL: f64 = 0.0001;
pub const MIN_GAIN: f64 = 1.0 / 16.0;
pub const MAX_GAIN: f64 = 16.0;
#[derive(Debug, Clone, Copy)]
pub struct Sample { pub linear: [f64;3], pub coverage: f64, pub risk: f64 }
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error { Size, Sample, Coverage, Clipped, Dark, Gain }
#[derive(Debug, PartialEq)]
pub struct Pick { pub mean: [f64;3], pub gains: [f64;3], pub count: usize }
fn luma(v: [f64;3]) -> f64 { if v[0]==v[1]&&v[1]==v[2] {v[0]} else {v.iter().zip(Y_WEIGHTS).map(|(v,w)|v*w).sum()} }
fn bounded_gain(v: f64) -> bool { v.is_finite() && (MIN_GAIN..=MAX_GAIN).contains(&v) }
/// Thresholds are a product safety policy, not sensor/RAW clipping detection and
/// not copied darktable constants. Reject rather than silently clamp the recipe.
pub fn pick(samples: &[Sample], manual: [f64;3]) -> Result<Pick,Error> {
    if samples.is_empty() || samples.len()>MAX_SAMPLES { return Err(Error::Size); }
    if !manual.iter().all(|v|v.is_finite()&&*v>0.0) { return Err(Error::Gain); }
    let mut mean=[0.0;3];
    for sample in samples {
        if !sample.linear.iter().all(|v|v.is_finite()&&(0.0..=1.0).contains(v)) { return Err(Error::Sample); }
        if !sample.coverage.is_finite() || !(1.0-COVERAGE_EPS..=1.0+COVERAGE_EPS).contains(&sample.coverage) { return Err(Error::Coverage); }
        if !sample.risk.is_finite() || sample.risk!=0.0 { return Err(Error::Clipped); }
        for (sum,value) in mean.iter_mut().zip(sample.linear) { *sum+=value; }
    }
    for value in &mut mean { *value/=samples.len() as f64; }
    if luma(mean)<MIN_Y || mean.iter().any(|v|*v<MIN_CHANNEL) { return Err(Error::Dark); }
    let gains=neutral_gains(mean,manual).map_err(|_|Error::Gain)?;
    if !(0..3).all(|i|bounded_gain(gains[i])&&bounded_gain(gains[i]*manual[i])) { return Err(Error::Gain); }
    Ok(Pick {mean,gains,count:samples.len()})
}

pub fn handle(tokens: &mut std::str::SplitWhitespace<'_>) -> Result<String,String> {
    if tokens.next()!=Some(POLICY) { return Err("unsupported WB sample policy".into()); }
    fn number(tokens: &mut std::str::SplitWhitespace<'_>) -> Result<f64,String> {
        let value=tokens.next().ok_or("missing picker scalar")?.parse::<f64>().map_err(|_|"invalid picker scalar")?;
        if !value.is_finite() { return Err("nonfinite picker scalar".into()); } Ok(value)
    }
    let manual=[number(tokens)?,number(tokens)?,number(tokens)?];
    let count=tokens.next().ok_or("missing sample count")?.parse::<usize>().map_err(|_|"invalid sample count")?;
    if !(1..=MAX_SAMPLES).contains(&count) { return Err("invalid sample count".into()); }
    let mut samples=Vec::with_capacity(count);
    for _ in 0..count {
        samples.push(Sample {linear:[number(tokens)?,number(tokens)?,number(tokens)?],coverage:number(tokens)?,risk:number(tokens)?});
    }
    if tokens.next().is_some() { return Err("unexpected trailing picker input".into()); }
    let result=pick(&samples,manual).map_err(|e|format!("WB sample rejected: {e:?}"))?;
    Ok(format!("{{\"version\":1,\"policy\":\"{}\",\"samples\":{},\"mean_linear\":[{:e},{:e},{:e}],\"gains\":[{:e},{:e},{:e}]}}",
        POLICY,result.count,result.mean[0],result.mean[1],result.mean[2],result.gains[0],result.gains[1],result.gains[2]))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sample(linear:[f64;3])->Sample { Sample {linear,coverage:1.0,risk:0.0} }
    #[test] fn valid_region_neutralizes_mean_and_preserves_y_without_accumulation() {
        let samples=[sample([0.1,0.2,0.3]),sample([0.3,0.4,0.5])];let manual=[0.9,1.0,1.2];
        let p=pick(&samples,manual).unwrap();assert_eq!(p.count,2);
        let q=[p.mean[0]*manual[0],p.mean[1]*manual[1],p.mean[2]*manual[2]];
        for i in 0..3 { assert!((q[i]*p.gains[i]-luma(q)).abs()<1e-14); }
        assert_eq!(pick(&samples,manual).unwrap(),p);
    }
    #[test] fn exact_neutral_is_identity() { assert_eq!(pick(&[sample([0.2;3])],[1.0;3]).unwrap().gains,[1.0;3]); }
    #[test] fn size_and_nonfinite_samples_fail_closed() {
        assert_eq!(pick(&[],[1.0;3]),Err(Error::Size));
        assert_eq!(pick(&vec![sample([0.2;3]);122],[1.0;3]),Err(Error::Size));
        for v in [f64::NAN,f64::INFINITY,-0.1,1.1] { assert_eq!(pick(&[sample([v,0.2,0.3])],[1.0;3]),Err(Error::Sample)); }
    }
    #[test] fn any_source_fill_or_clipped_contribution_rejects_whole_region() {
        let mut s=sample([0.2;3]);s.coverage=0.99;assert_eq!(pick(&[s],[1.0;3]),Err(Error::Coverage));
        for edge in [1.0-COVERAGE_EPS,1.0,1.0+COVERAGE_EPS] { s.coverage=edge;assert!(pick(&[s],[1.0;3]).is_ok()); }
        s.coverage=1.0-2.0*COVERAGE_EPS;assert_eq!(pick(&[s],[1.0;3]),Err(Error::Coverage));
        s.coverage=1.0;s.risk=1e-20;assert_eq!(pick(&[sample([0.2;3]),s],[1.0;3]),Err(Error::Clipped));
        s.risk=f64::NAN;assert_eq!(pick(&[s],[1.0;3]),Err(Error::Clipped));
    }
    #[test] fn dark_or_nearly_absent_channel_rejects_without_clamping() {
        assert!(pick(&[sample([MIN_Y;3])],[1.0;3]).is_ok());
        assert_eq!(pick(&[sample([MIN_Y/2.0;3])],[1.0;3]),Err(Error::Dark));
        assert_eq!(pick(&[sample([MIN_CHANNEL,0.2,0.3])],[1.0;3]),Err(Error::Gain));
        assert_eq!(pick(&[sample([MIN_CHANNEL/2.0,0.2,0.3])],[1.0;3]),Err(Error::Dark));
    }
    #[test] fn picked_and_effective_gain_budgets_both_apply() {
        assert_eq!(pick(&[sample([0.001,0.8,0.8])],[1.0;3]),Err(Error::Gain));
        assert_eq!(pick(&[sample([0.2;3])],[17.0;3]),Err(Error::Gain));
        assert_eq!(pick(&[sample([0.2;3])],[0.0;3]),Err(Error::Gain));
    }
    #[test] fn limits_are_inclusive_and_do_not_silently_expand() {
        assert!(bounded_gain(MIN_GAIN)&&bounded_gain(MAX_GAIN));
        assert!(!bounded_gain(MIN_GAIN/2.0)&&!bounded_gain(MAX_GAIN*2.0));
        assert!(pick(&vec![sample([0.2;3]);MAX_SAMPLES],[1.0;3]).is_ok());
    }
    #[test] fn bounded_wire_requires_policy_count_and_exact_scalars() {
        let good=format!("{POLICY} 1 1 1 1 .2 .2 .2 1 0");assert!(handle(&mut good.split_whitespace()).is_ok());
        for bad in ["unknown 1 1 1 1 .2 .2 .2 1 0".to_owned(),format!("{POLICY} 1 1 1 122"),format!("{good} extra"),format!("{POLICY} 1 1 1 1 nan .2 .2 1 0")] {
            assert!(handle(&mut bad.split_whitespace()).is_err());
        }
    }
}
