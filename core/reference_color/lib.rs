// SPDX-License-Identifier: GPL-3.0-or-later
//! Original fixed-reference robust photometric fit on geometrically matched patches.
//! OpenCV-style overlap reasoning, not its uchar stitching gain solver. No model.
#[allow(dead_code)]
#[path = "../curves/curve.rs"]
mod curve;
use std::slice;
const MIN: usize = 64;
const MAX: usize = 4096;
fn median(v: &mut [f64]) -> f64 {
    v.sort_by(f64::total_cmp);
    (v[(v.len()-1)/2]+v[v.len()/2])*0.5
}
fn center(pairs:&[[f64;3]])->[f64;3] {
    std::array::from_fn(|c|median(&mut pairs.iter().map(|v|v[c]).collect::<Vec<_>>()))
}
fn fit(reference:&[f64],target:&[f64])->Result<([f64;7],Vec<u8>),i32> {
    if reference.len()!=target.len()||reference.len()%3!=0||!(MIN..=MAX).contains(&(target.len()/3)){return Err(1);}
    if reference.iter().chain(target).any(|x|!x.is_finite()){return Err(2);}
    let mut ratios=Vec::new();
    let mut admitted=Vec::new();
    for (index,(r,t)) in reference.chunks_exact(3).zip(target.chunks_exact(3)).enumerate() {
        // Avoid quantisation/noise amplification and clipped channels. Full RGB
        // precision survives; these thresholds admit fitting, never clamp pixels.
        if r.iter().chain(t).any(|x|*x<=0.02||*x>=0.98){continue;}
        admitted.push(index);
        ratios.push(std::array::from_fn(|c|(curve::srgb_decode(r[c])/curve::srgb_decode(t[c])).log2()));
    }
    if ratios.len()<MIN{return Err(3);}
    let initial=center(&ratios);
    let consensus:Vec<_>=ratios.iter().copied().filter(|p|(0..3).all(|c|(p[c]-initial[c]).abs()<=0.18)).collect();
    if consensus.len()<MIN||consensus.len()*100<ratios.len()*65{return Err(4);}
    let gain=center(&consensus);
    if gain.iter().any(|g|g.abs()>2.){return Err(5);}
    let mut residuals:Vec<_>=consensus.iter().map(|p|(0..3).map(|c|(p[c]-gain[c]).abs()).fold(0.,f64::max)).collect();
    residuals.sort_by(f64::total_cmp);
    let mut mask=vec![0;target.len()/3];
    for (index,p) in admitted.iter().zip(&ratios) {
        if (0..3).all(|c|(p[c]-initial[c]).abs()<=0.18) {mask[*index]=1;}
    }
    Ok(([gain[0],gain[1],gain[2],residuals[(residuals.len()-1)*9/10],
        consensus.len() as f64,consensus.len() as f64/ratios.len() as f64,
        ratios.len() as f64/(target.len()/3) as f64],mask))
}
#[no_mangle]
pub extern "C" fn lrt_reference_color_abi()->u32{1}
/// Buffers: reference and target count*3 finite encoded-sRGB doubles; out 7 doubles.
/// Caller guarantees valid readable/writable extents and nonoverlap. inliers has count bytes. Writes atomic.
/// Result: log2 gains, p90 residual stops, consensus count/fraction, usable fraction.
#[no_mangle]
pub unsafe extern "C" fn lrt_reference_color_fit(reference:*const f64,target:*const f64,count:usize,out:*mut f64,inliers:*mut u8)->i32 {
    if reference.is_null()||target.is_null()||out.is_null()||inliers.is_null()||!(MIN..=MAX).contains(&count){return 1;}
    match fit(slice::from_raw_parts(reference,count*3),slice::from_raw_parts(target,count*3)) {
        Ok((result,mask))=>{slice::from_raw_parts_mut(out,7).copy_from_slice(&result);slice::from_raw_parts_mut(inliers,count).copy_from_slice(&mask);0},Err(code)=>code,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn identical_pairs_give_exact_zero() {
        let rgb:Vec<_>=(0..100).flat_map(|i|[0.1+i as f64*0.005;3]).collect();
        let (out,_)=fit(&rgb,&rgb).unwrap();assert_eq!(&out[..4],&[0.;4]);
    }
    #[test] fn known_full_precision_gain_and_outliers() {
        let t:Vec<_>=(0..100).flat_map(|i|[0.03+i as f64*0.002;3].map(curve::srgb_encode)).collect();
        let mut r:Vec<_>=t.chunks_exact(3).flat_map(|v|std::array::from_fn::<_,3,_>(|c|curve::srgb_encode(curve::srgb_decode(v[c])*[1.2,1.1,0.9][c]))).collect();
        for x in &mut r[..30]{*x=0.8;}
        let (out,_)=fit(&r,&t).unwrap();
        for c in 0..3 {assert!((out[c].exp2()-[1.2,1.1,0.9][c]).abs()<1e-10);}
    }
    #[test] fn low_support_and_nonfinite_refuse() {
        assert_eq!(fit(&vec![1.;300],&vec![0.5;300]),Err(3));
        assert_eq!(fit(&vec![f64::NAN;300],&vec![0.5;300]),Err(2));
    }
}
