// SPDX-License-Identifier: GPL-3.0-or-later
// Parametric curve family adapted from RawTherapee 5.12, rtengine/curves.h and
// diagonalcurves.cc. Copyright (c) 2004-2010 Gabor Horvath <hgabor@rawtherapee.com>.
// LumaRetouch modifications: Rust port, log-domain evaluation, explicit neutral
// bypass, identity continuation, bounded split validation, fixed floating LUT.
// Distributed under GPL version 3 or later, WITHOUT ANY WARRANTY. See LICENSE.
//! Versioned display-range RGB stage; not a Lightroom or whole-RawTherapee match.
pub const ALGORITHM:&str="lrt-rt512-parametric-splitgrid-lut-v1";
pub const INTERVALS:usize=65536;
pub const SAMPLES:usize=INTERVALS+1;
pub const HEADER_BYTES:usize=40;
pub const REGION_INTERVALS:usize=INTERVALS/4;
pub const MIN_REGION:f64=0.01;
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Spec {pub enabled:bool,pub values:[f64;4],pub splits:[f64;3]}
impl Default for Spec {
    fn default()->Self{Self{enabled:true,values:[0.;4],splits:[0.25,0.5,0.75]}}
}
#[derive(Clone,Copy,Debug)]
pub struct Curve {spec:Spec,weights:[f64;4],m:f64,ms:f64,mh:f64,log_mid:f64,identity:bool}
impl Curve {
    pub fn new(spec:Spec)->Result<Self,&'static str>{
        if !spec.values.iter().all(|v|v.is_finite()&&(-100.0..=100.0).contains(v)){
            return Err("parametric values must be finite in [-100,100]");
        }
        let [s,c,h]=spec.splits;
        // A few binary64 ULPs tolerate decimal boundary roundoff, not visibly
        // overlapping regions. Schema validators must use the same tolerance.
        let eps=8.*f64::EPSILON;
        if !spec.splits.iter().all(|x|x.is_finite())||s+eps<MIN_REGION||c-s+eps<MIN_REGION
            ||h-c+eps<MIN_REGION||1.-h+eps<MIN_REGION{return Err("parametric regions must each span at least .01");}
        let weights=spec.values.map(|v|(v+100.)/200.);
        let m=0.5f64.ln()/c.ln();let ms=0.5f64.ln()/(s/c).ln();let mh=0.5f64.ln()/((h-c)/(1.-c)).ln();
        let log_mid=log_q(0.5f64.ln(),weights[1],weights[2])/m;
        if ![m,ms,mh,log_mid].iter().all(|x|x.is_finite())||log_mid>=0.{return Err("invalid parametric transform");}
        Ok(Self{spec,weights,m,ms,mh,log_mid,identity:!spec.enabled||spec.values.iter().all(|v|*v==0.)})
    }
    pub fn spec(&self)->Spec{self.spec}
    pub fn is_identity(&self)->bool{self.identity}
    pub fn grid_x(&self,i:usize)->f64{
        assert!(i<=INTERVALS,"parametric grid index outside table");
        if i==INTERVALS{return 1.;}
        let bounds=[0.,self.spec.splits[0],self.spec.splits[1],self.spec.splits[2],1.];
        let region=i/REGION_INTERVALS;let t=(i%REGION_INTERVALS) as f64/REGION_INTERVALS as f64;
        bounds[region]+(bounds[region+1]-bounds[region])*t
    }
    fn position(&self,x:f64)->(usize,f64){
        let bounds=[0.,self.spec.splits[0],self.spec.splits[1],self.spec.splits[2],1.];
        let region=self.spec.splits.iter().filter(|split|x>=**split).count();
        let position=(x-bounds[region])/(bounds[region+1]-bounds[region])*REGION_INTERVALS as f64;
        let lo=(position.floor() as usize).min(REGION_INTERVALS-1);
        (region*REGION_INTERVALS+lo,(position-lo as f64).clamp(0.,1.))
    }
    pub fn evaluate_table(&self,table:&[f32],x:f64)->Result<f64,&'static str>{
        if table.len()!=SAMPLES{return Err("invalid parametric table size");}
        if self.identity||!(x>0.&&x<1.){return Ok(x);}
        let (i,t)=self.position(x);
        Ok(table[i] as f64+(table[i+1] as f64-table[i] as f64)*t)
    }
    pub fn encode(&self,table:&[f32])->Result<Vec<u8>,&'static str>{
        if table.len()!=SAMPLES||table[0]!=0.||table[SAMPLES-1]!=1.
            ||table.iter().any(|v|!v.is_finite())||table.windows(2).any(|p|p[1]<p[0]){return Err("invalid parametric table");}
        let mut bytes=vec![0u8;HEADER_BYTES];bytes[..4].copy_from_slice(b"LPC1");
        bytes[4..6].copy_from_slice(&1u16.to_le_bytes());bytes[6..8].copy_from_slice(&(HEADER_BYTES as u16).to_le_bytes());
        bytes[8..12].copy_from_slice(&(SAMPLES as u32).to_le_bytes());bytes[12..16].copy_from_slice(&1u32.to_le_bytes());
        for (i,split) in self.spec.splits.iter().enumerate(){bytes[16+i*8..24+i*8].copy_from_slice(&split.to_le_bytes());}
        for value in table{bytes.extend_from_slice(&value.to_le_bytes());}Ok(bytes)
    }
    pub fn evaluate(&self,x:f64)->f64{
        if self.identity||!(x>0.&&x<1.){return x;}
        let base=log_q(self.m*x.ln(),self.weights[1],self.weights[2])/self.m;
        let center=self.spec.splits[1];
        let result=if x==center{self.log_mid.exp()}
        else if x<center{
            (self.log_mid+log_q((self.ms*(base-self.log_mid)).min(0.),self.weights[0],0.5)/self.ms).exp()
        }else{
            // B(x)-B(c) and 1-B(c) remain accurate near the shared midpoint.
            let delta=(base-self.log_mid).exp_m1();
            if delta<=0.{return self.log_mid.exp();}
            let log_ratio=(self.log_mid+delta.ln()-(-self.log_mid.exp_m1()).ln()).min(0.);
            let adjusted=log_q(self.mh*log_ratio,0.5,self.weights[3])/self.mh;
            1.+(-self.log_mid.exp_m1())*adjusted.exp_m1()
        };
        result.clamp(0.,1.)
    }
    pub fn compile(&self)->Result<Vec<f32>,&'static str>{
        let mut table=Vec::with_capacity(SAMPLES);let mut previous=0.;
        for i in 0..SAMPLES{
            let value=self.evaluate(self.grid_x(i)) as f32;
            if !value.is_finite()||!(0.0..=1.0).contains(&value)||value<previous{
                return Err("parametric LUT is not finite, bounded and monotone");
            }
            previous=value;table.push(value);
        }
        Ok(table)
    }
    /// Same two lattice samples as the full table, without compiling all samples.
    pub fn sampled(&self,x:f64)->f64{
        if self.identity||!(x>0.&&x<1.){return x;}
        let (lo,t)=self.position(x);
        let a=self.evaluate(self.grid_x(lo)) as f32 as f64;
        let b=self.evaluate(self.grid_x(lo+1)) as f32 as f64;
        a+(b-a)*t
    }
    /// Reachable vertical graph drag; returns the parameter and actual LUT value.
    pub fn solve(&self,region:usize,target:f64)->Result<(f64,f64),&'static str>{
        if region>=4||!target.is_finite(){return Err("invalid parametric drag");}
        let bounds=[0.,self.spec.splits[0],self.spec.splits[1],self.spec.splits[2],1.];
        let x=(bounds[region]+bounds[region+1])*0.5;
        let evaluate=|v:f64|->Result<f64,&'static str>{let mut s=self.spec;s.enabled=true;s.values[region]=v;Ok(Self::new(s)?.sampled(x))};
        let mut lo=-100.;let mut hi=100.;let lower=evaluate(lo)?;let upper=evaluate(hi)?;
        if upper==lower{return Ok((self.spec.values[region],lower));}
        if upper<lower{return Err("parametric drag range is not monotone");}
        if target<=lower{return Ok((lo,lower));}if target>=upper{return Ok((hi,upper));}
        for _ in 0..48{let mid=(lo+hi)*0.5;if evaluate(mid)?<target{lo=mid;}else{hi=mid;}}
        let value=(lo+hi)*0.5;Ok((value,evaluate(value)?))
    }
}
// Log of the quartic basis, avoiding an intermediate underflow before taking roots.
fn log_q(log_z:f64,u:f64,v:f64)->f64{
    if log_z>=0.{return 0.;}
    if log_z<=0.5f64.ln(){return log_q_low(log_z,u,v);}
    let log_complement=(-log_z.exp_m1()).ln();
    (-log_q_low(log_complement,1.-v,1.-u).exp()).ln_1p()
}
fn log_q_low(log_z:f64,u:f64,v:f64)->f64{
    let z=log_z.exp();let a=2.-10.*u+6.*v;let b=-1.+9.*u-7.*v;
    if u==0.{3.*log_z+(a+b*z).ln()}
    else{log_z+(2.*u+z*z*(a+b*z)).ln()}
}
#[cfg(test)]
mod tests{
    use super::*;
    fn reference_q(x:f64,u:f64,v:f64)->f64{
        let low=|z:f64|(2.-z)*z*z*z;let high=|z:f64|z*(2.+(z-2.)*z*z);
        let base=(1.-u)*(1.-v)*low(x)+u*v*high(x);
        if x<=0.5{base+(1.-u)*v*low(2.*x)*0.5+u*(1.-v)*high(2.*x)*0.5}
        else{base+(1.-u)*v*(0.5+high(2.*x-1.)*0.5)+u*(1.-v)*(0.5+low(2.*x-1.)*0.5)}
    }
    fn reference(s:Spec,x:f64)->f64{
        let [a,b,d,e]=s.values.map(|v|(v+100.)/200.);let [l,c,h]=s.splits;
        let m=0.5f64.ln()/c.ln();let ms=0.5f64.ln()/(l/c).ln();let mh=0.5f64.ln()/((h-c)/(1.-c)).ln();
        let base=reference_q(x.powf(m),b,d).powf(1./m);let mid=reference_q(0.5,b,d).powf(1./m);
        if x<c{mid*reference_q((base/mid).powf(ms),a,0.5).powf(1./ms)}
        else{mid+(1.-mid)*reference_q(((base-mid)/(1.-mid)).powf(mh),0.5,e).powf(1./mh)}
    }
    #[test]fn neutral_and_disabled_are_exact_including_extended_values(){
        for splits in [[0.25,0.5,0.75],[0.01,0.02,0.99],[0.97,0.98,0.99]]{
            for s in [Spec{splits,..Spec::default()},Spec{enabled:false,values:[100.;4],splits}]{
                let c=Curve::new(s).unwrap();let table=c.compile().unwrap();
                for x in [-2.,-0.,0.,0.123456789,1.,12.]{
                    assert_eq!(c.evaluate(x).to_bits(),x.to_bits());assert_eq!(c.sampled(x).to_bits(),x.to_bits());
                    assert_eq!(c.evaluate_table(&table,x).unwrap().to_bits(),x.to_bits());
                }
            }
        }
    }
    #[test]fn rejects_invalid_values_and_regions(){
        for values in [[f64::NAN,0.,0.,0.],[101.,0.,0.,0.],[-101.,0.,0.,0.]]{assert!(Curve::new(Spec{values,..Spec::default()}).is_err());}
        for splits in [[0.,0.5,0.75],[0.4,0.3,0.8],[0.2,0.205,0.8],[0.2,0.5,1.]]{assert!(Curve::new(Spec{splits,..Spec::default()}).is_err());}
    }
    #[test]fn matches_upstream_basis_reference_in_normal_domain(){
        for values in [[-100.,100.,-100.,100.],[100.,-100.,100.,-100.],[32.,-42.,28.,-19.]]{
            let s=Spec{values,splits:[0.2,0.55,0.8],enabled:true};let c=Curve::new(s).unwrap();
            for i in 1..1000{let x=i as f64/1000.;assert!((c.evaluate(x)-reference(s,x)).abs()<2e-12,"x={x}");}
        }
    }
    #[test]fn four_slider_directions_and_known_midpoint_values(){
        for (region,x,up,down) in [(0,0.25,0.328125,0.171875),(3,0.75,0.828125,0.671875)]{
            for (value,expected) in [(100.,up),(-100.,down)]{let mut s=Spec::default();s.values[region]=value;assert!((Curve::new(s).unwrap().evaluate(x)-expected).abs()<1e-14);}
        }
        for region in 0..4{let x=[0.125,0.375,0.625,0.875][region];let mut s=Spec::default();s.values[region]=100.;assert!(Curve::new(s).unwrap().evaluate(x)>x);s.values[region]=-100.;assert!(Curve::new(s).unwrap().evaluate(x)<x);}
    }
    #[test]fn extreme_regions_remain_finite_bounded_and_monotone(){
        for splits in [[0.01,0.02,0.03],[0.01,0.5,0.99],[0.97,0.98,0.99],[0.25,0.5,0.75]]{
            for bits in 0..16{let values=std::array::from_fn(|i|if bits&(1<<i)==0{-100.}else{100.});
                let c=Curve::new(Spec{enabled:true,values,splits}).unwrap();let mut previous=0.;
                for i in 0..=4096{let y=c.evaluate(i as f64/4096.);assert!(y.is_finite()&&(0.0..=1.0).contains(&y)&&y+1e-14>=previous);previous=y;}
                for x in [1e-100,1e-20,splits[1]-1e-12,splits[1],splits[1]+1e-12,1.-1e-12]{assert!(c.evaluate(x).is_finite());}
            }
        }
    }
    #[test]fn lut_binary_and_sparse_sampling_agree(){
        let c=Curve::new(Spec{values:[47.,-32.,19.,-8.],..Spec::default()}).unwrap();let table=c.compile().unwrap();let bytes=c.encode(&table).unwrap();
        assert_eq!(bytes.len(),HEADER_BYTES+SAMPLES*4);assert_eq!(&bytes[..4],b"LPC1");assert_eq!(u32::from_le_bytes(bytes[12..16].try_into().unwrap()),1);
        for i in 0..3{assert_eq!(f64::from_le_bytes(bytes[16+i*8..24+i*8].try_into().unwrap()),c.spec.splits[i]);}
        for x in [-1.,0.,0.000001,0.1234567,0.500001,0.999999,1.,2.]{assert_eq!(c.sampled(x),c.evaluate_table(&table,x).unwrap());}
    }
    #[test]fn inverse_drag_preserves_other_parameters_and_reports_reachable_output(){
        let c=Curve::new(Spec::default()).unwrap();for region in 0..4{let x=[0.125,0.375,0.625,0.875][region];let mut s=c.spec;s.values[region]=37.;let target=Curve::new(s).unwrap().sampled(x);
            let (v,actual)=c.solve(region,target).unwrap();assert!((v-37.).abs()<0.01);assert!((actual-target).abs()<1e-7);}
        let (v,_)=c.solve(0,2.).unwrap();assert_eq!(v,100.);assert!(c.solve(4,0.5).is_err());
    }
    fn quality_cases()->Vec<Spec>{
        let mut cases=Vec::new();
        for splits in [[0.01,0.02,0.03],[0.01,0.5,0.99],[0.97,0.98,0.99],[0.25,0.5,0.75],
            [0.01,0.02,0.99],[0.01,0.98,0.99],[0.01,0.5,0.51],[0.49,0.5,0.99]]{
            for bits in 0..16{cases.push(Spec{enabled:true,splits,values:std::array::from_fn(|i|if bits&(1<<i)==0{-100.}else{100.})});}
            for values in [[47.,-32.,19.,-8.],[100.,-99.99999999999999,100.,-100.],[-100.,100.,-99.99999999999999,100.]]{
                cases.push(Spec{enabled:true,splits,values});
            }
        }
        let mut state=0x9e3779b97f4a7c15u64;
        let mut random=||{state=state.wrapping_mul(6364136223846793005).wrapping_add(1);(state>>11) as f64/((1u64<<53) as f64)};
        for _ in 0..16{let weights:[f64;4]=std::array::from_fn(|_|0.001+random());let sum:f64=weights.iter().sum();
            let splits=[0.01+0.96*weights[0]/sum,0.02+0.96*(weights[0]+weights[1])/sum,0.03+0.96*(weights[0]+weights[1]+weights[2])/sum];
            cases.push(Spec{enabled:true,splits,values:std::array::from_fn(|_|random()*200.-100.)});
        }
        cases
    }
    #[test]fn dense_lut_quality_gate_includes_between_sample_extreme_inputs(){
        let mut maximum=0.0f64;let cases=quality_cases();let mut worst=None;
        for spec in &cases{let c=Curve::new(*spec).unwrap();let table=c.compile().unwrap();
            for i in 0..INTERVALS{for fraction in [0.25,0.5,0.75]{let x=c.grid_x(i)+(c.grid_x(i+1)-c.grid_x(i))*fraction;
                let error=(c.evaluate_table(&table,x).unwrap()-c.evaluate(x)).abs();
                if error>maximum{maximum=error;worst=Some((*spec,x));}
            }}
            for split in spec.splits{for x in [split-1e-12,split,split+1e-12]{assert!((c.evaluate_table(&table,x).unwrap()-c.evaluate(x)).abs()<=2e-6);}}
        }
        eprintln!("parametric LUT maximum tested between-sample absolute error: {maximum:e}, profiles={}, worst={worst:?}",cases.len());
        assert!(maximum<=2e-6,"LUT density/representation needs improvement: {maximum:e}, worst={worst:?}");
    }

    #[test]fn own_region_drag_slider_has_monotone_response_across_mixed_extremes(){
        for splits in [[0.01,0.02,0.03],[0.01,0.5,0.99],[0.97,0.98,0.99],[0.25,0.5,0.75]]{
            let bounds=[0.,splits[0],splits[1],splits[2],1.];
            for region in 0..4{let x=(bounds[region]+bounds[region+1])*0.5;
                for bits in 0..16{let mut values=std::array::from_fn(|i|if bits&(1<<i)==0{-100.}else{100.});let mut previous=-1.;
                    for slider in -100..=100{values[region]=slider as f64;
                        let y=Curve::new(Spec{enabled:true,values,splits}).unwrap().sampled(x);
                        assert!(y+1e-12>=previous,"region={region}, slider={slider}, splits={splits:?}, other={values:?}");previous=y;
                    }
                }
            }
        }
    }

}
