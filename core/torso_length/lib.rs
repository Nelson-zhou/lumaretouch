// SPDX-License-Identifier: GPL-3.0-or-later
//! Original, dependency-free upper-body LENGTH field. AUTHORED / UNRUN.
//! This kernel owns no RGB, masks, model inference, face sampler or allocation.
//! Positive amount translates shoulders + the complete head upward, hips fixed.
use std::slice;

const STATE_LEN: usize = 11;
const SUPPORT_LEN: usize = 18;
const FACTS_LEN: usize = 16;
const MAX_POINTS: usize = 1_048_576;
const GAIN: f64 = 0.08;
const MAX_DISPLACEMENT: f64 = 128.0;
const MAX_GRADIENT: f64 = 0.45;
const STEP_TOLERANCE: f64 = 1e-9;
const RESIDUAL_TOLERANCE: f64 = 1e-7;

// Codes: 1 malformed input/state; 2 amount; 4 visibility/crop; 5 posture;
// 6 support/gradient/displacement; 8 image domain; 9 inverse/Jacobian.
#[derive(Clone, Copy, Debug)]
struct State([f64; STATE_LEN]);

fn smooth(t: f64) -> (f64, f64) {
    if t <= 0.0 { return (0.0, 0.0); }
    if t >= 1.0 { return (1.0, 0.0); }
    (t*t*t*(10.0+t*(-15.0+6.0*t)), 30.0*t*t*(1.0-t)*(1.0-t))
}

impl State {
    fn gradient_bound(self) -> f64 {
        let s = self.0;
        let mx = (s[1]-s[0]).min(s[3]-s[2]);
        let my = (s[5]-s[4]).min(s[7]-s[6]);
        1.875*s[8].abs()*(1.0/mx).hypot(1.0/my)
    }

    fn validate(self) -> Result<(), i32> {
        let s = self.0;
        if s.iter().any(|v| !v.is_finite())
            || !(2.0..=1_000_000.0).contains(&s[9])
            || !(2.0..=1_000_000.0).contains(&s[10])
            || s[9].fract() != 0.0 || s[10].fract() != 0.0
            || !(s[0]<s[1] && s[1]<s[2] && s[2]<s[3]
                 && s[4]<s[5] && s[5]<s[6] && s[6]<s[7]) {
            return Err(1);
        }
        if s[0]<1.0 || s[3]>s[9]-2.0 || s[4]<1.0 || s[7]>s[10]-2.0 {
            return Err(8);
        }
        if s[7]-s[6]<64.0 || s[8].abs()>GAIN*(s[7]-s[6])
            || s[8].abs()>MAX_DISPLACEMENT || self.gradient_bound()>MAX_GRADIENT {
            return Err(6);
        }
        Ok(())
    }

    // Forward displacement dy, partial dy/partial x, partial dy/partial y.
    fn forward(self, x: f64, y: f64) -> (f64, f64, f64) {
        let s = self.0;
        if x<=s[0] || x>=s[3] || y<=s[4] || y>=s[7] || s[8]==0.0 {
            return (0.0, 0.0, 0.0);
        }
        let (wx, dx) = if x<s[1] {
            let (v,d)=smooth((x-s[0])/(s[1]-s[0])); (v,d/(s[1]-s[0]))
        } else if x>s[2] {
            let (v,d)=smooth((s[3]-x)/(s[3]-s[2])); (v,-d/(s[3]-s[2]))
        } else { (1.0,0.0) };
        let (by, dy) = if y<s[5] {
            let (v,d)=smooth((y-s[4])/(s[5]-s[4])); (v,d/(s[5]-s[4]))
        } else if y>s[6] {
            let (v,d)=smooth((s[7]-y)/(s[7]-s[6])); (v,-d/(s[7]-s[6]))
        } else { (1.0,0.0) };
        (s[8]*wx*by, s[8]*dx*by, s[8]*wx*dy)
    }

    fn in_domain(self, x: f64, y: f64) -> bool {
        x.is_finite() && y.is_finite() && x>=0.0 && x<=self.0[9]-1.0
            && y>=0.0 && y<=self.0[10]-1.0
    }

    fn inverse(self, x: f64, target_y: f64) -> Result<(f64, f64), i32> {
        if !self.in_domain(x,target_y) { return Err(8); }
        let mut source_y=target_y;
        let mut converged=false;
        for _ in 0..64 {
            let (d,_,_)=self.forward(x,source_y);
            let next=target_y-d;
            if !next.is_finite() { return Err(9); }
            if (next-source_y).abs()<=STEP_TOLERANCE {
                source_y=next; converged=true; break;
            }
            source_y=next;
        }
        let (d,_,dy)=self.forward(x,source_y);
        let determinant=1.0+dy;
        let bound=self.gradient_bound();
        if !converged || (source_y+d-target_y).abs()>RESIDUAL_TOLERANCE
            || !determinant.is_finite()
            || determinant<1.0-bound-1e-12 || determinant>1.0+bound+1e-12
            || (target_y-source_y).abs()>self.0[8].abs()+RESIDUAL_TOLERANCE {
            return Err(9);
        }
        // Domain failures are explicit, never made into plausible edge pixels.
        if !self.in_domain(x,source_y) { return Err(8); }
        Ok((target_y-source_y,1.0/determinant))
    }

    fn facts(self) -> [f64; FACTS_LEN] {
        let s=self.0; let bound=self.gradient_bound();
        [s[0],s[4],s[3],s[7], s[1],s[5],s[2],s[6],
         s[8].abs(),bound,1.0-bound,1.0+bound,s[8],s[6],s[7],RESIDUAL_TOLERANCE]
    }
}

fn read_state(raw: &[f64]) -> Result<State,i32> {
    if raw.len()!=STATE_LEN { return Err(1); }
    let mut s=[0.0;STATE_LEN]; s.copy_from_slice(raw);
    let state=State(s); state.validate()?; Ok(state)
}

// This checks address arithmetic/alignment/aliasing, not whether the caller
// actually owns a live allocation. That remains an explicit unsafe C contract.
fn disjoint_buffers(buffers: &[(usize,usize)]) -> bool {
    for (i,&(address,length)) in buffers.iter().enumerate() {
        if address==0 || address%std::mem::align_of::<f64>()!=0 { return false; }
        let bytes=match length.checked_mul(std::mem::size_of::<f64>()) { Some(n)=>n,None=>return false };
        if bytes>isize::MAX as usize { return false; }
        let end=match address.checked_add(bytes) { Some(n)=>n,None=>return false };
        for &(other_address,other_length) in &buffers[..i] {
            let other_bytes=match other_length.checked_mul(std::mem::size_of::<f64>()) { Some(n)=>n,None=>return false };
            let other_end=match other_address.checked_add(other_bytes) { Some(n)=>n,None=>return false };
            if bytes!=0 && other_bytes!=0 && address<other_end && other_address<end { return false; }
        }
    }
    true
}

fn prepare(points: &[f64], amount: f64, support: &[f64], w: f64, h: f64) -> Result<State,i32> {
    if points.len()!=165 || support.len()!=SUPPORT_LEN
        || points.iter().chain(support).any(|v| !v.is_finite())
        || !w.is_finite() || !h.is_finite()
        || !(2.0..=1_000_000.0).contains(&w) || !(2.0..=1_000_000.0).contains(&h)
        || w.fract()!=0.0 || h.fract()!=0.0 { return Err(1); }
    if !amount.is_finite() || !(-1.0..=1.0).contains(&amount) { return Err(2); }
    if support.iter().any(|n| *n<=0.0 || *n>=1.0) { return Err(6); }
    let p=|i: usize| (points[i*5]*(w-1.0),points[i*5+1]*(h-1.0));
    for i in 0..25 {
        let q=&points[i*5..i*5+5];
        if q[0]<=0.0 || q[0]>=1.0 || q[1]<=0.0 || q[1]>=1.0
            || !(0.8..=1.0).contains(&q[3]) || !(0.8..=1.0).contains(&q[4]) {
            return Err(4);
        }
    }
    let shoulder_y=p(11).1.max(p(12).1);
    let hip_y=p(23).1.min(p(24).1);
    let height=hip_y-shoulder_y;
    if height<64.0 { return Err(5); }
    for (a,b) in [(11,23),(12,24)] {
        let (ax,ay)=p(a); let (bx,by)=p(b); let dy=by-ay;
        if dy<64.0 || (bx-ax).abs()>0.35*dy
            || (points[b*5+2]-points[a*5+2]).abs()*(w-1.0)>0.35*dy { return Err(5); }
    }
    for (a,b) in [(11,12),(23,24)] {
        let (ax,ay)=p(a); let (bx,by)=p(b); let dx=(bx-ax).abs();
        if dx<32.0 || (by-ay).abs()>0.25*dx
            || (points[b*5+2]-points[a*5+2]).abs()*(w-1.0)>0.35*dx { return Err(5); }
    }
    let s=State([support[0]*(w-1.0),support[1]*(w-1.0),support[2]*(w-1.0),
        support[3]*(w-1.0),support[4]*(h-1.0),support[5]*(h-1.0),
        shoulder_y,hip_y,-amount*GAIN*height,w,h]);
    s.validate()?;
    for i in 0..25 {
        let (x,y)=p(i);
        if x<=s.0[1] || x>=s.0[2] || y<=s.0[5] || y>h-2.0 { return Err(6); }
    }
    let groups: [&[usize];3]=[&[0,1,2,3,4,5,6,7,8,9,10],&[11,13,15,17,19,21],&[12,14,16,18,20,22]];
    for (index, ids) in groups.iter().enumerate() {
        let raw=&support[6+index*4..10+index*4];
        let b=[raw[0]*(w-1.0),raw[1]*(h-1.0),raw[2]*(w-1.0),raw[3]*(h-1.0)];
        if !(s.0[1]<b[0] && b[0]<b[2] && b[2]<s.0[2]
            && s.0[5]<b[1] && b[1]<b[3] && b[3]<=h-2.0) { return Err(6); }
        if index==0 && (b[3]>=shoulder_y || b[1]+s.0[8]<1.0 || b[3]+s.0[8]>h-2.0) { return Err(8); }
        for &i in *ids {
            let (x,y)=p(i);
            if x<=b[0] || x>=b[2] || y<=b[1] || y>=b[3] { return Err(6); }
        }
    }
    Ok(s)
}

#[no_mangle]
pub extern "C" fn lrt_torso_length_abi() -> u32 { 1 }

/// All pointers must be valid, aligned, length-matched and mutually disjoint.
/// Never pass application-owned live arrays; the bridge snapshots input buffers.
#[no_mangle]
pub unsafe extern "C" fn lrt_torso_length_prepare(
    points: *const f64, points_len: usize, amounts: *const f64, amounts_len: usize,
    support: *const f64, support_len: usize, w: f64, h: f64,
    out: *mut f64, out_len: usize,
) -> i32 {
    if points.is_null() || amounts.is_null() || support.is_null() || out.is_null()
        || points_len!=165 || amounts_len!=1 || support_len!=SUPPORT_LEN || out_len!=STATE_LEN { return 1; }
    if !disjoint_buffers(&[(points as usize,points_len),(amounts as usize,amounts_len),
        (support as usize,support_len),(out as usize,out_len)]) { return 1; }
    match prepare(slice::from_raw_parts(points,points_len),*amounts,
                  slice::from_raw_parts(support,support_len),w,h) {
        Ok(s) => { slice::from_raw_parts_mut(out,out_len).copy_from_slice(&s.0); 0 },
        Err(code) => code,
    }
}

#[no_mangle]
pub unsafe extern "C" fn lrt_torso_length_describe(
    state: *const f64, state_len: usize, out: *mut f64, out_len: usize,
) -> i32 {
    if state.is_null() || out.is_null() || state_len!=STATE_LEN || out_len!=FACTS_LEN { return 1; }
    if !disjoint_buffers(&[(state as usize,state_len),(out as usize,out_len)]) { return 1; }
    match read_state(slice::from_raw_parts(state,state_len)) {
        Ok(s) => { slice::from_raw_parts_mut(out,out_len).copy_from_slice(&s.facts()); 0 },
        Err(code) => code,
    }
}

#[no_mangle]
pub unsafe extern "C" fn lrt_torso_length_evaluate(
    state: *const f64, state_len: usize, xy: *const f64, xy_len: usize, count: usize,
    out: *mut f64, out_len: usize, jac: *mut f64, jac_len: usize,
) -> i32 {
    if state.is_null() || xy.is_null() || out.is_null() || jac.is_null()
        || state_len!=STATE_LEN || count>MAX_POINTS || xy_len!=count*2
        || out_len!=count*2 || jac_len!=count { return 1; }
    if !disjoint_buffers(&[(state as usize,state_len),(xy as usize,xy_len),
        (out as usize,out_len),(jac as usize,jac_len)]) { return 1; }
    let state=match read_state(slice::from_raw_parts(state,state_len)) { Ok(s)=>s,Err(c)=>return c };
    let input=slice::from_raw_parts(xy,xy_len);
    if input.iter().any(|v| !v.is_finite()) { return 1; }
    // Admission pass leaves BOTH output buffers untouched on any refusal.
    // No allocations, mutable inputs, callbacks or fallible work intervene.
    for i in 0..count {
        if let Err(code)=state.inverse(input[i*2],input[i*2+1]) { return code; }
    }
    let output=slice::from_raw_parts_mut(out,out_len);
    let determinants=slice::from_raw_parts_mut(jac,jac_len);
    for i in 0..count {
        match state.inverse(input[i*2],input[i*2+1]) {
            Ok((dy,j)) => { output[i*2]=0.0; output[i*2+1]=dy; determinants[i]=j; },
            Err(code) => return code,
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    fn state(amount: f64) -> State {
        State([10.0,410.0,690.0,1090.0,10.0,410.0,650.0,1150.0,-amount*40.0,1201.0,1601.0])
    }
    #[test]
    fn signed_length_moves_shoulders_and_head_but_not_hips() {
        for amount in [-1.0,-0.125,0.0,0.125,1.0] {
            let s=state(amount); s.validate().unwrap();
            for y in [440.0,500.0,650.0] { assert_eq!(s.forward(550.0,y).0,-amount*40.0); }
            assert_eq!(s.forward(550.0,1150.0).0,0.0);
            assert_eq!(s.forward(550.0,1200.0).0,0.0);
            assert_eq!(1150.0-(650.0+s.forward(550.0,650.0).0),500.0+amount*40.0);
        }
    }
    #[test]
    fn inverse_off_grid_both_signs_and_analytic_determinant() {
        for amount in [-1.0,1.0] {
            let s=state(amount); s.validate().unwrap();
            for (x,y) in [(215.37,254.21),(550.37,812.21),(932.7,1074.13)] {
                let (d,j)=s.inverse(x,y).unwrap();
                assert!((y-d+s.forward(x,y-d).0-y).abs()<RESIDUAL_TOLERANCE);
                let eps=1e-4; let (d2,_)=s.inverse(x,y+eps).unwrap();
                assert!((j-((y+eps-d2)-(y-d))/eps).abs()<1e-5);
            }
        }
    }
    #[test]
    fn fixed_source_edges_and_both_sign_domain_preservation() {
        for amount in [-1.0,1.0] {
            let s=state(amount);
            for (x,y) in [(0.0,0.0),(1200.0,1600.0),(550.0,10.0),(550.0,1150.0),(10.0,500.0),(1090.0,500.0)] {
                assert_eq!(s.inverse(x,y).unwrap(),(0.0,1.0));
            }
            assert_eq!(s.inverse(-0.01,500.0),Err(8));
            assert_eq!(s.inverse(550.0,1600.01),Err(8));
        }
    }
    #[test]
    fn refuse_narrow_transition_without_attenuating_requested_amount() {
        let mut s=state(1.0); s.0[5]=20.0;
        assert_eq!(s.validate(),Err(6));
        let mut s=state(-1.0); s.0[0]=0.0;
        assert_eq!(s.validate(),Err(8));
        let mut s=state(1.0); s.0[8]=129.0;
        assert_eq!(s.validate(),Err(6));
    }
    #[test]
    fn raw_abi_refuses_alias_and_keeps_outputs_unchanged_on_late_refusal() {
        let s=state(1.0).0;
        let mut xy=[550.0,500.0,550.0,1600.01];
        let mut out=[73.0;4]; let mut jac=[91.0;2];
        let code=unsafe { lrt_torso_length_evaluate(s.as_ptr(),11,xy.as_ptr(),4,2,
            out.as_mut_ptr(),4,jac.as_mut_ptr(),2) };
        assert_eq!(code,8); assert_eq!(out,[73.0;4]); assert_eq!(jac,[91.0;2]);
        xy[3]=900.0;
        let code=unsafe { lrt_torso_length_evaluate(s.as_ptr(),11,xy.as_ptr(),4,2,
            xy.as_mut_ptr(),4,jac.as_mut_ptr(),2) };
        assert_eq!(code,1); assert_eq!(jac,[91.0;2]);
    }
    #[test]
    fn raw_abi_checks_alignment_lengths_and_address_overflow_before_slices() {
        assert!(!disjoint_buffers(&[(1,11)]));
        assert!(!disjoint_buffers(&[(usize::MAX-7,11)]));
        let s=state(1.0).0;let mut out=[19.0;16];
        let code=unsafe { lrt_torso_length_describe(s.as_ptr(),10,out.as_mut_ptr(),16) };
        assert_eq!(code,1);assert_eq!(out,[19.0;16]);
    }
}
