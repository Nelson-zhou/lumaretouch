// SPDX-License-Identifier: GPL-3.0-or-later
// Original dependency-free f64 radix-2 reference FFT. AUTHORED / UNRUN.
// No table download, library planner, SIMD/thread pool, or hidden allocation.
use crate::{poll, RESULT_ERROR};
#[derive(Clone, Copy, Default, Debug)]
pub(crate) struct Complex { pub re:f64, pub im:f64 }
impl Complex {
    pub(crate) fn mul(self,b:Self)->Self { Self { re:self.re*b.re-self.im*b.im, im:self.re*b.im+self.im*b.re } }
}
fn line<F:FnMut()->bool>(a:&mut [Complex],inverse:bool,cancel:&mut F)->Result<(),i32> {
    let n=a.len();
    debug_assert!(n.is_power_of_two());
    let mut j=0usize;
    for i in 1..n {
        let mut bit=n>>1;
        while j&bit!=0 { j^=bit; bit>>=1; }
        j^=bit;
        if i<j { a.swap(i,j); }
    }
    let mut len=2usize;
    while len<=n {
        let angle=(if inverse {2.0} else {-2.0})*std::f64::consts::PI/len as f64;
        let (s,c)=angle.sin_cos();
        let root=Complex {re:c,im:s};
        for start in (0..n).step_by(len) {
            let mut w=Complex {re:1.0,im:0.0};
            for k in 0..len/2 {
                let u=a[start+k];
                let v=a[start+k+len/2].mul(w);
                a[start+k]=Complex {re:u.re+v.re, im:u.im+v.im};
                a[start+k+len/2]=Complex {re:u.re-v.re,im:u.im-v.im};
                w=w.mul(root);
            }
        }
        len*=2;
    }
    poll(cancel)
}
pub(crate) fn transform<F:FnMut()->bool>(a:&mut [Complex],width:usize,height:usize,
    column:&mut [Complex],inverse:bool,cancel:&mut F)->Result<(),i32> {
    // Poll every row and column; one uninterruptible radix-2 line is <=512.
    for row in a.chunks_exact_mut(width) { line(row,inverse,cancel)?; }
    for x in 0..width {
        for y in 0..height { column[y]=a[y*width+x]; }
        line(&mut column[..height],inverse,cancel)?;
        for y in 0..height { a[y*width+x]=column[y]; }
    }
    if inverse {
        let norm=(width*height) as f64;
        for row in a.chunks_exact_mut(width) {
            poll(cancel)?;
            for c in row { c.re/=norm; c.im/=norm; }
        }
    }
    for chunk in a.chunks(256){
        poll(cancel)?;
        if chunk.iter().any(|c|!c.re.is_finite() || !c.im.is_finite()){return Err(RESULT_ERROR);}
    }
    Ok(())
}
#[cfg(test)]
pub(crate) fn test_transform(a:&mut [Complex],w:usize,h:usize,inverse:bool)->Result<(),i32> {
    let mut col=vec![Complex::default();h];
    transform(a,w,h,&mut col,inverse,&mut ||false)
}
