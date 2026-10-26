//! Original bounded, stratified trimmed-log gray-world estimator. Not AI or a
//! neutral-object detector: a spatially uniform dominant colour can mislead it.
//! All thresholds are conservative product policy, not calibrated camera facts.
use super::white_balance::{neutral_gains, Y_WEIGHTS};

pub const POLICY: &str = "stratified-trimmed-log-gray-world-v1";
pub const GRID: usize = 32;
pub const SAMPLES: usize = GRID * GRID;
pub const MIN_GAIN: f64 = 0.25;
pub const MAX_GAIN: f64 = 4.0;
const MIN_TILE: usize = 24;
const MIN_ACCEPTED: usize = 512;
const MIN_TILES: usize = 12;
const MAX_LOG_DEVIATION: f64 = 0.30;

#[derive(Clone, Copy)]
pub struct Sample { pub rgb: [f64; 3], pub coverage: f64, pub risk: f64 }
#[derive(Debug, PartialEq)]
pub enum Error { Size, Invalid, Insufficient, Unstable, Gain }
#[derive(Debug, PartialEq)]
pub struct Estimate {
    pub gains: [f64; 3], pub illuminant: [f64; 3],
    pub accepted: usize, pub stable_tiles: usize, pub spread: f64,
}
fn median(values: &mut [f64]) -> f64 {
    values.sort_by(f64::total_cmp);
    let middle=values.len()/2;
    if values.len()%2==0 {(values[middle-1]+values[middle])*0.5} else {values[middle]}
}
fn trimmed(values: &mut [f64]) -> f64 {
    values.sort_by(f64::total_cmp);
    let trim=values.len()/5;
    let kept=&values[trim..values.len()-trim];
    kept.iter().sum::<f64>()/kept.len() as f64
}
fn bounded(value: f64) -> bool { value.is_finite() && (MIN_GAIN..=MAX_GAIN).contains(&value) }

/// Exactly a row-major 32x32 grid, at unique stratum centres on the frozen
/// projected input. Equal-area tile statistics prevent one bright area from
/// dominating. No previous picked correction, EV, or post-WB pixel is an input.
pub fn estimate(samples: &[Sample], manual: [f64; 3]) -> Result<Estimate, Error> {
    if samples.len()!=SAMPLES {return Err(Error::Size);}
    if !manual.iter().all(|v|v.is_finite()&&*v>0.0) {return Err(Error::Gain);}
    let mut tiles: Vec<(Vec<f64>,Vec<f64>)>=(0..16).map(|_|(Vec::new(),Vec::new())).collect();
    let mut accepted=0;
    for (index,s) in samples.iter().enumerate() {
        if !s.rgb.iter().all(|v|v.is_finite()) || !s.coverage.is_finite() || !s.risk.is_finite()
            || !(0.0..=1.000001).contains(&s.coverage) || !(0.0..=1.000001).contains(&s.risk) {
            return Err(Error::Invalid);
        }
        // Coverage and risk were projected independently from the same source.
        // Tiny clipped contributions cannot be hidden by averaging RGB.
        if s.coverage<1.0-1e-6 || s.risk!=0.0 {continue;}
        let y=s.rgb.iter().zip(Y_WEIGHTS).map(|(v,w)|v*w).sum::<f64>();
        if y<0.01 || s.rgb.iter().any(|v|*v<0.002||*v>=0.98) {continue;}
        let tile=(index/GRID/8)*4+(index%GRID/8);
        tiles[tile].0.push((s.rgb[0]/s.rgb[1]).ln());
        tiles[tile].1.push((s.rgb[2]/s.rgb[1]).ln());
        accepted+=1;
    }
    if accepted<MIN_ACCEPTED {return Err(Error::Insufficient);}
    let cells:Vec<(usize,[f64;2])>=tiles.iter_mut().enumerate().filter_map(|(i,(r,b))| {
        if r.len()<MIN_TILE {None} else {Some((i,[trimmed(r),trimmed(b)]))}
    }).collect();
    if cells.len()<MIN_TILES {return Err(Error::Insufficient);}
    let centre=[median(&mut cells.iter().map(|(_,c)|c[0]).collect::<Vec<_>>()),
                median(&mut cells.iter().map(|(_,c)|c[1]).collect::<Vec<_>>())];
    let mut quadrants=[0usize;4];
    let stable:Vec<[f64;2]>=cells.iter().filter_map(|(i,c)| {
        if (c[0]-centre[0]).abs().max((c[1]-centre[1]).abs())>MAX_LOG_DEVIATION {return None;}
        quadrants[(i/4/2)*2+(i%4/2)]+=1;Some(*c)
    }).collect();
    if stable.len()<MIN_TILES || quadrants.iter().any(|n|*n<3) {return Err(Error::Unstable);}
    let chroma=[median(&mut stable.iter().map(|c|c[0]).collect::<Vec<_>>()),
                median(&mut stable.iter().map(|c|c[1]).collect::<Vec<_>>())];
    let illuminant=[chroma[0].exp(),1.0,chroma[1].exp()];
    // Replacement correction mathematically compensates the retained manual
    // gains. Same pre-WB input + same manual controls => same stored correction.
    let gains=neutral_gains(illuminant,manual).map_err(|_|Error::Gain)?;
    if !(0..3).all(|i|bounded(gains[i])&&bounded(gains[i]*manual[i])) {return Err(Error::Gain);}
    let spread=stable.iter().map(|c|(c[0]-chroma[0]).abs().max((c[1]-chroma[1]).abs())).fold(0.0,f64::max);
    Ok(Estimate {gains,illuminant,accepted,stable_tiles:stable.len(),spread})
}

// AUTHORED / UNRUN: executable policy fixtures, not runtime acceptance evidence.
#[cfg(test)]
#[path="automatic_test.rs"]
mod tests;
