//! Original fixed-alpha colour estimation and conservative near-edge despill.
//! Source-only implementation; all authored fixtures are UNRUN.
//! ABI 1: full-domain immutable, straight linear-sRGB-D65 SDR inputs. No alpha
//! output and no alpha modification. Read README.md for limitations and budgets.
use std::slice;

const MAX_PIXELS: usize = 32_000_000;
const MAX_BYTES: usize = 2_147_483_648;
const ANALYSIS_SIDE: usize = 1024;
const SCRATCH_BYTES: usize = 67_108_864;
const NONE: u32 = u32::MAX;
const LUMA: [f64; 3] = [0.2126, 0.7152, 0.0722];
type Cancel = Option<extern "C" fn() -> i32>;
type Rgb = [f64; 3];

fn stopped(cancel: Cancel) -> bool { cancel.map_or(false, |f| f() != 0) }
fn poll(cancel: Cancel) -> Result<(), i32> { if stopped(cancel) { Err(3) } else { Ok(()) } }
fn floats(n: usize) -> Result<Vec<f32>, i32> {
    let mut v = Vec::new(); v.try_reserve_exact(n).map_err(|_| 4)?;
    v.resize(n, 0.0); Ok(v)
}
fn indices(n: usize) -> Result<Vec<u32>, i32> {
    let mut v = Vec::new(); v.try_reserve_exact(n).map_err(|_| 4)?;
    v.resize(n, NONE); Ok(v)
}
fn rgb(a: &[f32], i: usize) -> Rgb { [a[3*i] as f64, a[3*i+1] as f64, a[3*i+2] as f64] }
fn dot(a: Rgb, b: Rgb) -> f64 { a[0]*b[0]+a[1]*b[1]+a[2]*b[2] }
fn sub(a: Rgb, b: Rgb) -> Rgb { [a[0]-b[0],a[1]-b[1],a[2]-b[2]] }
fn mul(a: Rgb, s: f64) -> Rgb { [a[0]*s,a[1]*s,a[2]*s] }
fn norm(a: Rgb) -> f64 { dot(a,a).sqrt() }
fn chroma(a: Rgb) -> Rgb { let y=dot(a,LUMA); [a[0]-y,a[1]-y,a[2]-y] }
fn fade(a: f64, b: f64, x: f64) -> f64 {
    let t=((x-a)/(b-a)).clamp(0.0,1.0); t*t*(3.0-2.0*t)
}
fn distance(i: usize, seed: u32, w: usize) -> usize {
    if seed==NONE { usize::MAX } else {
        let j=seed as usize; (i%w).abs_diff(j%w)+(i/w).abs_diff(j/w)
    }
}

// Deterministic two-pass nearest-seed propagation, with optional foreground
// connectivity constraint. It may omit winding support, never invent a seed.
fn propagate(map: &mut [u32], alpha: &[f32], w: usize, h: usize,
             foreground_only: bool, cancel: Cancel) -> Result<(), i32> {
    for reverse in [false,true] {
        for line in 0..h {
            poll(cancel)?; let y=if reverse {h-1-line} else {line};
            for col in 0..w {
                let x=if reverse {w-1-col} else {col}; let i=y*w+x;
                if foreground_only && alpha[i]<0.05 { continue; }
                let candidates=if reverse {
                    [if x+1<w {map[i+1]} else {NONE},if y+1<h {map[i+w]} else {NONE}]
                } else {
                    [if x>0 {map[i-1]} else {NONE},if y>0 {map[i-w]} else {NONE}]
                };
                for seed in candidates {
                    let d=distance(i,seed,w); let old=distance(i,map[i],w);
                    if d<old || (d==old && seed<map[i]) { map[i]=seed; }
                }
            }
        }
    }
    Ok(())
}

// Independent local prior and disagreement estimate. A seed alone is not enough.
fn seed_stats(source: &[f32], alpha: &[f32], seed: u32, w: usize, h: usize,
              foreground: bool) -> Option<(Rgb,f64)> {
    if seed==NONE { return None; }
    let i=seed as usize; let (x,y)=(i%w,i/w);
    let mut mean=[0.0;3]; let mut square=0.0; let mut count=0.0;
    for yy in y.saturating_sub(1)..=(y+1).min(h-1) {
        for xx in x.saturating_sub(1)..=(x+1).min(w-1) {
            let j=yy*w+xx;
            if (foreground && alpha[j]<0.98) || (!foreground && alpha[j]>0.02) { continue; }
            let c=rgb(source,j); for k in 0..3 { mean[k]+=c[k]; }
            square+=dot(c,c); count+=1.0;
        }
    }
    if count<3.0 { return None; }
    for k in 0..3 {mean[k]/=count;}
    Some((mean,(square/count-dot(mean,mean)).max(0.0).sqrt()))
}

// A straight support path must remain on this subject and avoid luminance
// discontinuities. This deliberately abstains on thin or disconnected details.
fn coherent_path(source: &[f32], alpha: &[f32], i: usize, seed: u32,
                 w: usize, opaque: bool) -> bool {
    if seed==NONE { return false; }
    let (x,y)=(i%w,i/w); let (sx,sy)=(seed as usize%w,seed as usize/w);
    let steps=x.abs_diff(sx).max(y.abs_diff(sy));
    let mut last=dot(rgb(source,i),LUMA);
    for step in 1..=steps {
        let t=step as f64/steps as f64;
        let xx=(x as f64+(sx as f64-x as f64)*t).round() as usize;
        let yy=(y as f64+(sy as f64-y as f64)*t).round() as usize;
        let j=yy*w+xx;
        if alpha[j] < if opaque {0.95} else {0.05} { return false; }
        let next=dot(rgb(source,j),LUMA);
        if opaque && (next-last).abs()>0.045 { return false; }
        last=next;
    }
    true
}

// Area-average from the immutable source, never repeatedly resample the image.
fn reduce(source: &[f32], alpha: &[f32], sw: usize, sh: usize, w: usize, h: usize,
          cancel: Cancel) -> Result<(Vec<f32>,Vec<f32>),i32> {
    let mut image=floats(3*w*h)?; let mut matte=floats(w*h)?;
    // A single coarse row may span the entire source on a very wide image.
    // Bound work between cancellation polls by source samples, not output rows.
    let mut until_poll=4096usize;
    for y in 0..h {
        poll(cancel)?;
        for x in 0..w {
            let mut sum=[0.0;4]; let mut count=0.0;
            for sy in y*sh/h..((y+1)*sh/h).max(y*sh/h+1) {
                for sx in x*sw/w..((x+1)*sw/w).max(x*sw/w+1) {
                    let i=sy*sw+sx;
                    for c in 0..3 {sum[c]+=source[3*i+c] as f64;}
                    sum[3]+=alpha[i] as f64; count+=1.0;
                    until_poll-=1;
                    if until_poll==0 {poll(cancel)?;until_poll=4096;}
                }
            }
            let i=y*w+x;
            for c in 0..3 {image[3*i+c]=(sum[c]/count) as f32;}
            matte[i]=(sum[3]/count) as f32;
        }
    }
    Ok((image,matte))
}
fn sample(field: &[f32], w: usize, h: usize, x: f64, y: f64, c: usize) -> f64 {
    let x=x.clamp(0.0,(w-1) as f64); let y=y.clamp(0.0,(h-1) as f64);
    let ix=x.floor() as usize; let iy=y.floor() as usize; let tx=x-ix as f64; let ty=y-iy as f64;
    let mut v=0.0;
    for (xx,wx) in [(ix,1.0-tx),((ix+1).min(w-1),tx)] {
        for (yy,wy) in [(iy,1.0-ty),((iy+1).min(h-1),ty)] {v+=field[3*(yy*w+xx)+c] as f64*wx*wy;}
    }
    v
}

// Local normal equations for the documented joint F/B energy. Red-black order
// is deterministic and race-free. No componentwise colour clamping: a common
// six-component line step keeps the unconstrained solve inside the SDR box.
fn relax(image: &[f32], alpha: &[f32], f: &mut [f32], b: &mut [f32],
         w: usize, h: usize, rounds: usize, cancel: Cancel) -> Result<(),i32> {
    for _ in 0..rounds { for parity in 0..2 { for y in 0..h {
        poll(cancel)?;
        for x in 0..w {
            if (x+y)%2!=parity {continue;}
            let i=y*w+x; let a=alpha[i] as f64; let z=1.0-a;
            let mut lambda=0.002; // weak identity prior makes a 1x1 solve defined
            let original=rgb(image,i); let mut rf=mul(original,a+0.002); let mut rb=mul(original,z+0.002);
            for j in [if x>0 {i-1} else {i},if x+1<w {i+1} else {i},
                      if y>0 {i-w} else {i},if y+1<h {i+w} else {i}] {
                if i==j {continue;}
                let weight=0.002+0.15*(a-alpha[j] as f64).abs(); lambda+=weight;
                for c in 0..3 {rf[c]+=weight*f[3*j+c] as f64;rb[c]+=weight*b[3*j+c] as f64;}
            }
            let aa=a*a+lambda; let bb=z*z+lambda; let ab=a*z; let det=aa*bb-ab*ab;
            if !det.is_finite() || det<=0.0 {return Err(5);}
            let old_f=rgb(f,i); let old_b=rgb(b,i); let mut df=[0.0;3]; let mut db=[0.0;3];
            let mut step=1.0f64;
            for c in 0..3 {
                let next_f=if a==1.0 {original[c]} else {(bb*rf[c]-ab*rb[c])/det};
                let next_b=if a==0.0 {original[c]} else {(aa*rb[c]-ab*rf[c])/det};
                df[c]=next_f-old_f[c]; db[c]=next_b-old_b[c];
                for (v,d) in [(old_f[c],df[c]),(old_b[c],db[c])] {
                    if !d.is_finite() {return Err(5);}
                    if d>0.0 {step=step.min((1.0-v)/d);} else if d<0.0 {step=step.min(-v/d);}
                }
            }
            if step<1.0 {step=step.max(0.0)*(1.0-1.0/1_048_576.0);}
            for c in 0..3 {f[3*i+c]=(old_f[c]+step*df[c]) as f32;b[3*i+c]=(old_b[c]+step*db[c]) as f32;}
        }
    }}}
    Ok(())
}

fn analysis_shape(mut w: usize, mut h: usize) -> (usize,usize) {
    while w>ANALYSIS_SIDE || h>ANALYSIS_SIDE {w=(w+1)/2;h=(h+1)/2;}
    (w,h)
}
fn solve(source: &[f32], alpha: &[f32], fg: &[u32], bg: &[u32],
         sw: usize, sh: usize, cancel: Cancel) -> Result<(Vec<f32>,Vec<f32>),i32> {
    let mut dimensions=Vec::new(); let (mut w,mut h)=analysis_shape(sw,sh);
    dimensions.push((w,h));
    while w>32 || h>32 {w=(w+1)/2;h=(h+1)/2;dimensions.push((w,h));}
    let (mut old_f,mut old_b)=(Vec::new(),Vec::new()); let (mut pw,mut ph)=(0,0);
    for &(w,h) in dimensions.iter().rev() {
        poll(cancel)?; let mut f=floats(3*w*h)?; let mut b=floats(3*w*h)?;
        for y in 0..h { poll(cancel)?; for x in 0..w {
            let i=y*w+x; let sx=((2*x+1)*sw/(2*w)).min(sw-1); let sy=((2*y+1)*sh/(2*h)).min(sh-1); let s=sy*sw+sx;
            for c in 0..3 {
                if pw==0 {
                    let fs=if fg[s]==NONE {s} else {fg[s] as usize};
                    let bs=if bg[s]==NONE {s} else {bg[s] as usize};
                    f[3*i+c]=source[3*fs+c];b[3*i+c]=source[3*bs+c];
                } else {
                    f[3*i+c]=sample(&old_f,pw,ph,(x as f64+0.5)*pw as f64/w as f64-0.5,(y as f64+0.5)*ph as f64/h as f64-0.5,c) as f32;
                    b[3*i+c]=sample(&old_b,pw,ph,(x as f64+0.5)*pw as f64/w as f64-0.5,(y as f64+0.5)*ph as f64/h as f64-0.5,c) as f32;
                }
                // Anchor exactly observed colours before bounded relaxation.
                if alpha[s]==1.0 {f[3*i+c]=source[3*s+c];}
                if alpha[s]==0.0 {b[3*i+c]=source[3*s+c];}
            }
        }}
        // Release coarser F/B before reduced image or relaxation allocations.
        drop(old_f); drop(old_b);
        let rounds=if w<=32 && h<=32 {24} else {6};
        if w==sw && h==sh {relax(source,alpha,&mut f,&mut b,w,h,rounds,cancel)?;} else {
            let (image,matte)=reduce(source,alpha,sw,sh,w,h,cancel)?;
            relax(&image,&matte,&mut f,&mut b,w,h,rounds,cancel)?;
        }
        old_f=f;old_b=b;pw=w;ph=h;
    }
    Ok((old_f,old_b))
}

// Source-pixel refinement uses actual full-resolution I and alpha, with the
// upsampled F/B estimates only as colour priors. It does not upsample a finished
// proxy correction or a matte. Out-of-SDR solutions are uncertain and abstain.
fn refine(input: Rgb, a: f64, prior_f: Rgb, prior_b: Rgb) -> Option<(Rgb,Rgb)> {
    let z=1.0-a;let lambda=0.02;let aa=a*a+lambda;let bb=z*z+lambda;let ab=a*z;
    let det=aa*bb-ab*ab;let mut f=[0.0;3];let mut b=[0.0;3];
    for c in 0..3 {
        let rf=a*input[c]+lambda*prior_f[c];let rb=z*input[c]+lambda*prior_b[c];
        f[c]=if a==1.0 {input[c]} else {(bb*rf-ab*rb)/det};
        b[c]=if a==0.0 {input[c]} else {(aa*rb-ab*rf)/det};
        if !f[c].is_finite() || !b[c].is_finite() || !(0.0..=1.0).contains(&f[c]) || !(0.0..=1.0).contains(&b[c]) {return None;}
    }
    Some((f,b))
}

fn prepare(source: &[f32], alpha: &[f32], delta: &mut [f32], confidence: &mut [f32],
           w: usize, h: usize, strength: f64, scale: f64, cancel: Cancel) -> Result<(),i32> {
    for y in 0..h {
        poll(cancel)?;
        if source[y*w*3..(y+1)*w*3].iter().chain(alpha[y*w..(y+1)*w].iter())
            .any(|v|!v.is_finite() || !(0.0..=1.0).contains(v)) {return Err(2);}
    }
    for y in 0..h {poll(cancel)?;delta[y*w*3..(y+1)*w*3].fill(0.0);confidence[y*w..(y+1)*w].fill(0.0);}
    if strength==0.0 {return Ok(());}
    let n=w*h; let mut fg=indices(n)?; let mut bg=indices(n)?;
    // Interior depth is measured from non-opaque coverage, not eroded alpha.
    for y in 0..h {poll(cancel)?;for x in 0..w {let i=y*w+x;if alpha[i]<0.98 {bg[i]=i as u32;}}}
    propagate(&mut bg,alpha,w,h,false,cancel)?;
    let inner=(8.0*scale).ceil().max(1.0) as usize;
    let radius=(32.0*scale).ceil().max(2.0) as usize;
    let mut fg_count=0;let mut bg_count=0;
    for y in 0..h {poll(cancel)?;for x in 0..w {let i=y*w+x;
        if alpha[i]>=0.98 && bg[i]!=NONE && distance(i,bg[i],w)>=inner {fg[i]=i as u32;fg_count+=1;}
        bg[i]=if alpha[i]<=0.02 {bg_count+=1;i as u32} else {NONE};
    }}
    if fg_count==0 || bg_count==0 {return Ok(());}
    propagate(&mut fg,alpha,w,h,true,cancel)?;propagate(&mut bg,alpha,w,h,false,cancel)?;
    let (f,b)=solve(source,alpha,&fg,&bg,w,h,cancel)?;
    let (aw,ah)=analysis_shape(w,h);
    for y in 0..h {poll(cancel)?;for x in 0..w {
        let i=y*w+x;let a=alpha[i] as f64;
        let fd=distance(i,fg[i],w);let bd=distance(i,bg[i],w);
        if a<0.05 || fd>radius || bd>radius {continue;}
        let (prior,fvar)=match seed_stats(source,alpha,fg[i],w,h,true) {Some(v)=>v,None=>continue};
        let (back,bvar)=match seed_stats(source,alpha,bg[i],w,h,false) {Some(v)=>v,None=>continue};
        if fvar>0.055 || bvar>0.035 {continue;}
        let pc=chroma(prior);let bc=chroma(back);let pn=norm(pc);let bn=norm(bc);
        if bn<0.035 {continue;}
        // Similar genuine foreground hue is observationally ambiguous, not spill.
        if pn>0.025 && dot(pc,bc)/(pn*bn)>0.90 {continue;}
        let input=rgb(source,i);let mut prior_f=[0.0;3];let mut prior_b=[0.0;3];
        for c in 0..3 {
            let px=(x as f64+0.5)*aw as f64/w as f64-0.5;let py=(y as f64+0.5)*ah as f64/h as f64-0.5;
            prior_f[c]=sample(&f,aw,ah,px,py,c);prior_b[c]=sample(&b,aw,ah,px,py,c);
        }
        let (estimated_f,estimated_b)=match refine(input,a,prior_f,prior_b) {Some(v)=>v,None=>continue};
        let residual=norm(sub(input,[a*estimated_f[0]+(1.0-a)*estimated_b[0],
            a*estimated_f[1]+(1.0-a)*estimated_b[1],a*estimated_f[2]+(1.0-a)*estimated_b[2]]));
        // At opacity one the matting equation cannot identify B. The reflected
        // branch instead uses real local background seed agreement below.
        if residual>0.04 || (a<0.98 && norm(sub(estimated_b,back))>0.15) {continue;}
        let mut trust=(1.0-fade(0.015,0.035,bvar))*(1.0-fade(0.025,0.055,fvar))
            *(1.0-fade(0.01,0.04,residual))*(1.0-fade(radius as f64*0.5,radius as f64,bd as f64));
        let change;
        if a<0.98 {
            if !coherent_path(source,alpha,i,fg[i],w,false) || norm(sub(estimated_f,prior))>0.20 {continue;}
            let axis=mul(bc,1.0/bn);let excess=dot(chroma(sub(input,estimated_f)),axis);
            if excess<=0.002 || excess>0.30 {continue;}
            change=mul(axis,-excess);
            trust*=fade(0.05,0.20,a)*fade(0.002,0.015,excess);
        } else {
            // Reflected opaque spill is not identifiable from the compositing
            // equation. This is a separate, narrower, original edge heuristic.
            let narrow=(8.0*scale).ceil().max(1.0);
            if bd as f64>narrow || fd==0 || !coherent_path(source,alpha,i,fg[i],w,true)
                || (dot(input,LUMA)-dot(prior,LUMA)).abs()>0.08 {continue;}
            let axis=sub(bc,pc);let axis2=dot(axis,axis);if axis2<0.0025 {continue;}
            let excess=chroma(sub(input,prior));let amount=dot(excess,axis)/axis2;
            if amount<=0.01 || amount>0.30 {continue;}
            let aligned=mul(axis,amount);let orthogonal=norm(sub(excess,aligned));
            if orthogonal>0.02 || orthogonal>0.30*norm(aligned)+0.002 {continue;}
            change=mul(aligned,-1.0);
            trust*=0.5*fade(0.01,0.04,amount)*(1.0-fade(narrow*0.5,narrow,bd as f64))
                *(1.0-fade(0.005,0.02,orthogonal));
        }
        if trust<=0.0 {continue;}
        for c in 0..3 {delta[3*i+c]=change[c] as f32;}
        confidence[i]=(strength*trust) as f32;
    }}
    poll(cancel)
}

#[no_mangle]
pub extern "C" fn lrt_spill_removal_abi() -> u32 {1}

/// Status: 0 success, 1 shape/parameter, 2 non-finite/out-of-SDR input,
/// 3 cancelled, 4 memory admission/allocation, 5 numerical failure.
/// Pointers must be valid, correctly sized, non-overlapping and exclusively
/// owned as required. Outputs are unpublished scratch until return status 0.
#[no_mangle]
pub unsafe extern "C" fn lrt_spill_removal_prepare(
    source: *const f32, alpha: *const f32, delta: *mut f32, confidence: *mut f32,
    w: usize, h: usize, strength: f32, render_scale: f32, cancel: Cancel) -> i32 {
    if source.is_null() || alpha.is_null() || delta.is_null() || confidence.is_null() {return 1;}
    let n=match w.checked_mul(h) {Some(n) if n>0 && n<=MAX_PIXELS && w<=65536 && h<=65536=>n,_=>return 1};
    if !strength.is_finite() || !(0.0..=1.0).contains(&strength) || !render_scale.is_finite()
        || !(0.000001..=1.0).contains(&render_scale) {return 1;}
    if n.checked_mul(64).and_then(|v|v.checked_add(SCRATCH_BYTES)).map_or(true,|v|v>MAX_BYTES) {return 4;}
    let source=slice::from_raw_parts(source,3*n);let alpha=slice::from_raw_parts(alpha,n);
    let delta=slice::from_raw_parts_mut(delta,3*n);let confidence=slice::from_raw_parts_mut(confidence,n);
    match prepare(source,alpha,delta,confidence,w,h,strength as f64,render_scale as f64,cancel) {Ok(())=>0,Err(code)=>code}
}

#[cfg(test)]
mod tests {
    use super::*;
    // Authored contract fixtures only. No compiler or test was run.
    #[test] fn neutral_is_exact_and_does_not_change_alpha() {
        let source=[0.2f32,0.4,0.7];let alpha=[0.5f32];let before=alpha;
        let mut d=[1.0;3];let mut q=[1.0];
        assert_eq!(prepare(&source,&alpha,&mut d,&mut q,1,1,0.0,1.0,None),Ok(()));
        assert_eq!(d,[0.0;3]);assert_eq!(q,[0.0]);assert_eq!(alpha,before);
    }
    #[test] fn no_real_seed_support_is_neutral() {
        let source=[0.2f32;27];let alpha=[0.5f32;9];let mut d=[1.0;27];let mut q=[1.0;9];
        assert_eq!(prepare(&source,&alpha,&mut d,&mut q,3,3,1.0,1.0,None),Ok(()));
        assert_eq!(d,[0.0;27]);assert_eq!(q,[0.0;9]);
    }
    #[test] fn reject_nonfinite_and_hdr_before_output() {
        for value in [f32::NAN,f32::INFINITY,-0.01,1.01] {
            let source=[value,0.2,0.3];let alpha=[0.5];let mut d=[7.0;3];let mut q=[7.0];
            assert_eq!(prepare(&source,&alpha,&mut d,&mut q,1,1,1.0,1.0,None),Err(2));
            assert_eq!(d,[7.0;3]);assert_eq!(q,[7.0]);
        }
    }
    extern "C" fn cancelled() -> i32 {1}
    #[test] fn cancellation_does_not_publish_scratch() {
        let source=[0.2;3];let alpha=[0.5];let mut d=[7.0;3];let mut q=[7.0];
        assert_eq!(prepare(&source,&alpha,&mut d,&mut q,1,1,1.0,1.0,Some(cancelled)),Err(3));
        assert_eq!(d,[7.0;3]);assert_eq!(q,[7.0]);
    }
    #[test] fn one_coarse_row_polls_inside_its_source_scan() {
        // Authored, UNRUN. Row-only polling would finish this reduction before
        // observing the second callback's cancellation request.
        use std::sync::atomic::{AtomicUsize,Ordering};
        static POLLS: AtomicUsize=AtomicUsize::new(0);
        extern "C" fn cancel_after_first_poll() -> i32 {
            if POLLS.fetch_add(1,Ordering::SeqCst)>0 {1} else {0}
        }
        POLLS.store(0,Ordering::SeqCst);
        let source=vec![0.2f32;3*8192];let alpha=vec![0.5f32;8192];
        assert_eq!(reduce(&source,&alpha,8192,1,1,1,Some(cancel_after_first_poll)),Err(3));
        assert_eq!(POLLS.load(Ordering::SeqCst),2);
    }
    #[test] fn colour_projection_preserves_luminance() {
        let d=chroma([0.1,0.4,-0.2]);assert!(dot(d,LUMA).abs()<1e-12);
    }
    #[test] fn joint_estimator_reconstructs_known_flat_composite() {
        let w=65;let h=5;let n=w*h;let mut source=vec![0.0f32;3*n];let mut alpha=vec![0.0f32;n];
        let fg_colour=[0.3,0.2,0.1];let bg_colour=[0.05,0.65,0.05];
        let mut fg=vec![NONE;n];let mut bg=vec![NONE;n];
        for y in 0..h {for x in 0..w {let i=y*w+x;let a=if x<24 {1.0} else if x>40 {0.0} else {(41-x) as f32/18.0};alpha[i]=a;
            for c in 0..3 {source[3*i+c]=a*fg_colour[c]+(1.0-a)*bg_colour[c];}
            if x<24 {fg[i]=i as u32;}if x>40 {bg[i]=i as u32;}
        }}
        propagate(&mut fg,&alpha,w,h,false,None).unwrap();propagate(&mut bg,&alpha,w,h,false,None).unwrap();
        let (f,b)=solve(&source,&alpha,&fg,&bg,w,h,None).unwrap();
        let i=2*w+32;let a=alpha[i];
        for c in 0..3 {assert!((a*f[3*i+c]+(1.0-a)*b[3*i+c]-source[3*i+c]).abs()<0.035);}
        assert!(f[3*i+1]<source[3*i+1]);
    }
    #[test] fn reflected_edge_has_a_nonzero_guarded_path() {
        let (w,h)=(48,9);let n=w*h;let mut source=vec![0.0f32;3*n];let mut alpha=vec![0.0f32;n];
        let prior=[0.30,0.30,0.30];let back=[0.10,0.70,0.10];let axis=chroma(sub(back,prior));
        for y in 0..h {for x in 0..w {let i=y*w+x;
            alpha[i]=if x<16 {0.0} else {1.0};
            let amount=if (16..23).contains(&x) {0.12*(23-x) as f64/7.0} else {0.0};
            for c in 0..3 {source[3*i+c]=if x<16 {back[c] as f32} else {(prior[c]+amount*axis[c]) as f32};}
        }}
        let mut d=vec![0.0;3*n];let mut q=vec![0.0;n];
        assert_eq!(prepare(&source,&alpha,&mut d,&mut q,w,h,1.0,1.0,None),Ok(()));
        let i=4*w+17;assert!(q[i]>0.0);assert!(d[3*i+1]<0.0);
        assert!(dot(rgb(&d,i),LUMA).abs()<1e-7);
        assert_eq!(q[4*w+35],0.0); // no deep opaque correction
        assert_eq!(alpha[4*w+17],1.0); // no coverage erosion
    }
    #[test] fn genuine_matching_colour_foreground_abstains() {
        let (w,h)=(48,9);let n=w*h;let mut source=vec![0.0f32;3*n];let mut alpha=vec![0.0f32;n];
        for y in 0..h {for x in 0..w {let i=y*w+x;alpha[i]=if x<16 {0.0} else {1.0};
            let c=if x<16 {[0.1,0.7,0.1]} else {[0.2,0.6,0.2]};source[3*i..3*i+3].copy_from_slice(&c);
        }}
        let mut d=vec![1.0;3*n];let mut q=vec![1.0;n];
        assert_eq!(prepare(&source,&alpha,&mut d,&mut q,w,h,1.0,1.0,None),Ok(()));
        assert!(q.iter().all(|v|*v==0.0));assert!(d.iter().all(|v|*v==0.0));
    }
    #[test] fn mixed_edge_emits_colour_delta_not_alpha() {
        let (w,h)=(48,9);let n=w*h;let mut source=vec![0.0f32;3*n];let mut alpha=vec![0.0f32;n];
        for y in 0..h {for x in 0..w {let i=y*w+x;
            let a=if x<16 {0.0} else if x>=24 {1.0} else {(x-15) as f32/9.0};alpha[i]=a;
            for c in 0..3 {source[3*i+c]=a*[0.4,0.3,0.2][c]+(1.0-a)*[0.1,0.7,0.1][c];}
        }}
        let before=alpha.clone();let mut d=vec![0.0;3*n];let mut q=vec![0.0;n];
        assert_eq!(prepare(&source,&alpha,&mut d,&mut q,w,h,1.0,1.0,None),Ok(()));
        assert!((16..24).any(|x|q[4*w+x]>0.0 && d[3*(4*w+x)+1]<0.0));
        assert_eq!(alpha,before);
    }
}
