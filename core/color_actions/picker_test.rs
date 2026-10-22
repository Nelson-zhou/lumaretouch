//! Standalone unit-test crate; no image runtime, models or GUI.
#[path="../curves/curve.rs"] mod curve;
#[path="../levels/levels.rs"] mod levels;
mod picker;
#[cfg(test)]
mod additional {
    use super::*;
    #[test] fn white_neighbourhood_mean_stays_in_contract(){
        for count in [1,25,121] {let s=picker::sample(&vec![[1.,1.,1.,1.];count]).unwrap();assert_eq!(s.rgb,[1.;3]);assert_eq!(s.hsl,[0.,0.,1.]);}
    }
    #[test] fn black_pick_maps_rgb_to_existing_output_black_and_preserves_master(){
        let neutral=[0.,1.,1.,0.,1.];let mut bands=[neutral;4];bands[0]=[0.1,0.9,1.2,0.,1.];bands[1][3]=0.05;
        let s=picker::sample(&[[0.2,0.3,0.4,1.]]).unwrap();let next=picker::levels_pick(&s,bands,false).unwrap();
        assert_eq!(next[0],bands[0]);let channels=next.map(|r|levels::Channel::new(r).unwrap());
        let rgb=levels::apply_rgb(s.rgb,&channels,true);assert_eq!(rgb,[0.05,0.,0.]);
    }
    #[test] fn white_pick_preserves_gamma_output_and_opposite_endpoint(){
        let neutral=[0.,1.,1.,0.,1.];let s=picker::sample(&[[0.7,0.8,0.9,1.]]).unwrap();
        let next=picker::levels_pick(&s,[neutral;4],true).unwrap();
        assert_eq!(next[0],neutral);for i in 0..3{assert_eq!(next[i+1],[0.,s.rgb[i],1.,0.,1.]);}
    }
    #[test] fn hue_wrap_and_common_limit_are_finite(){
        for pixel in [[1.,0.,0.02,1.],[1.,0.02,0.,1.]]{
            let sample=picker::sample(&[pixel]).unwrap();let mut bands=[0.;24];bands[0]=59.;
            let (next,achieved)=picker::hsl_pick(&sample,bands,20.).unwrap();
            assert!((next[0]-60.).abs()<1e-12);assert!(achieved>0.&&achieved<20.);
        }
    }
    #[test] fn curve_near_endpoint_reuses_exact_endpoint(){
        let points=[curve::Point{x:0.,y:0.},curve::Point{x:1.,y:1.}];
        let (next,index,_)=picker::curve_pick(&points,0.000001,0.1).unwrap();assert_eq!(index,0);assert_eq!(next.len(),2);assert_eq!(next[0].x,0.);
    }
}
