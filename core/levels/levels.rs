//! Display-sRGB levels contract. Pure scalar reference and native validation.
pub const MIN_GAP:f64=1e-5;
pub const GAMMA_MIN:f64=0.1;
pub const GAMMA_MAX:f64=10.0;
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Channel {pub black:f64,pub white:f64,pub gamma:f64,pub out_black:f64,pub out_white:f64}
impl Channel {
    pub fn new(values:[f64;5])->Result<Self,&'static str>{
        let [black,white,gamma,out_black,out_white]=values;
        if !values.iter().all(|v|v.is_finite()) {return Err("levels require finite values");}
        if [black,white,out_black,out_white].iter().any(|v|!(0.0..=1.0).contains(v)) {
            return Err("levels endpoints must be in [0,1]");
        }
        if white-black<MIN_GAP {return Err("levels input white must exceed black by at least 1e-5");}
        if !(GAMMA_MIN..=GAMMA_MAX).contains(&gamma) {return Err("levels gamma must be in [0.1,10]");}
        Ok(Self{black,white,gamma,out_black,out_white})
    }
    pub fn identity(&self)->bool {
        self.black==0. && self.white==1. && self.gamma==1. && self.out_black==0. && self.out_white==1.
    }
    pub fn apply(&self,x:f64)->f64 {
        if self.identity(){return x;}
        let t=((x-self.black)/(self.white-self.black)).clamp(0.,1.);
        self.out_black+(self.out_white-self.out_black)*t.powf(1./self.gamma)
    }
}
pub fn apply_rgb(rgb:[f64;3],channels:&[Channel;4],enabled:bool)->[f64;3]{
    if !enabled {return rgb;}
    std::array::from_fn(|i|channels[i+1].apply(channels[0].apply(rgb[i])))
}
#[cfg(test)]
mod tests {
    use super::*;
    fn neutral()->Channel{Channel::new([0.,1.,1.,0.,1.]).unwrap()}
    #[test] fn neutral_preserves_hdr_negative_and_signed_zero(){
        for x in [-2.,-0.,0.4,3.]{assert_eq!(neutral().apply(x).to_bits(),x.to_bits());}
    }
    #[test] fn gamma_greater_than_one_brightens_and_endpoints_are_exact(){
        let c=Channel::new([0.1,0.9,2.,0.2,0.8]).unwrap();
        assert_eq!(c.apply(-1.),0.2);assert_eq!(c.apply(2.),0.8);
        assert!((c.apply(0.3)-0.5).abs()<1e-12);
    }
    #[test] fn output_inversion_and_flat_output_are_intentional(){
        assert_eq!(Channel::new([0.,1.,1.,1.,0.]).unwrap().apply(0.25),0.75);
        assert_eq!(Channel::new([0.,1.,2.,0.4,0.4]).unwrap().apply(0.25),0.4);
    }
    #[test] fn malformed_parameters_are_rejected(){
        for p in [[0.,0.,1.,0.,1.],[0.,1.,0.,0.,1.],[0.,1.,f64::NAN,0.,1.],[-0.1,1.,1.,0.,1.]] {
            assert!(Channel::new(p).is_err());
        }
    }
    #[test] fn channel_order_and_untouched_channels_are_exact(){
        let n=neutral();let red=Channel::new([0.,1.,2.,0.,1.]).unwrap();
        assert_eq!(apply_rgb([0.25,-0.2,2.],&[n,red,n,n],true),[0.5,-0.2,2.]);
    }
}
