// SPDX-License-Identifier: GPL-3.0-or-later
// Same original Lumaretouch v1 aperture and radius arithmetic, new accumulation
// identity. No external implementation adapted; v1 source is left untouched.
use crate::{Settings, SETTINGS_ERROR};

pub(crate) fn unit(x: f32) -> bool { x.is_finite() && (0.0..=1.0).contains(&x) }
impl Settings {
    pub(crate) fn validate(self) -> Result<(), i32> {
        if self.aperture > 4 || !unit(self.manual_depth) || self.manual_depth_ack != 1
            || !self.max_radius_px.is_finite() || !(0.0..=128.0).contains(&self.max_radius_px)
            || !unit(self.focus_near) || !unit(self.focus_far) || self.focus_near > self.focus_far
            || !self.depth_falloff.is_finite() || !(0.000_001..=1.0).contains(&self.depth_falloff)
            || !unit(self.occlusion_tolerance) || !self.rotation_radians.is_finite()
            || !(-std::f32::consts::PI..=std::f32::consts::PI).contains(&self.rotation_radians)
        { return Err(SETTINGS_ERROR); }
        Ok(())
    }
}
pub(crate) fn radius(q: f32, s: Settings) -> f64 {
    let z = f64::from(s.manual_depth);
    let distance = (f64::from(s.focus_near)-z).max(z-f64::from(s.focus_far)).max(0.0);
    let base = (distance/f64::from(s.depth_falloff)).min(1.0);
    let q = f64::from(q);
    let refined = if q >= 0.0 { base+(1.0-base)*q } else { base*(1.0+q) };
    f64::from(s.max_radius_px)*refined
}
pub(crate) fn halo(r: f64) -> usize { if r <= 0.5 { 0 } else { (r+0.5).ceil() as usize } }
pub(crate) struct Aperture {
    id: u32, cosine: f64, sine: f64, normals: [[f64; 2]; 8], sides: usize,
    inradius: f64, unit_mass: f64,
}
impl Aperture {
    pub(crate) fn new(s: Settings) -> Self {
        let (sine, cosine) = f64::from(s.rotation_radians).sin_cos();
        let sides = match s.aperture { 2=>5, 3=>8, _=>0 };
        let mut normals = [[0.0; 2]; 8];
        let pi = std::f64::consts::PI;
        for (k, n) in normals.iter_mut().take(sides).enumerate() {
            let angle = 2.0*pi*k as f64/sides as f64;
            *n = [angle.cos(), angle.sin()];
        }
        let inradius = if sides > 0 { (pi/sides as f64).cos() } else { 0.0 };
        let unit_mass = match s.aperture {
            0=>pi, 1=>0.625*pi,
            2|3=>0.5*sides as f64*(2.0*pi/sides as f64).sin(),
            4=>2.0*0.35_f64.acos()-0.7*(1.0-0.35_f64.powi(2)).sqrt(),
            _=>unreachable!(),
        };
        Self { id:s.aperture, cosine, sine, normals, sides, inradius, unit_mass }
    }
    fn transmission(&self, x:f64, y:f64)->f64 {
        let u=self.cosine*x+self.sine*y;
        let v=-self.sine*x+self.cosine*y;
        let rr=u*u+v*v;
        if rr>1.0 { return 0.0; }
        match self.id {
            0=>1.0, 1=>0.25+0.75*rr,
            2|3=>if self.normals[..self.sides].iter().all(|n|u*n[0]+v*n[1]<=self.inradius) {1.0} else {0.0},
            4=>if (u-0.35).powi(2)+v*v<=1.0 && (u+0.35).powi(2)+v*v<=1.0 {1.0} else {0.0},
            _=>0.0,
        }
    }
    pub(crate) fn weight(&self, dx:f64, dy:f64, r:f64)->f64 {
        if r<=0.5 { return if dx==0.0 && dy==0.0 {1.0} else {0.0}; }
        if dx.abs()>r+0.5 || dy.abs()>r+0.5 { return 0.0; }
        let mut integral=0.0;
        for sy in 0..4 {
            let y=(dy+(sy as f64+0.5)/4.0-0.5)/r;
            for sx in 0..4 {
                let x=(dx+(sx as f64+0.5)/4.0-0.5)/r;
                integral+=self.transmission(x,y);
            }
        }
        integral/(16.0*self.unit_mass*r*r)
    }
}
