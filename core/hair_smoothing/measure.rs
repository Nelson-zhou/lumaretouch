// SPDX-License-Identifier: GPL-3.0-or-later
//! Original bounded, symmetric, source-direction luminance regularization.
use crate::contract::{allocate, poll, Cancel, Plan, Result, CONTEXT, INPUT, MAX_LOG_GAIN, NUMERICS};
use crate::direction::{self, Direction};

pub(crate) struct Measured {
    pub gain: Vec<f32>, pub eligible: Vec<u8>, pub counts: [u64; 4], pub metrics: [f64; 2],
}

/// Integer-only support integral is exact at <=32 MP. It is not a signal
/// integral and cannot carry source texture from another owner into a tensor.
fn admitted(context_weight: &[f32], protect: &[u8], plan: Plan, cancel: Cancel,
    context: *mut std::ffi::c_void) -> Result<(Vec<bool>, Vec<u8>)> {
    let (w, h) = (plan.width, plan.height); let stride = w+1;
    let mut support = allocate(plan.pixels, false)?;
    let mut blocked = allocate((w+1)*(h+1), 0_u32)?;
    for y in 0..h {
        poll(cancel, context)?; let mut row = 0_u32;
        for x in 0..w {
            let i=y*w+x; support[i]=context_weight[i]>0.0 && protect[i]==0;
            row += u32::from(!support[i]);
            blocked[(y+1)*stride+x+1] = blocked[y*stride+x+1]+row;
        }
    }
    let mut eligible = allocate(plan.pixels, 0_u8)?;
    let r=plan.halo;
    if w <= 2*r || h <= 2*r { return Ok((support, eligible)); }
    for y in r..h-r {
        poll(cancel, context)?;
        for x in r..w-r {
            let (x0,y0,x1,y1)=(x-r,y-r,x+r+1,y+r+1);
            // Reorder subtraction to avoid unsigned intermediate underflow.
            let left = blocked[y1*stride+x1] as u64 + blocked[y0*stride+x0] as u64;
            let right = blocked[y0*stride+x1] as u64 + blocked[y1*stride+x0] as u64;
            if left == right { eligible[y*w+x]=1; }
        }
    }
    Ok((support, eligible))
}

fn photometric(rgb: &[f32], log_y: &[f32], i: usize) -> bool {
    // Conservative numerical heuristics, NOT a physical highlight classifier.
    let y=(log_y[i] as f64).exp();
    y >= 0.004 && y <= 0.82 && rgb[3*i..3*i+3].iter().all(|&v| v<0.985)
}

fn sample(x: f64, y: f64, log_y: &[f32], rgb: &[f32], directions: &[Direction],
    support: &[bool], direction: Direction, plan: Plan) -> Option<f64> {
    if x<0.0 || y<0.0 || x.ceil()>=plan.width as f64 || y.ceil()>=plan.height as f64 { return None; }
    let (ix,iy)=(x.floor() as usize,y.floor() as usize);
    let (fx,fy)=(x-ix as f64,y-iy as f64);
    let taps=[(ix,iy,(1.0-fx)*(1.0-fy)),(ix+1,iy,fx*(1.0-fy)),
        (ix,iy+1,(1.0-fx)*fy),(ix+1,iy+1,fx*fy)];
    let mut value=0.0;
    for (tx,ty,weight) in taps {
        // Even zero-weight neighboring taps must be supported. The frozen
        // square halo already admits these conservative extra dependencies.
        if tx>=plan.width || ty>=plan.height { return None; }
        let i=ty*plan.width+tx; let d=directions[i];
        let dot=(d.x as f64*direction.x as f64+d.y as f64*direction.y as f64).abs();
        if !support[i] || d.coherence<0.50 || dot<0.94 || !photometric(rgb,log_y,i) { return None; }
        value+=weight*log_y[i] as f64;
    }
    value.is_finite().then_some(value)
}

pub(crate) fn run(rgb: &[f32], target: &[f32], context_weight: &[f32], protect: &[u8],
    scale: f64, plan: Plan, cancel: Cancel, context: *mut std::ffi::c_void) -> Result<Measured> {
    for y in 0..plan.height {
        poll(cancel,context)?;
        for x in 0..plan.width {
            let i=y*plan.width+x;
            if !rgb[3*i..3*i+3].iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v))
                || !target[i].is_finite() || !(0.0..=1.0).contains(&target[i])
                || !context_weight[i].is_finite() || !(0.0..=1.0).contains(&context_weight[i]) || protect[i]>1 {
                return Err(INPUT);
            }
            if target[i]>0.0 && context_weight[i]<=0.0 && protect[i]==0 { return Err(INPUT); }
        }
    }
    let (support,mut eligible)=admitted(context_weight,protect,plan,cancel,context)?;
    let mut counts=[0_u64;4];
    for i in 0..plan.pixels {
        if target[i]<=0.0 || protect[i]!=0 { eligible[i]=0; continue; }
        if eligible[i]!=0 { counts[0]+=1; } else { counts[1]+=1; }
    }
    if counts[0]==0 { return Err(CONTEXT); }
    let log_y=direction::log_luminance(rgb,plan,cancel,context)?;
    let directions=direction::measure(&log_y,&support,plan,cancel,context)?;
    let mut gain=allocate(plan.pixels,0.0_f32)?;
    let mut metrics=[0.0_f64;2];
    for y in 0..plan.height {
        poll(cancel,context)?;
        for x in 0..plan.width {
            let i=y*plan.width+x;
            if eligible[i]==0 { continue; }
            let direction=directions[i];
            if direction.coherence<0.60 || !photometric(rgb,&log_y,i) { continue; }
            counts[2]+=1;
            metrics[1]=metrics[1].max(direction.coherence as f64);
            let center=log_y[i] as f64;
            let mut weighted=0.0; let mut total=0.0; let mut pairs=0;
            let mut veto=false;
            for step in 1..=4 {
                let distance=0.5*scale*step as f64;
                let dx=distance*direction.x as f64; let dy=distance*direction.y as f64;
                let Some(a)=sample(x as f64+dx,y as f64+dy,&log_y,rgb,&directions,&support,direction,plan) else { veto=true; break; };
                let Some(b)=sample(x as f64-dx,y as f64-dy,&log_y,rgb,&directions,&support,direction,plan) else { veto=true; break; };
                let residual=(a-center).abs().max((b-center).abs());
                // A symmetric pair is wholly rejected on either strong edge.
                if residual>=0.18 || (a-b).abs()>=0.24 { veto=true; break; }
                let u=residual/0.18;
                let robust=(1.0-u*u).powi(2);
                let weight=(-0.5*(distance/scale).powi(2)).exp()*robust;
                if weight>1.0e-4 { weighted+=weight*0.5*(a+b); total+=weight; pairs+=1; }
            }
            if veto || pairs<3 || total<=1.0e-6 { continue; }
            let residual=weighted/total-center;
            let proposal=(0.45*direction.coherence as f64*target[i] as f64*residual).clamp(-MAX_LOG_GAIN,MAX_LOG_GAIN);
            if !proposal.is_finite() { return Err(NUMERICS); }
            if proposal.abs()<1.0e-5 { continue; }
            let stored=proposal as f32;
            // Round toward zero when the f32 conversion exceeds the f64 cap.
            let safe=if (stored as f64).abs()>MAX_LOG_GAIN { f32::from_bits(stored.to_bits()-1) } else { stored };
            gain[i]=safe; counts[3]+=1; metrics[0]=metrics[0].max((safe as f64).abs());
        }
    }
    poll(cancel,context)?;
    Ok(Measured {gain,eligible,counts,metrics})
}
