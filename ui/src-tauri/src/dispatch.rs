//! One acknowledged command in flight; coalesce only explicitly interactive values.
use std::io::Write;
use std::sync::{Arc, Condvar, Mutex};
use serde_json::{json, Value};
use crate::edit_queue::LatestQueue;

struct State {
    queue: LatestQueue<Value>,
    in_flight: Option<u64>,
    next: u64,
    closed: bool,
    finishing: bool,
}
pub struct Dispatcher { state: Mutex<State>, wake: Condvar }
impl Dispatcher {
    pub fn new() -> Arc<Self> {
        Arc::new(Self { state: Mutex::new(State {queue:LatestQueue::new(256),in_flight:None,next:1,closed:false,finishing:false}), wake:Condvar::new() })
    }
    pub fn enqueue(&self, key: Option<String>, cmd: Value) -> Result<(), String> {
        let mut s=self.state.lock().map_err(|_|"编辑队列锁中毒")?;
        if s.closed {return Err("引擎已断开，操作未提交".into());}
        if cmd["cmd"] == "shutdown" {
            if !s.finishing {s.queue.finish(cmd);s.finishing=true;}
        } else {
            if s.finishing {return Err("引擎正在退出，操作未提交".into());}
            s.queue.push(key,cmd).map_err(str::to_owned)?;
        }
        self.wake.notify_all(); Ok(())
    }
    pub fn acknowledge(&self, id:u64) {
        if let Ok(mut s)=self.state.lock() {
            if s.in_flight==Some(id) {s.in_flight=None;self.wake.notify_all();}
        }
    }
    pub fn close(&self) {
        if let Ok(mut s)=self.state.lock() {s.closed=true;self.wake.notify_all();}
    }
    pub fn stats(&self)->Value {
        match self.state.lock() {
            Ok(s)=>json!({"pending":s.queue.len(),"in_flight":s.in_flight.is_some(),"coalesced":s.queue.coalesced,"closed":s.closed}),
            Err(_)=>json!({"error":"编辑队列锁中毒"}),
        }
    }
    pub fn run<W: Write>(&self, mut stdin:W) -> Result<(),String> {
        loop {
            let mut s=self.state.lock().map_err(|_|"编辑队列锁中毒")?;
            while !s.closed && (s.in_flight.is_some() || s.queue.len()==0) {
                s=self.wake.wait(s).map_err(|_|"编辑队列锁中毒")?;
            }
            if s.closed {return Ok(());}
            let mut cmd=s.queue.pop().ok_or("编辑队列为空")?;
            let id=s.next;s.next=s.next.checked_add(1).ok_or("命令序号耗尽")?;
            s.in_flight=Some(id);
            drop(s);
            cmd["_host_request_id"]=json!(id);
            let line=serde_json::to_string(&cmd).map_err(|e|e.to_string())?;
            if let Err(e)=stdin.write_all(line.as_bytes()).and_then(|_|stdin.write_all(b"\n")).and_then(|_|stdin.flush()) {
                self.close();return Err(format!("写引擎 stdin 失败，未重试：{e}"));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io;
    use std::thread;
    use std::time::{Duration,Instant};
    struct Sink(Arc<Mutex<Vec<u8>>>);
    impl Write for Sink {
        fn write(&mut self,b:&[u8])->io::Result<usize>{self.0.lock().unwrap().extend_from_slice(b);Ok(b.len())}
        fn flush(&mut self)->io::Result<()>{Ok(())}
    }
    fn wait(mut f:impl FnMut()->bool) {
        let until=Instant::now()+Duration::from_secs(2);
        while !f() {assert!(Instant::now()<until,"dispatcher timed out");thread::sleep(Duration::from_millis(1));}
    }
    #[test]
    fn acknowledged_dispatch_coalesces_only_pending_and_keeps_barriers() {
        let d=Dispatcher::new();let bytes=Arc::new(Mutex::new(Vec::new()));
        let runner=d.clone();let sink=Sink(bytes.clone());
        let worker=thread::spawn(move||runner.run(sink));
        d.enqueue(None,json!({"cmd":"hello"})).unwrap();
        wait(||bytes.lock().unwrap().ends_with(b"\n"));
        for n in 0..20 {d.enqueue(Some("ev".into()),json!({"cmd":"exposure","ev":n})).unwrap();}
        d.enqueue(None,json!({"cmd":"history","action":"undo"})).unwrap();
        assert_eq!(d.stats()["pending"],2);assert_eq!(d.stats()["coalesced"],19);
        d.acknowledge(999);assert_eq!(d.stats()["pending"],2);
        d.acknowledge(1);
        wait(||bytes.lock().unwrap().iter().filter(|&&b|b==b'\n').count()==2);
        let lines=String::from_utf8(bytes.lock().unwrap().clone()).unwrap();
        let events:Vec<Value>=lines.lines().map(|s|serde_json::from_str(s).unwrap()).collect();
        assert_eq!(events[1]["ev"],19);assert_eq!(events[1]["_host_request_id"],2);
        d.acknowledge(2);
        wait(||bytes.lock().unwrap().iter().filter(|&&b|b==b'\n').count()==3);
        let lines=String::from_utf8(bytes.lock().unwrap().clone()).unwrap();
        let last:Value=serde_json::from_str(lines.lines().last().unwrap()).unwrap();
        assert_eq!(last["cmd"],"history");
        d.close();assert!(worker.join().unwrap().is_ok());
        assert!(d.enqueue(None,json!({"cmd":"hello"})).is_err());
    }
    struct Broken;
    impl Write for Broken {
        fn write(&mut self,_:&[u8])->io::Result<usize>{Err(io::Error::new(io::ErrorKind::BrokenPipe,"test"))}
        fn flush(&mut self)->io::Result<()>{Ok(())}
    }
    #[test]
    fn broken_write_closes_without_retry() {
        let d=Dispatcher::new();d.enqueue(None,json!({"cmd":"hello"})).unwrap();
        assert!(d.run(Broken).is_err());assert_eq!(d.stats()["closed"],true);
        assert!(d.enqueue(None,json!({"cmd":"hello"})).is_err());
    }
}
