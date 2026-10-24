// SPDX-License-Identifier: GPL-3.0-or-later
//! Original measured WHOLE-PERSON WIDTH field. AUTHORED / UNRUN.
//! No RGB, sampling, model inference, hidden silhouette construction or allocation.
//! A complete manual polygon supplies measured extrema; joints only validate evidence.
use std::slice;
const STATE_LEN: usize = 11;
const FACTS_LEN: usize = 16;
const MAX_POINTS: usize = 1_048_576;
const GAIN: f64 = 0.08;
const MAX_GRADIENT: f64 = 0.45;
const STEP_TOLERANCE: f64 = 1e-9;
const RESIDUAL_TOLERANCE: f64 = 1e-7;
#[derive(Clone, Copy, Debug)]
struct State([f64; STATE_LEN]);
fn smooth(t: f64) -> (f64,f64) {
    if t<=0.0 { return (0.0,0.0); }
    if t>=1.0 { return (1.0,0.0); }
    (t*t*t*(10.0+t*(-15.0+6.0*t)),30.0*t*t*(1.0-t)*(1.0-t))
}
fn window(t:f64,a:f64,b:f64,c:f64,d:f64)->(f64,f64) {
    if t<=a || t>=d { return (0.0,0.0); }
    if t<b { let(v,g)=smooth((t-a)/(b-a));(v,g/(b-a)) }
    else if t>c { let(v,g)=smooth((d-t)/(d-c));(v,-g/(d-c)) }
    else {(1.0,0.0)}
}
impl State {
    fn center(self)->f64 {(self.0[1]+self.0[2])*0.5}
    fn radius(self)->f64 {(self.0[0]-self.center()).abs().max((self.0[3]-self.center()).abs())}
    fn max_displacement(self)->f64 {self.0[8].abs()*self.radius()}
    fn gradient_bound(self)->f64 {
        let s=self.0;let mx=(s[1]-s[0]).min(s[3]-s[2]);let my=(s[5]-s[4]).min(s[7]-s[6]);
        s[8].abs()*(1.0+1.875*self.radius()/mx).hypot(1.875*self.radius()/my)
    }
    fn validate(self)->Result<(),i32> {
        let s=self.0;
        if s.iter().any(|v|!v.is_finite()) || !(2.0..=1_000_000.0).contains(&s[9])
            || !(2.0..=1_000_000.0).contains(&s[10]) || s[9].fract()!=0.0 || s[10].fract()!=0.0
            || !(s[0]<s[1] && s[1]<s[2] && s[2]<s[3] && s[4]<s[5] && s[5]<s[6] && s[6]<s[7]) {return Err(1);}
        if s[0]<1.0 || s[3]>s[9]-2.0 || s[4]<1.0 || s[7]>s[10]-2.0 {return Err(8);}
        if s[2]-s[1]<64.0 || s[6]-s[5]<128.0 || s[8].abs()>GAIN
            || self.max_displacement()>4096.0 || self.max_displacement()>0.125*s[9].min(s[10])
            || self.gradient_bound()>MAX_GRADIENT {return Err(6);}
        Ok(())
    }
    // Forward dx and its x/y partials. Width factor on whole measured silhouette = 1+k.
    fn forward(self,x:f64,y:f64)->(f64,f64,f64) {
        let s=self.0;
        if x<=s[0] || x>=s[3] || y<=s[4] || y>=s[7] || s[8]==0.0 {return (0.0,0.0,0.0);}
        let (wx,gx)=window(x,s[0],s[1],s[2],s[3]);let(wy,gy)=window(y,s[4],s[5],s[6],s[7]);
        let q=x-self.center();
        (s[8]*q*wx*wy,s[8]*(wx+q*gx)*wy,s[8]*q*wx*gy)
    }
    fn in_domain(self,x:f64,y:f64)->bool {
        x.is_finite() && y.is_finite() && x>=0.0 && y>=0.0 && x<=self.0[9]-1.0 && y<=self.0[10]-1.0
    }
    fn inverse(self,target_x:f64,y:f64)->Result<(f64,f64),i32> {
        if !self.in_domain(target_x,y) {return Err(8);}
        let mut x=target_x;let mut converged=false;
        for _ in 0..64 {
            let next=target_x-self.forward(x,y).0;
            if !next.is_finite() {return Err(9);}
            if (next-x).abs()<=STEP_TOLERANCE {x=next;converged=true;break;}
            x=next;
        }
        let(d,g,_)=self.forward(x,y);let determinant=1.0+g;let bound=self.gradient_bound();
        if !converged || (x+d-target_x).abs()>RESIDUAL_TOLERANCE
            || !determinant.is_finite() || determinant<1.0-bound-1e-12 || determinant>1.0+bound+1e-12
            || (target_x-x).abs()>self.max_displacement()+RESIDUAL_TOLERANCE {return Err(9);}
        if !self.in_domain(x,y) {return Err(8);}
        Ok((target_x-x,1.0/determinant))
    }
    fn facts(self)->[f64;FACTS_LEN] {
        let s=self.0;let b=self.gradient_bound();
        [s[0],s[4],s[3],s[7],s[1],s[5],s[2],s[6],self.max_displacement(),b,1.0-b,1.0+b,
         1.0+s[8],self.center(),s[2]-s[1],RESIDUAL_TOLERANCE]
    }
}
fn read_state(raw:&[f64])->Result<State,i32> {
    if raw.len()!=STATE_LEN {return Err(1);}
    let mut values=[0.0;STATE_LEN];values.copy_from_slice(raw);let s=State(values);s.validate()?;Ok(s)
}
fn cross(a:(f64,f64),b:(f64,f64),p:(f64,f64))->f64 {(b.0-a.0)*(p.1-a.1)-(b.1-a.1)*(p.0-a.0)}
fn on(a:(f64,f64),b:(f64,f64),p:(f64,f64))->bool {
    cross(a,b,p).abs()<=1e-12 && p.0>=a.0.min(b.0)-1e-12 && p.0<=a.0.max(b.0)+1e-12
        && p.1>=a.1.min(b.1)-1e-12 && p.1<=a.1.max(b.1)+1e-12
}
fn inside(poly:&[f64],p:(f64,f64))->bool {
    let mut yes=false;let n=poly.len()/2;
    for i in 0..n {
        let j=(i+1)%n;let a=(poly[2*i],poly[2*i+1]);let b=(poly[2*j],poly[2*j+1]);
        if on(a,b,p) {return false;}
        if (a.1>p.1)!=(b.1>p.1) && p.0<(b.0-a.0)*(p.1-a.1)/(b.1-a.1)+a.0 {yes=!yes;}
    }
    yes
}
fn prepare(points:&[f64],amount:f64,support:&[f64],w:f64,h:f64)->Result<State,i32> {
    if points.len()!=165 || support.len()<20 || support.len()>260 || support.len()%2!=0
        || points.iter().chain(support).any(|v|!v.is_finite())
        || !w.is_finite() || !h.is_finite() || !(2.0..=1_000_000.0).contains(&w)
        || !(2.0..=1_000_000.0).contains(&h) || w.fract()!=0.0 || h.fract()!=0.0 {return Err(1);}
    if !amount.is_finite() || !(-1.0..=1.0).contains(&amount) {return Err(2);}
    if support.iter().any(|v|*v<=0.0 || *v>=1.0) {return Err(6);}
    let poly=&support[4..];let n=poly.len()/2;
    let vertex=|i:usize| (poly[2*(i%n)],poly[2*(i%n)+1]);
    let(mut l,mut r,mut t,mut b)=(1.0_f64,0.0_f64,1.0_f64,0.0_f64);let mut area=0.0;
    for i in 0..n {
        let a=vertex(i);let q=vertex(i+1);
        l=l.min(a.0);r=r.max(a.0);t=t.min(a.1);b=b.max(a.1);area+=a.0*q.1-q.0*a.1;
        if (a.0-q.0).hypot(a.1-q.1)<=1e-6 || cross(vertex(i+n-1),a,q).abs()<=1e-12 {return Err(6);}
        for j in i+1..n {
            if j==(i+1)%n || i==(j+1)%n {continue;}
            let c=vertex(j);let d=vertex(j+1);
            if (cross(a,q,c)*cross(a,q,d)<0.0 && cross(c,d,a)*cross(c,d,q)<0.0)
                || on(a,q,c) || on(a,q,d) || on(c,d,a) || on(c,d,q) {return Err(6);}
        }
    }
    if area.abs()*0.5<=1e-5 {return Err(6);}
    for i in 0..33 {
        let p=&points[i*5..i*5+5];
        if p[0]<=0.0 || p[0]>=1.0 || p[1]<=0.0 || p[1]>=1.0
            || !(0.8..=1.0).contains(&p[3]) || !(0.8..=1.0).contains(&p[4]) || !inside(poly,(p[0],p[1])) {return Err(4);}
    }
    let s=State([support[0]*(w-1.0),l*(w-1.0),r*(w-1.0),support[2]*(w-1.0),
        support[1]*(h-1.0),t*(h-1.0),b*(h-1.0),support[3]*(h-1.0),-GAIN*amount,w,h]);
    s.validate()?;Ok(s)
}
// Checks alignment, arithmetic and non-aliasing. Caller must still own live buffers.
fn disjoint_buffers(buffers:&[(usize,usize)])->bool {
    for (i,&(address,length)) in buffers.iter().enumerate() {
        if address==0 || address%std::mem::align_of::<f64>()!=0 {return false;}
        let bytes=match length.checked_mul(8) {Some(n)=>n,None=>return false};
        if bytes>isize::MAX as usize {return false;}
        let end=match address.checked_add(bytes) {Some(n)=>n,None=>return false};
        for &(other,count) in &buffers[..i] {
            let other_bytes=match count.checked_mul(8) {Some(n)=>n,None=>return false};
            let other_end=match other.checked_add(other_bytes) {Some(n)=>n,None=>return false};
            if bytes!=0 && other_bytes!=0 && address<other_end && other<end {return false;}
        }
    }
    true
}
#[no_mangle]
pub extern "C" fn lrt_body_slim_abi()->u32 {1}
/// Pointers must name valid live f64 allocations with exact lengths and no aliases.
#[no_mangle]
pub unsafe extern "C" fn lrt_body_slim_prepare(points:*const f64,points_len:usize,
    amounts:*const f64,amounts_len:usize,support:*const f64,support_len:usize,w:f64,h:f64,out:*mut f64,out_len:usize)->i32 {
    if points_len!=165 || amounts_len!=1 || !(20..=260).contains(&support_len) || support_len%2!=0 || out_len!=STATE_LEN
        || !disjoint_buffers(&[(points as usize,points_len),(amounts as usize,amounts_len),(support as usize,support_len),(out as usize,out_len)]) {return 1;}
    match prepare(slice::from_raw_parts(points,points_len),*amounts,slice::from_raw_parts(support,support_len),w,h) {
        Ok(s)=>{slice::from_raw_parts_mut(out,out_len).copy_from_slice(&s.0);0},Err(c)=>c
    }
}
#[no_mangle]
pub unsafe extern "C" fn lrt_body_slim_describe(state:*const f64,state_len:usize,out:*mut f64,out_len:usize)->i32 {
    if state_len!=STATE_LEN || out_len!=FACTS_LEN || !disjoint_buffers(&[(state as usize,state_len),(out as usize,out_len)]) {return 1;}
    match read_state(slice::from_raw_parts(state,state_len)) {
        Ok(s)=>{slice::from_raw_parts_mut(out,out_len).copy_from_slice(&s.facts());0},Err(c)=>c
    }
}
#[no_mangle]
pub unsafe extern "C" fn lrt_body_slim_evaluate(state:*const f64,state_len:usize,xy:*const f64,xy_len:usize,count:usize,
    out:*mut f64,out_len:usize,jac:*mut f64,jac_len:usize)->i32 {
    if state_len!=STATE_LEN || count>MAX_POINTS || xy_len!=count*2 || out_len!=count*2 || jac_len!=count
        || !disjoint_buffers(&[(state as usize,state_len),(xy as usize,xy_len),(out as usize,out_len),(jac as usize,jac_len)]) {return 1;}
    let s=match read_state(slice::from_raw_parts(state,state_len)) {Ok(s)=>s,Err(c)=>return c};
    let points=slice::from_raw_parts(xy,xy_len);
    if points.iter().any(|p|!p.is_finite()) {return 1;}
    // Complete admission before writing either buffer. No caller mutation during call.
    for i in 0..count {if let Err(c)=s.inverse(points[i*2],points[i*2+1]) {return c;}}
    let output=slice::from_raw_parts_mut(out,out_len);let determinants=slice::from_raw_parts_mut(jac,jac_len);
    for i in 0..count {
        match s.inverse(points[i*2],points[i*2+1]) {
            Ok((dx,j))=>{output[i*2]=dx;output[i*2+1]=0.0;determinants[i]=j;},Err(c)=>return c
        }
    }
    0
}
// These numerical fixtures are AUTHORED / UNRUN, not validation evidence.
#[cfg(test)]
mod tests {
    use super::*;
    fn state(amount:f64)->State {State([100.,400.,600.,900.,100.,400.,1200.,1500.,-0.08*amount,1001.,1601.])}
    #[test]
    fn whole_person_width_changes_at_head_torso_and_feet_without_height_change() {
        for amount in [-1.,0.,1.] {
            let s=state(amount);s.validate().unwrap();
            for y in [400.,800.,1200.] {
                let left=400.+s.forward(400.,y).0;let right=600.+s.forward(600.,y).0;
                assert!((right-left-200.*(1.-0.08*amount)).abs()<1e-10);
            }
        }
    }
    #[test]
    fn collar_exterior_identity_and_off_grid_inverse() {
        for amount in [-1.,1.] {
            let s=state(amount);s.validate().unwrap();
            for (x,y) in [(0.,0.),(1000.,1600.),(100.,800.),(900.,800.),(500.,100.),(500.,1500.)] {assert_eq!(s.inverse(x,y).unwrap(),(0.,1.));}
            for (x,y) in [(230.71,270.43),(410.31,711.13),(790.12,1312.17)] {
                let(d,j)=s.inverse(x,y).unwrap();assert!((x-d+s.forward(x-d,y).0-x).abs()<1e-7);
                let eps=1e-4;let(d2,_)=s.inverse(x+eps,y).unwrap();assert!((j-(eps-d2+d)/eps).abs()<1e-5);
            }
        }
    }
    #[test]
    fn no_clipping_no_partial_output_on_late_refusal() {
        let s=state(1.).0;let xy=[500.,800.,1000.1,800.];let mut out=[7.;4];let mut jac=[9.;2];
        assert_eq!(unsafe{lrt_body_slim_evaluate(s.as_ptr(),11,xy.as_ptr(),4,2,out.as_mut_ptr(),4,jac.as_mut_ptr(),2)},8);
        assert_eq!(out,[7.;4]);assert_eq!(jac,[9.;2]);
    }
    #[test]
    fn insufficient_collar_is_refused_not_strength_clamped() {
        let mut s=state(1.);s.0[0]=399.;assert_eq!(s.validate(),Err(6));
    }
}
