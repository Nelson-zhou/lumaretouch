//! Full-source inspection admission/latest-result contracts (transport wiring pending).
//! ROI coordinates belong to the edited canvas. A patch is never a whole-image proxy.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Ticket { pub id:u64, pub document:u64, pub source_generation:u64, pub recipe:u64, pub viewport:u64 }
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Roi { pub x:u64, pub y:u64, pub width:u64, pub height:u64 }
#[derive(Clone, Debug)]
pub struct Request {
    pub ticket:Ticket,
    pub source_width:u64, pub source_height:u64,
    pub canvas_width:u64, pub canvas_height:u64,
    pub roi:Roi,
    /// Conservative live-buffer estimate, not just source file size.
    pub estimated_live_bytes:u64,
}
pub struct Budget { pub source_pixels:u64, pub patch_pixels:u64, pub live_bytes:u64 }
impl Request {
    pub fn rgba_bytes(&self)->Result<u64,&'static str>{
        self.roi.width.checked_mul(self.roi.height).and_then(|n|n.checked_mul(4)).ok_or("patch size overflow")
    }
    pub fn validate(&self,budget:&Budget)->Result<(),&'static str>{
        if self.ticket.id==0 || self.source_width==0 || self.source_height==0 || self.canvas_width==0 ||
           self.canvas_height==0 || self.roi.width==0 || self.roi.height==0 {return Err("empty inspection request");}
        let source=self.source_width.checked_mul(self.source_height).ok_or("source size overflow")?;
        let patch=self.roi.width.checked_mul(self.roi.height).ok_or("patch size overflow")?;
        let right=self.roi.x.checked_add(self.roi.width).ok_or("ROI overflow")?;
        let bottom=self.roi.y.checked_add(self.roi.height).ok_or("ROI overflow")?;
        if right>self.canvas_width || bottom>self.canvas_height {return Err("ROI outside edited canvas");}
        if source>budget.source_pixels || patch>budget.patch_pixels || self.estimated_live_bytes==0 ||
           self.estimated_live_bytes>budget.live_bytes {return Err("inspection exceeds admitted budget");}
        self.rgba_bytes()?;
        Ok(())
    }
}

#[derive(Default)]
pub struct Gate {
    last_id:u64,
    desired:Option<Ticket>,
    pending:Option<Request>,
    running:Option<Request>,
}
impl Gate {
    pub fn submit(&mut self,request:Request,budget:&Budget)->Result<(),&'static str>{
        request.validate(budget)?;
        if request.ticket.id<=self.last_id {return Err("inspection IDs must increase");}
        self.last_id=request.ticket.id;
        self.desired=Some(request.ticket);
        self.pending=Some(request); // bounded: newest desired request replaces only pending work
        Ok(())
    }
    pub fn start_next(&mut self)->Option<Request>{
        if self.running.is_some(){return None;}
        let request=self.pending.take()?;
        self.running=Some(request.clone());
        Some(request)
    }
    pub fn cancelled(&self,ticket:Ticket)->bool {self.desired!=Some(ticket)}
    pub fn invalidate(&mut self){self.desired=None;self.pending=None;}
    /// A failed/cancelled worker has no pixel payload. Release its own slot only.
    pub fn fail(&mut self,ticket:Ticket)->Result<(),&'static str>{
        if self.running.as_ref().map(|r|r.ticket)!=Some(ticket) {
            return Err("failure is not the running generation");
        }
        self.running=None;
        Ok(())
    }

    /// Consume only the known worker's completion. Stale completions free the
    /// running slot but never gain permission to replace displayed pixels.
    pub fn finish(&mut self,ticket:Ticket,roi:Roi,rgba_bytes:u64)->Result<bool,&'static str>{
        let running=self.running.as_ref().ok_or("no inspection is running")?;
        if running.ticket!=ticket {return Err("completion is not the running generation");}
        let expected=running.clone();
        self.running=None;
        if self.cancelled(ticket){return Ok(false);}
        if roi!=expected.roi || rgba_bytes!=expected.rgba_bytes()? {return Err("inspection pixel layout mismatch");}
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn budget()->Budget {Budget{source_pixels:10000,patch_pixels:100,live_bytes:1000000}}
    fn request(id:u64)->Request {Request{ticket:Ticket{id,document:1,source_generation:1,recipe:1,viewport:id},
        source_width:100,source_height:100,canvas_width:100,canvas_height:100,
        roi:Roi{x:10,y:20,width:10,height:10},estimated_live_bytes:500000}}
    #[test] fn only_one_running_and_latest_pending(){
        let mut g=Gate::default();g.submit(request(1),&budget()).unwrap();let first=g.start_next().unwrap();
        g.submit(request(2),&budget()).unwrap();g.submit(request(3),&budget()).unwrap();
        assert!(g.start_next().is_none());assert!(g.cancelled(first.ticket));
        assert!(!g.finish(first.ticket,first.roi,400).unwrap());
        let last=g.start_next().unwrap();assert_eq!(last.ticket.id,3);
        assert!(g.finish(last.ticket,last.roi,400).unwrap());assert!(g.start_next().is_none());
    }
    #[test] fn changing_document_invalidates_pixels_not_recipe(){
        let mut g=Gate::default();g.submit(request(1),&budget()).unwrap();let r=g.start_next().unwrap();
        g.invalidate();assert!(!g.finish(r.ticket,r.roi,400).unwrap());assert!(g.start_next().is_none());
    }
    #[test] fn reject_budget_and_coordinate_overflows(){
        let mut r=request(1);r.roi.x=u64::MAX;assert!(r.validate(&budget()).is_err());
        r=request(1);r.source_width=u64::MAX;assert!(r.validate(&budget()).is_err());
        r=request(1);r.estimated_live_bytes=1000001;assert!(r.validate(&budget()).is_err());
        r=request(1);r.roi.width=11;assert!(r.validate(&budget()).is_err());
        r=request(1);r.roi.width=0;assert!(r.validate(&budget()).is_err());
    }
    #[test] fn reused_ids_cannot_resurrect_old_viewports(){
        let mut g=Gate::default();g.submit(request(2),&budget()).unwrap();g.invalidate();
        assert!(g.submit(request(2),&budget()).is_err());assert!(g.submit(request(1),&budget()).is_err());
    }
    #[test] fn mismatched_completion_cannot_release_another_worker(){
        let mut g=Gate::default();g.submit(request(1),&budget()).unwrap();let r=g.start_next().unwrap();
        assert!(g.finish(request(2).ticket,r.roi,400).is_err());assert!(g.start_next().is_none());
        assert!(g.finish(r.ticket,r.roi,400).unwrap());
    }
    #[test] fn failed_worker_releases_slot_without_fake_pixels(){
        let mut g=Gate::default();g.submit(request(1),&budget()).unwrap();let first=g.start_next().unwrap();
        let mut next=request(2);next.ticket.source_generation=2;g.submit(next,&budget()).unwrap();
        assert!(g.fail(request(2).ticket).is_err());assert!(g.start_next().is_none());
        g.fail(first.ticket).unwrap();let second=g.start_next().unwrap();
        assert_eq!(second.ticket.source_generation,2);
        assert!(g.fail(first.ticket).is_err());assert!(g.finish(second.ticket,second.roi,400).unwrap());
    }
    #[test] fn cancelled_worker_can_report_failure_and_release_slot(){
        let mut g=Gate::default();g.submit(request(1),&budget()).unwrap();let r=g.start_next().unwrap();
        g.invalidate();g.fail(r.ticket).unwrap();g.submit(request(2),&budget()).unwrap();
        assert!(g.start_next().is_some());
    }
    #[test] fn incomplete_pixel_payload_never_publishes(){
        let mut g=Gate::default();g.submit(request(1),&budget()).unwrap();let r=g.start_next().unwrap();
        assert!(g.finish(r.ticket,r.roi,399).is_err());
        g.submit(request(2),&budget()).unwrap();assert!(g.start_next().is_some());
    }
}
