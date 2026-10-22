//! Descriptor-relative reads under a host-created private job root.
use std::ffi::CString;
use std::fs::{self, File, OpenOptions};
use std::io::Read;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::{Component, Path, PathBuf};
use crate::inspection_host::{budget, wire, PATCH_PIXELS};
use wire::refinement::Request;

pub struct Root { pub path:PathBuf, directory:File }
impl Root {
    pub fn create(epoch:[u8;16])->Result<Self,String>{
        let base=std::env::temp_dir().canonicalize().map_err(|e|e.to_string())?;
        let hex:String=epoch.iter().map(|b|format!("{b:02x}")).collect();
        let path=base.join(format!("lumaretouch-inspection-host-{}-{hex}",std::process::id()));
        fs::DirBuilder::new().mode(0o700).create(&path).map_err(|e|e.to_string())?;
        let directory=match OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY|libc::O_NOFOLLOW|libc::O_CLOEXEC).open(&path){
            Ok(f)=>f,Err(e)=>{let _=fs::remove_dir(&path);return Err(e.to_string());}
        };
        let m=directory.metadata().map_err(|e|e.to_string())?;
        if m.uid()!=unsafe{libc::geteuid()} || m.mode()&0o077!=0{return Err("inspection root ownership/mode invalid".into());}
        Ok(Self{path,directory})
    }
    pub fn cleanup(&self)->Result<(),String>{
        match fs::remove_dir_all(&self.path){Ok(())=>Ok(()),Err(e) if e.kind()==std::io::ErrorKind::NotFound=>Ok(()),Err(e)=>Err(e.to_string())}
    }
    /// A complete LRCP packet at a path derived solely from a registered native
    /// identity. No engine-provided path, mmap, SHM mutation or unbounded read.
    pub fn read_capture(&self,expected:&crate::capture_wire::Identity)->Result<Vec<u8>,String>{
        use crate::capture_wire::{HEADER_BYTES,MAX_PAYLOAD};
        let header=expected.header().map_err(str::to_owned)?;
        let payload=expected.payload_len().map_err(str::to_owned)?;
        if payload>MAX_PAYLOAD{return Err("source patch capture exceeds 128 MiB budget".into());}
        let total=HEADER_BYTES.checked_add(payload).ok_or("capture packet length overflow")?;
        let job=format!("lumaretouch-source-patch-{}-{}",crate::frame_identity::hex(expected.capture),expected.ticket);
        let name=CString::new(job).map_err(|_|"invalid source patch capture name")?;
        let fd=unsafe{libc::openat(self.directory.as_raw_fd(),name.as_ptr(),libc::O_RDONLY|libc::O_DIRECTORY|libc::O_NOFOLLOW|libc::O_CLOEXEC|libc::O_NONBLOCK)};
        if fd<0{return Err(std::io::Error::last_os_error().to_string());}
        let directory=unsafe{File::from_raw_fd(fd)};
        let dm=directory.metadata().map_err(|e|e.to_string())?;
        if !dm.is_dir() || dm.uid()!=unsafe{libc::geteuid()} || dm.mode()&0o7777!=0o700{
            return Err("source patch capture directory ownership/mode invalid".into());
        }
        let name=CString::new("capture.lrcp").unwrap();
        let fd=unsafe{libc::openat(directory.as_raw_fd(),name.as_ptr(),libc::O_RDONLY|libc::O_NOFOLLOW|libc::O_CLOEXEC|libc::O_NONBLOCK)};
        if fd<0{return Err(std::io::Error::last_os_error().to_string());}
        let mut file=unsafe{File::from_raw_fd(fd)};
        let info=file.metadata().map_err(|e|e.to_string())?;
        if !info.is_file() || info.uid()!=unsafe{libc::geteuid()} || info.mode()&0o7777!=0o600 || info.nlink()!=1 || info.len()!=total as u64{
            return Err("source patch capture type/owner/mode/length invalid".into());
        }
        let mut prefix=[0u8;HEADER_BYTES];file.read_exact(&mut prefix).map_err(|e|e.to_string())?;
        if prefix!=header{return Err("source patch capture LRCP identity/header mismatch".into());}
        let mut bytes=Vec::new();bytes.try_reserve_exact(total).map_err(|e|e.to_string())?;
        bytes.extend_from_slice(&prefix);bytes.resize(total,0);
        file.read_exact(&mut bytes[HEADER_BYTES..]).map_err(|e|e.to_string())?;
        let mut extra=[0u8;1];
        if file.read(&mut extra).map_err(|e|e.to_string())?!=0{return Err("source patch capture grew during read".into());}
        let after=file.metadata().map_err(|e|e.to_string())?;
        if after.len()!=info.len() || after.mode()!=info.mode() || after.uid()!=info.uid() || after.nlink()!=1
            || after.mtime()!=info.mtime() || after.mtime_nsec()!=info.mtime_nsec()
            || after.ctime()!=info.ctime() || after.ctime_nsec()!=info.ctime_nsec(){
            return Err("source patch capture changed during read".into());
        }
        Ok(bytes)
    }
    pub fn read(&self,path:&Path,epoch:[u8;16],request:&Request)->Result<Vec<u8>,String>{
        let relative=path.strip_prefix(&self.path).map_err(|_|"inspection result escapes its host root")?;
        let parts:Vec<_>=relative.components().collect();
        let job=match &parts[..]{
            [Component::Normal(job),Component::Normal(file)] if *file==std::ffi::OsStr::new("result.lrif")=>job.to_str().ok_or("inspection job name is not UTF-8")?,
            _=>return Err("inspection result path is not a fixed job result".into()),
        };
        if !job.starts_with("lumaretouch-inspection-") || !job.bytes().all(|b|b.is_ascii_alphanumeric() || b==b'-' || b==b'_'){
            return Err("inspection job name is invalid".into());
        }
        let name=CString::new(job).map_err(|_|"invalid inspection job name")?;
        let fd=unsafe{libc::openat(self.directory.as_raw_fd(),name.as_ptr(),libc::O_RDONLY|libc::O_DIRECTORY|libc::O_NOFOLLOW|libc::O_CLOEXEC|libc::O_NONBLOCK)};
        if fd<0{return Err(std::io::Error::last_os_error().to_string());}
        let directory=unsafe{File::from_raw_fd(fd)};
        let dm=directory.metadata().map_err(|e|e.to_string())?;
        if !dm.is_dir() || dm.uid()!=unsafe{libc::geteuid()} || dm.mode()&0o077!=0{return Err("inspection job ownership/mode invalid".into());}
        let name=CString::new("result.lrif").unwrap();
        let fd=unsafe{libc::openat(directory.as_raw_fd(),name.as_ptr(),libc::O_RDONLY|libc::O_NOFOLLOW|libc::O_CLOEXEC|libc::O_NONBLOCK)};
        if fd<0{return Err(std::io::Error::last_os_error().to_string());}
        let mut file=unsafe{File::from_raw_fd(fd)};
        let info=file.metadata().map_err(|e|e.to_string())?;
        if !info.is_file() || info.uid()!=unsafe{libc::geteuid()} || info.len()>wire::HEADER_BYTES as u64+PATCH_PIXELS*4{
            return Err("inspection result type/length/owner invalid".into());
        }
        let mut prefix=[0u8;wire::HEADER_BYTES];file.read_exact(&mut prefix).map_err(|e|e.to_string())?;
        let header=wire::parse_header(&prefix,epoch,request,&budget(),PATCH_PIXELS*4)?;
        let total=wire::HEADER_BYTES.checked_add(header.payload_bytes).ok_or("inspection length overflow")?;
        if info.len()!=total as u64{return Err("inspection result file length mismatch".into());}
        let mut bytes=Vec::new();bytes.try_reserve_exact(total).map_err(|e|e.to_string())?;
        bytes.extend_from_slice(&prefix);bytes.resize(total,0);
        file.read_exact(&mut bytes[wire::HEADER_BYTES..]).map_err(|e|e.to_string())?;
        let mut extra=[0u8;1];
        if file.read(&mut extra).map_err(|e|e.to_string())?!=0{return Err("inspection result grew during read".into());}
        wire::parse_packet(&bytes,epoch,request,&budget(),PATCH_PIXELS*4)?;
        Ok(bytes)
    }
}

#[cfg(test)]
mod tests{
    use super::*;
    use wire::refinement::{Roi,Ticket};
    fn request()->Request{Request{ticket:Ticket{id:9007199254740993,document:2,source_generation:3,recipe:4,viewport:5},
        source_width:10,source_height:10,canvas_width:10,canvas_height:10,
        roi:Roi{x:1,y:2,width:2,height:1},estimated_live_bytes:1000}}
    fn packet()->Vec<u8>{include_str!("../../../core/inspection/packet-v1.hex").trim().as_bytes().chunks_exact(2)
        .map(|p|u8::from_str_radix(std::str::from_utf8(p).unwrap(),16).unwrap()).collect()}
    fn job(root:&Root)->PathBuf{let dir=root.path.join("lumaretouch-inspection-test");fs::DirBuilder::new().mode(0o700).create(&dir).unwrap();dir}
    #[test] fn inspection_descriptor_reader_accepts_exact_packet(){
        let root=Root::create([31;16]).unwrap();let dir=job(&root);let path=dir.join("result.lrif");
        fs::write(&path,packet()).unwrap();assert_eq!(root.read(&path,[7;16],&request()).unwrap(),packet());
        root.cleanup().unwrap();root.cleanup().unwrap();
    }
    #[test] fn inspection_descriptor_reader_rejects_symlink_and_fifo_without_blocking(){
        let root=Root::create([32;16]).unwrap();let dir=job(&root);let path=dir.join("result.lrif");
        std::os::unix::fs::symlink("/dev/null",&path).unwrap();assert!(root.read(&path,[7;16],&request()).is_err());
        fs::remove_file(&path).unwrap();let name=CString::new(path.to_str().unwrap()).unwrap();
        assert_eq!(unsafe{libc::mkfifo(name.as_ptr(),0o600)},0);
        assert!(root.read(&path,[7;16],&request()).is_err());root.cleanup().unwrap();
    }
    #[test] fn inspection_descriptor_reader_rejects_escaping_and_oversized_results(){
        let root=Root::create([33;16]).unwrap();let dir=job(&root);let path=dir.join("result.lrif");
        assert!(root.read(Path::new("/tmp/result.lrif"),[7;16],&request()).is_err());
        File::create(&path).unwrap().set_len(129+PATCH_PIXELS*4).unwrap();
        assert!(root.read(&path,[7;16],&request()).is_err());root.cleanup().unwrap();
    }
    fn capture_identity()->crate::capture_wire::Identity{crate::capture_wire::Identity{
        epoch:[1;16],instance:[2;16],capture:[3;16],seq:1,generation:7,document:123,ticket:9,
        width:2,height:1,presentation_width:2,presentation_height:1}}
    fn capture_job(root:&Root,id:&crate::capture_wire::Identity)->PathBuf{
        let dir=root.path.join(format!("lumaretouch-source-patch-{}-{}",crate::frame_identity::hex(id.capture),id.ticket));
        fs::DirBuilder::new().mode(0o700).create(&dir).unwrap();dir
    }
    fn capture_packet(id:&crate::capture_wire::Identity)->Vec<u8>{
        let mut bytes=id.header().unwrap().to_vec();bytes.resize(crate::capture_wire::HEADER_BYTES+id.payload_len().unwrap(),37);bytes
    }
    fn write_capture(path:&Path,bytes:&[u8]){
        use std::io::Write;
        let mut f=OpenOptions::new().write(true).create_new(true).mode(0o600).open(path).unwrap();f.write_all(bytes).unwrap();
    }
    #[test] fn capture_reader_accepts_exact_private_lrcp_and_rejects_other_identity(){
        let root=Root::create([41;16]).unwrap();let id=capture_identity();let dir=capture_job(&root,&id);let path=dir.join("capture.lrcp");
        let bytes=capture_packet(&id);write_capture(&path,&bytes);assert_eq!(root.read_capture(&id).unwrap(),bytes);
        let mut wrong=id.clone();wrong.generation+=1;assert!(root.read_capture(&wrong).is_err());
        wrong=id.clone();wrong.instance=[4;16];assert!(root.read_capture(&wrong).is_err());
        wrong=id;wrong.ticket+=1;assert!(root.read_capture(&wrong).is_err());root.cleanup().unwrap();
    }
    #[test] fn capture_reader_rejects_file_and_directory_symlinks_and_fifo_without_blocking(){
        let root=Root::create([42;16]).unwrap();let id=capture_identity();let dir=capture_job(&root,&id);let path=dir.join("capture.lrcp");
        std::os::unix::fs::symlink("/dev/null",&path).unwrap();assert!(root.read_capture(&id).is_err());fs::remove_file(&path).unwrap();
        let name=CString::new(path.to_str().unwrap()).unwrap();assert_eq!(unsafe{libc::mkfifo(name.as_ptr(),0o600)},0);
        assert!(root.read_capture(&id).is_err());fs::remove_file(&path).unwrap();fs::remove_dir(&dir).unwrap();
        std::os::unix::fs::symlink(&root.path,&dir).unwrap();assert!(root.read_capture(&id).is_err());root.cleanup().unwrap();
    }
    #[test] fn capture_reader_rejects_permissions_lengths_reserved_bytes_and_links(){
        use std::os::unix::fs::PermissionsExt;
        let root=Root::create([43;16]).unwrap();let id=capture_identity();let dir=capture_job(&root,&id);let path=dir.join("capture.lrcp");
        let bytes=capture_packet(&id);write_capture(&path,&bytes);
        fs::set_permissions(&path,fs::Permissions::from_mode(0o644)).unwrap();assert!(root.read_capture(&id).is_err());
        fs::set_permissions(&path,fs::Permissions::from_mode(0o600)).unwrap();
        fs::set_permissions(&dir,fs::Permissions::from_mode(0o755)).unwrap();assert!(root.read_capture(&id).is_err());
        fs::set_permissions(&dir,fs::Permissions::from_mode(0o700)).unwrap();
        let link=dir.join("other");fs::hard_link(&path,&link).unwrap();assert!(root.read_capture(&id).is_err());fs::remove_file(link).unwrap();
        for invalid in [bytes[..bytes.len()-1].to_vec(),[bytes.as_slice(),&[0]].concat(),{
            let mut v=bytes.clone();v[112]=1;v
        }]{fs::remove_file(&path).unwrap();write_capture(&path,&invalid);assert!(root.read_capture(&id).is_err());}
        fs::remove_file(&path).unwrap();let mut huge=id;huge.width=u32::MAX;
        assert!(root.read_capture(&huge).is_err());root.cleanup().unwrap();
    }
}
