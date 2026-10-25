// SPDX-License-Identifier: GPL-3.0-or-later
use crate::{kernel::{self,Aperture},fft::{self,Complex},plan::{self,alloc,Residual,Cohort},*};
/// Declared ABI2 roundoff acceptance policy, not an empirically verified error
/// bound: finite normalized opaque-SDR error <=1e-9 can round to its legal
/// endpoint. Anything outside it is recomputed directly or rejected. Never feed
/// HDR/nonopaque input here. Acceptance tests remain UNRUN.
pub const NORMALIZED_ROUNDOFF:f64=1.0e-9;
pub struct Job<'a>{
    pub(crate) source:&'a [f32],pub(crate) refinement:Option<&'a [f32]>,
    pub(crate) settings:Settings,pub(crate) plan:Plan,
    pub(crate) cohorts:Vec<Cohort>,pub(crate) residuals:Vec<Residual>,
    pub(crate) tile_residual_pairs:Vec<u64>,
    pub(crate) halo:usize,pub(crate) next:u64,pub(crate) failed:bool,
    pub(crate) repairs_used:u64,
}
impl<'a> Job<'a>{
    pub fn plan(&self)->Plan{self.plan}
    pub fn create<F:FnMut()->bool>(source:&'a [f32],refinement:Option<&'a [f32]>,
        width:usize,height:usize,settings:Settings,budget:Budget,mut cancel:F)->Result<Self,i32>{
        let (plan,radii)=plan::make_plan(source,refinement,width,height,settings,budget,&mut cancel)?;
        let mut residuals=Vec::new();
        residuals.try_reserve_exact(plan.residual_emitters as usize).map_err(|_|RESOURCE_ERROR)?;
        let mut halo=0;
        for i in 0..plan.source_pixels as usize{
            if i%256==0{poll(&mut cancel)?;}
            let radius=kernel::radius(q_at(refinement,i),settings);halo=halo.max(kernel::halo(radius));
            if radius>0.5 && plan::index(radius,&radii).is_none(){residuals.push(Residual{i,radius});}
        }
        let mut tile_residual_pairs=alloc(plan.tile_count as usize,0u64)?;
        for index in 0..plan.tile_count{
            poll(&mut cancel)?;
            let x=(index%plan.tile_columns*plan.tile_width) as usize;
            let y=(index/plan.tile_columns*plan.tile_height) as usize;
            let tw=(plan.tile_width as usize).min(width-x);
            let th=(plan.tile_height as usize).min(height-y);
            let count=&mut tile_residual_pairs[index as usize];
            for (k,e) in residuals.iter().enumerate(){
                if k%256==0{poll(&mut cancel)?;}
                let eh=kernel::halo(e.radius);let sx=e.i%width;let sy=e.i/width;
                let x0=sx.saturating_sub(eh).max(x);let y0=sy.saturating_sub(eh).max(y);
                let x1=(sx+eh+1).min(x+tw).min(width);let y1=(sy+eh+1).min(y+th).min(height);
                if x0<x1&&y0<y1{*count=plan::add(*count,((x1-x0)*(y1-y0)) as u64)?;}
                if *count>plan::TILE_DIRECT{return Err(RESOURCE_ERROR);}
            }
        }
        let cohorts=plan::prepare(&radii,plan,settings,&mut cancel)?;
        poll(&mut cancel)?;
        Ok(Self{source,refinement,settings,plan,cohorts,residuals,tile_residual_pairs,halo,next:0,failed:false,repairs_used:0})
    }
    pub fn tile_rect(&self,index:u64)->Result<(usize,usize,usize,usize),i32>{
        if index>=self.plan.tile_count{return Err(STATE_ERROR);}
        let x=(index%self.plan.tile_columns)*self.plan.tile_width;
        let y=(index/self.plan.tile_columns)*self.plan.tile_height;
        Ok((x as usize,y as usize,self.plan.tile_width.min(self.plan.width-x) as usize,
            self.plan.tile_height.min(self.plan.height-y) as usize))
    }
    pub fn finish(&self)->Result<(),i32>{
        if self.failed || self.next!=self.plan.tile_count {Err(STATE_ERROR)}else{Ok(())}
    }
    pub fn render_next<F:FnMut()->bool>(&mut self,index:u64,output:&mut [f32],mut cancel:F)->Result<(),i32>{
        if self.failed || index!=self.next{self.failed=true;return Err(STATE_ERROR);}
        let result=self.render(index,output,&mut cancel);
        match result{Ok(())=>{self.next+=1;Ok(())},Err(e)=>{self.failed=true;Err(e)}}
    }
    fn weight(&self,i:usize,dx:isize,dy:isize,aperture:&Aperture)->f64{
        let r=kernel::radius(q_at(self.refinement,i),self.settings);
        if r<=0.5{return if dx==0&&dy==0{1.0}else{0.0};}
        if let Some(c)=self.cohorts.iter().find(|c|c.radius.to_bits()==r.to_bits()){
            c.weight(dx,dy)
        }else{aperture.weight(dx as f64,dy as f64,r)}
    }
    fn nonself_witness(&self,x:usize,y:usize,a:&Aperture)->bool{
        let w=self.plan.width as usize;let h=self.plan.height as usize;
        for dy in -1isize..=1{
            for dx in -1isize..=1{
                if dx==0&&dy==0{continue;}
                let sx=x as isize+dx;let sy=y as isize+dy;
                if sx<0||sy<0||sx>=w as isize||sy>=h as isize{continue;}
                if self.weight(sy as usize*w+sx as usize,-dx,-dy,a)>0.0{return true;}
            }
        }
        false // Inconclusive, NEVER interpreted as proof of sole self.
    }
    fn direct<F:FnMut()->bool>(&mut self,x:usize,y:usize,a:&Aperture,
        tile_direct:&mut u64,cancel:&mut F)->Result<[f32;4],i32>{
        let w=self.plan.width as usize;let h=self.plan.height as usize;
        let x0=x.saturating_sub(self.halo);let y0=y.saturating_sub(self.halo);
        let x1=(x+self.halo).min(w-1);let y1=(y+self.halo).min(h-1);
        let pairs=((x1-x0+1)*(y1-y0+1)) as u64;
        let used=plan::add(self.repairs_used,pairs)?;let tiled=plan::add(*tile_direct,pairs)?;
        if used>self.plan.repair_candidate_reservation||tiled>plan::TILE_DIRECT{return Err(RESOURCE_ERROR);}
        self.repairs_used=used;*tile_direct=tiled;
        let destination=y*w+x;let mut sums=[0.0;5];let mut contributors=0usize;let mut sole=usize::MAX;
        let mut ticks=0usize;
        for sy in y0..=y1{
            for sx in x0..=x1{
                if ticks%256==0{poll(cancel)?;}ticks+=1;
                let i=sy*w+sx;
                let weight=self.weight(i,x as isize-sx as isize,y as isize-sy as isize,a);
                if weight==0.0{continue;}
                contributors+=1;sole=i;
                for c in 0..4{sums[c]+=weight*f64::from(self.source[4*i+c]);}
                sums[4]+=weight;
            }
        }
        if contributors==1&&sole==destination{return Ok(self.original(destination));}
        self.normalized(sums,destination).ok_or(RESULT_ERROR)
    }
    fn original(&self,i:usize)->[f32;4]{self.source[4*i..4*i+4].try_into().expect("validated source")}
    fn normalized(&self,sums:[f64;5],destination:usize)->Option<[f32;4]>{
        let mass=sums[4];if !mass.is_finite()||mass<=0.0{return None;}
        let clear=f64::from((-q_at(self.refinement,destination)).max(0.0));
        let mut out=[0.0f32;4];
        for c in 0..4{
            let value=(1.0-clear)*(sums[c]/mass)+clear*f64::from(self.source[4*destination+c]);
            if !value.is_finite()||value< -NORMALIZED_ROUNDOFF||value>1.0+NORMALIZED_ROUNDOFF{return None;}
            if c==3{
                if (value-1.0).abs()>NORMALIZED_ROUNDOFF{return None;}
                out[c]=1.0; // Explicit ABI2 opaque-only numerical endpoint policy.
            }else{out[c]=value.clamp(0.0,1.0) as f32;}
        }
        Some(out)
    }
    fn render<F:FnMut()->bool>(&mut self,index:u64,output:&mut [f32],cancel:&mut F)->Result<(),i32>{
        let (x,y,tw,th)=self.tile_rect(index)?;let tn=tw*th;
        if output.len()!=tn*4{return Err(ABI_ERROR);}poll(cancel)?;
        let mut staged=alloc(tn*4,0.0f32)?;
        let w=self.plan.width as usize;let h=self.plan.height as usize;
        if self.halo==0{
            for ry in 0..th{poll(cancel)?;staged[ry*tw*4..(ry+1)*tw*4]
                .copy_from_slice(&self.source[((y+ry)*w+x)*4..((y+ry)*w+x+tw)*4]);}
            poll(cancel)?;output.copy_from_slice(&staged);return Ok(());
        }
        let mut tile_direct=self.tile_residual_pairs[index as usize];
        // Exact residual candidate rectangle intersections are disjoint between
        // cores; their full-job sum is bounded before any output is published.
        let mut sums=alloc(tn,[0.0f64;5])?;
        // Delta emitters (including q=-1 protected pixels) remain present.
        for ry in 0..th{
            poll(cancel)?;
            for rx in 0..tw{
                let i=(y+ry)*w+x+rx;
                if kernel::radius(q_at(self.refinement,i),self.settings)<=0.5{
                    for c in 0..4{sums[ry*tw+rx][c]=f64::from(self.source[4*i+c]);}
                    sums[ry*tw+rx][4]=1.0;
                }
            }
        }
        let fw=self.plan.fft_width as usize;let fh=self.plan.fft_height as usize;
        let mut buffer=alloc(fw*fh,Complex::default())?;let mut column=alloc(fh,Complex::default())?;
        let ox=x as isize-self.halo as isize;let oy=y as isize-self.halo as isize;
        let mut any_cohort_input=false;
        for cohort in &self.cohorts{
            // Three complex pairs carry R+iG, B+iA, mass+i0. Each input emitter
            // belongs to this exact radius-bit cohort OR a different partition.
            for pair in 0..3{
                let mut members=0usize;
                for fy in 0..fh{
                    poll(cancel)?;
                    for fx in 0..fw{
                        let entry=&mut buffer[fy*fw+fx];*entry=Complex::default();
                        if fx>=tw+2*self.halo||fy>=th+2*self.halo{continue;}
                        let sx=ox+fx as isize;let sy=oy+fy as isize;
                        if sx<0||sy<0||sx>=w as isize||sy>=h as isize{continue;}
                        let i=sy as usize*w+sx as usize;
                        if kernel::radius(q_at(self.refinement,i),self.settings).to_bits()!=cohort.radius.to_bits(){continue;}
                        members+=1;
                        if pair==2{entry.re=1.0;}else{
                            entry.re=f64::from(self.source[4*i+2*pair]);entry.im=f64::from(self.source[4*i+2*pair+1]);
                        }
                    }
                }
                if pair==0{
                    if members==0{break;} // Exact empty-mask certificate, not FFT thresholding.
                    any_cohort_input=true;
                }
                fft::transform(&mut buffer,fw,fh,&mut column,false,cancel)?;
                for fy in 0..fh{
                    poll(cancel)?;
                    for fx in 0..fw{let i=fy*fw+fx;buffer[i]=buffer[i].mul(cohort.spectrum[i]);}
                }
                fft::transform(&mut buffer,fw,fh,&mut column,true,cancel)?;
                for ry in 0..th{
                    poll(cancel)?;
                    for rx in 0..tw{
                        let v=buffer[(ry+self.halo)*fw+rx+self.halo];let dst=&mut sums[ry*tw+rx];
                        if pair==2{dst[4]+=v.re;}else{dst[pair*2]+=v.re;dst[pair*2+1]+=v.im;}
                    }
                }
            }
        }
        let aperture=Aperture::new(self.settings);let mut ticks=0usize;
        for e in &self.residuals{
            poll(cancel)?;
            let eh=kernel::halo(e.radius);let sx=e.i%w;let sy=e.i/w;
            for dy in sy.saturating_sub(eh).max(y)..(sy+eh+1).min(y+th).min(h){
                for dx in sx.saturating_sub(eh).max(x)..(sx+eh+1).min(x+tw).min(w){
                    if ticks%256==0{poll(cancel)?;}ticks+=1;
                    let weight=aperture.weight(dx as f64-sx as f64,dy as f64-sy as f64,e.radius);
                    let dst=&mut sums[(dy-y)*tw+dx-x];
                    for c in 0..4{dst[c]+=weight*f64::from(self.source[4*e.i+c]);}
                    dst[4]+=weight;
                }
            }
        }
        for ry in 0..th{
            for rx in 0..tw{
                if (ry*tw+rx)%256==0{poll(cancel)?;}
                let destination=(y+ry)*w+x+rx;
                let result=if q_at(self.refinement,destination)==-1.0
                    || (!any_cohort_input&&self.tile_residual_pairs[index as usize]==0){self.original(destination)}
                    else if !self.nonself_witness(x+rx,y+ry,&aperture){
                        self.direct(x+rx,y+ry,&aperture,&mut tile_direct,cancel)?
                    }else if let Some(value)=self.normalized(sums[ry*tw+rx],destination){value}
                    else{self.direct(x+rx,y+ry,&aperture,&mut tile_direct,cancel)?};
                staged[(ry*tw+rx)*4..(ry*tw+rx+1)*4].copy_from_slice(&result);
            }
        }
        poll(cancel)?;
        // The only caller-output write; errors above cannot leak partial tiles.
        output.copy_from_slice(&staged);Ok(())
    }
}
