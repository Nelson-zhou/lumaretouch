//! Adjacent latest-value queue. Every unkeyed command is an ordering barrier.
use std::collections::VecDeque;

pub struct LatestQueue<T> {
    items: VecDeque<(Option<String>, T)>,
    pub coalesced: u64,
    capacity: usize,
}
impl<T> LatestQueue<T> {
    pub fn new(capacity: usize) -> Self {
        Self { items: VecDeque::new(), coalesced: 0, capacity }
    }
    pub fn push(&mut self, key: Option<String>, value: T) -> Result<(), &'static str> {
        if let Some(k) = key.as_ref() {
            if let Some((Some(last), item)) = self.items.back_mut() {
                if last == k { *item = value; self.coalesced += 1; return Ok(()); }
            }
        }
        if self.items.len() >= self.capacity { return Err("编辑队列已满，请等待当前操作完成"); }
        self.items.push_back((key, value));
        Ok(())
    }
    /// One final shutdown barrier is reserved even when normal capacity is full.
    pub fn finish(&mut self, value: T) { self.items.push_back((None,value)); }
    pub fn pop(&mut self) -> Option<T> { self.items.pop_front().map(|(_, v)| v) }
    pub fn len(&self) -> usize { self.items.len() }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn last_pending_value_wins() {
        let mut q=LatestQueue::new(8);
        for n in 0..100 {q.push(Some("skin-strength".into()),n).unwrap();}
        assert_eq!(q.len(),1); assert_eq!(q.pop(),Some(99)); assert_eq!(q.coalesced,99);
    }
    #[test] fn never_cross_document_history_or_export_barriers() {
        let mut q=LatestQueue::new(8);
        q.push(Some("x".into()),1).unwrap();q.push(None,2).unwrap();
        q.push(Some("x".into()),3).unwrap();q.push(Some("x".into()),4).unwrap();
        assert_eq!((q.pop(),q.pop(),q.pop()),(Some(1),Some(2),Some(4)));
    }
    #[test] fn separate_controls_do_not_overwrite() {
        let mut q=LatestQueue::new(8);
        for (k,v) in [("ev",1),("tint",2),("ev",3)] {q.push(Some(k.into()),v).unwrap();}
        assert_eq!((q.pop(),q.pop(),q.pop()),(Some(1),Some(2),Some(3)));
    }
    #[test] fn in_flight_value_is_not_replaced() {
        let mut q=LatestQueue::new(8);q.push(Some("x".into()),1).unwrap();
        let running=q.pop();q.push(Some("x".into()),2).unwrap();q.push(Some("x".into()),3).unwrap();
        assert_eq!(running,Some(1));assert_eq!(q.pop(),Some(3));
    }
    #[test] fn shutdown_barrier_is_preserved_when_full() {
        let mut q=LatestQueue::new(1);q.push(None,1).unwrap();q.finish(2);
        assert_eq!((q.pop(),q.pop()),(Some(1),Some(2)));
    }
    #[test] fn bounded_queue_rejects_without_dropping_earlier_work() {
        let mut q=LatestQueue::new(1);q.push(None,1).unwrap();assert!(q.push(None,2).is_err());
        assert_eq!(q.pop(),Some(1));
    }
}
