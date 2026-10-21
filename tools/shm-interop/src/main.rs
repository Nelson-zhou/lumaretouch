#[path = "../../../ui/src-tauri/src/frame_presentation.rs"]
mod frame_presentation;
#[path = "../../../ui/src-tauri/src/frame_identity.rs"]
mod frame_identity;
#[path = "../../../ui/src-tauri/src/shm.rs"]
mod shm;
fn main() {
    let name=std::env::args().nth(1).expect("shared memory name");
    let reader=shm::ShmReader::open(&name).expect("open frame");
    if std::env::args().nth(2).as_deref()==Some("check-replacement") {
        use std::io::Write;
        println!("OPENED");std::io::stdout().flush().unwrap();
        let mut line=String::new();std::io::stdin().read_line(&mut line).unwrap();
        match reader.read() {
            Err(error) if error.contains("instance replaced")=>{println!("{error}");return;}
            Err(error)=>panic!("wrong rejection: {error}"),
            Ok(_)=>panic!("reader accepted replaced instance"),
        }
    }
    let locked=reader.read().expect("read lock");
    if std::env::args().nth(2).as_deref()==Some("expect-empty") {
        assert!(locked.freshest().expect("frame metadata").is_none());println!("NO_FRAME");return;
    }
    let (meta,slot)=locked.freshest().expect("frame metadata").expect("frame");
    if let Some(ms)=std::env::args().nth(2) {
        use std::io::Write;
        println!("LOCKED"); std::io::stdout().flush().unwrap();
        std::thread::sleep(std::time::Duration::from_millis(ms.parse().unwrap()));
    }
    let mut pixels=vec![0;reader.pixel_size];
    locked.copy_span(slot,0,&mut pixels).expect("copy frame");
    assert!(pixels.iter().all(|x|*x==pixels[0]),"torn uniform frame");
    println!("{} {} {} {}",meta.seq,meta.w,meta.h,pixels[0]);
}
