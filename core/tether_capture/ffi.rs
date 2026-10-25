// SPDX-License-Identifier: LGPL-2.0-or-later
// Minimal ABI declarations translated from libgphoto2's public headers.
// Header authors: Scott Fritzinger (2000), Lutz Mueller (2001),
// Marcus Meissner (2008-2009). See THIRD_PARTY.md for provenance/licences.
// No driver implementation or command-line/sample transfer policy is copied.
use crate::{Error, ErrorKind, Result};
use libc::{c_char, c_int, c_void};
use std::{ffi::CStr, ptr};

macro_rules! opaque { ($($name:ident),+) => { $(#[repr(C)] pub struct $name { _opaque: [u8; 0] })+ }; }
opaque!(Camera, Context, List, AbilitiesList, PortInfoList, PortInfo, Widget, CameraFile);

#[repr(C)]
#[derive(Clone, Copy)]
pub struct CameraAbilities {
    pub model: [c_char; 128],
    pub status: c_int,
    pub port: c_int,
    pub speed: [c_int; 64],
    pub operations: c_int,
    pub file_operations: c_int,
    pub folder_operations: c_int,
    pub usb_vendor: c_int,
    pub usb_product: c_int,
    pub usb_class: c_int,
    pub usb_subclass: c_int,
    pub usb_protocol: c_int,
    pub library: [c_char; 1024],
    pub id: [c_char; 1024],
    pub device_type: c_int,
    pub reserved: [c_int; 7],
}
#[repr(C)]
pub struct CameraFilePath { pub name: [c_char; 128], pub folder: [c_char; 1024] }
pub type HandlerSize = unsafe extern "C" fn(*mut c_void, *mut u64) -> c_int;
pub type HandlerIo = unsafe extern "C" fn(*mut c_void, *mut u8, *mut u64) -> c_int;
#[repr(C)]
pub struct CameraFileHandler {
    pub size: Option<HandlerSize>,
    pub read: Option<HandlerIo>,
    pub write: Option<HandlerIo>,
}
pub type CancelFn = unsafe extern "C" fn(*mut Context, *mut c_void) -> c_int;

pub const NOT_SUPPORTED: i32 = -6;
pub const CANCEL: i32 = -112;
pub const IO_WRITE: i32 = -35;
pub const BAD_PARAMETERS: i32 = -2;
pub const PORT_USB: i32 = 1 << 2;
pub const CAPTURE_IMAGE: i32 = 1;
pub const CAPTURE_PREVIEW: i32 = 1 << 3;
pub const CONFIG: i32 = 1 << 4;
pub const TRIGGER_CAPTURE: i32 = 1 << 5;
pub const FILE_TYPE_NORMAL: i32 = 1;

struct Library(*mut c_void);
struct Libraries { camera: Library, port: Library }
impl Library {
    fn open(name: &'static [u8]) -> Result<Self> {
        // Fixed ABI SONAME, no caller-supplied library path or installation.
        let handle = unsafe { libc::dlopen(name.as_ptr().cast(), libc::RTLD_NOW | libc::RTLD_LOCAL) };
        if handle.is_null() {
            return Err(Error::new(ErrorKind::Unavailable, "load_driver", format!(
                "Cannot load {}: {}", String::from_utf8_lossy(&name[..name.len()-1]), loader_error())));
        }
        Ok(Self(handle))
    }
    fn symbol(&self, name: &'static [u8]) -> Result<*mut c_void> {
        unsafe { libc::dlerror(); }
        let value = unsafe { libc::dlsym(self.0, name.as_ptr().cast()) };
        let error = unsafe { libc::dlerror() };
        if !error.is_null() || value.is_null() {
            return Err(Error::new(ErrorKind::Unavailable, "load_driver", format!(
                "Required public symbol missing: {}", String::from_utf8_lossy(&name[..name.len()-1]))));
        }
        Ok(value)
    }
}
impl Drop for Library { fn drop(&mut self) { unsafe { libc::dlclose(self.0); } } }
fn loader_error() -> String {
    let p = unsafe { libc::dlerror() };
    if p.is_null() { "dynamic loader returned no diagnostic".into() }
    else { unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned() }
}

// Every symbol is resolved with its exact public prototype. No guessed ABI,
// variadic call, private Camera access, or transmute to an unconstrained generic.
macro_rules! api {
    ($($lib:ident : $name:ident ($($arg:ty),*) -> $ret:ty;)+) => {
        pub struct Api {
            $(pub $name: unsafe extern "C" fn($($arg),*) -> $ret,)+
            _camera: Library,
            _port: Library,
        }
        impl Api {
            pub fn load() -> Result<Self> {
                let port = Library::open(b"libgphoto2_port.so.12\0")?;
                let libraries = Libraries { camera: Library::open(b"libgphoto2.so.6\0")?, port };
                Ok(Self {
                    $($name: unsafe { std::mem::transmute::<*mut c_void, unsafe extern "C" fn($($arg),*) -> $ret>(
                        libraries.$lib.symbol(concat!(stringify!($name), "\0").as_bytes())?) },)+
                    _camera: libraries.camera, _port: libraries.port,
                })
            }
        }
    }
}
api! {
    camera: gp_context_new() -> *mut Context;
    camera: gp_context_unref(*mut Context) -> ();
    camera: gp_context_set_cancel_func(*mut Context, Option<CancelFn>, *mut c_void) -> ();
    camera: gp_list_new(*mut *mut List) -> c_int;
    camera: gp_list_free(*mut List) -> c_int;
    camera: gp_list_count(*mut List) -> c_int;
    camera: gp_list_get_name(*mut List, c_int, *mut *const c_char) -> c_int;
    camera: gp_list_get_value(*mut List, c_int, *mut *const c_char) -> c_int;
    camera: gp_camera_autodetect(*mut List, *mut Context) -> c_int;
    camera: gp_abilities_list_new(*mut *mut AbilitiesList) -> c_int;
    camera: gp_abilities_list_free(*mut AbilitiesList) -> c_int;
    camera: gp_abilities_list_load(*mut AbilitiesList, *mut Context) -> c_int;
    camera: gp_abilities_list_lookup_model(*mut AbilitiesList, *const c_char) -> c_int;
    camera: gp_abilities_list_get_abilities(*mut AbilitiesList, c_int, *mut CameraAbilities) -> c_int;
    port: gp_port_info_list_new(*mut *mut PortInfoList) -> c_int;
    port: gp_port_info_list_free(*mut PortInfoList) -> c_int;
    port: gp_port_info_list_load(*mut PortInfoList) -> c_int;
    port: gp_port_info_list_lookup_path(*mut PortInfoList, *const c_char) -> c_int;
    port: gp_port_info_list_get_info(*mut PortInfoList, c_int, *mut *mut PortInfo) -> c_int;
    port: gp_port_info_get_type(*mut PortInfo, *mut c_int) -> c_int;
    camera: gp_camera_new(*mut *mut Camera) -> c_int;
    camera: gp_camera_set_abilities(*mut Camera, CameraAbilities) -> c_int;
    camera: gp_camera_get_abilities(*mut Camera, *mut CameraAbilities) -> c_int;
    camera: gp_camera_set_port_info(*mut Camera, *mut PortInfo) -> c_int;
    camera: gp_camera_init(*mut Camera, *mut Context) -> c_int;
    camera: gp_camera_exit(*mut Camera, *mut Context) -> c_int;
    camera: gp_camera_unref(*mut Camera) -> c_int;
    camera: gp_camera_wait_for_event(*mut Camera, c_int, *mut c_int, *mut *mut c_void, *mut Context) -> c_int;
    camera: gp_camera_get_config(*mut Camera, *mut *mut Widget, *mut Context) -> c_int;
    camera: gp_widget_free(*mut Widget) -> c_int;
    camera: gp_widget_get_child_by_name(*mut Widget, *const c_char, *mut *mut Widget) -> c_int;
    camera: gp_widget_get_type(*mut Widget, *mut c_int) -> c_int;
    camera: gp_widget_get_label(*mut Widget, *mut *const c_char) -> c_int;
    camera: gp_widget_get_readonly(*mut Widget, *mut c_int) -> c_int;
    camera: gp_widget_get_value(*mut Widget, *mut c_void) -> c_int;
    camera: gp_file_new_from_handler(*mut *mut CameraFile, *mut CameraFileHandler, *mut c_void) -> c_int;
    camera: gp_file_unref(*mut CameraFile) -> c_int;
    camera: gp_file_get_mime_type(*mut CameraFile, *mut *const c_char) -> c_int;
    camera: gp_camera_file_get(*mut Camera, *const c_char, *const c_char, c_int, *mut CameraFile, *mut Context) -> c_int;
    camera: gp_camera_capture(*mut Camera, c_int, *mut CameraFilePath, *mut Context) -> c_int;
    camera: gp_camera_trigger_capture(*mut Camera, *mut Context) -> c_int;
    camera: gp_camera_capture_preview(*mut Camera, *mut CameraFile, *mut Context) -> c_int;
}

pub fn check(operation: &'static str, code: i32) -> Result<i32> {
    if code >= 0 { return Ok(code); }
    let kind = match code {
        -6 => ErrorKind::Unsupported,
        -10 => ErrorKind::Timeout,
        -53 | -60 | -110 => ErrorKind::Busy,
        -52 | -105 => ErrorKind::Disconnected,
        -112 => ErrorKind::Cancelled,
        _ => ErrorKind::Native,
    };
    Err(Error { kind, operation, native_code: Some(code),
        message: format!("libgphoto2 returned {code}"), outcome_unknown: false })
}

pub unsafe fn text(pointer: *const c_char, max: usize, operation: &'static str) -> Result<String> {
    if pointer.is_null() { return Err(Error::new(ErrorKind::Protocol, operation, "Null native string")); }
    // Pointer and NUL termination are part of the trusted public libgphoto2 ABI.
    let length = libc::strnlen(pointer, max + 1);
    if length > max { return Err(Error::new(ErrorKind::Protocol, operation, "Native string too long")); }
    let data = std::slice::from_raw_parts(pointer.cast::<u8>(), length);
    std::str::from_utf8(data).map(str::to_owned)
        .map_err(|_| Error::new(ErrorKind::Protocol, operation, "Non-UTF-8 native text is not supported losslessly"))
}
pub fn fixed_text(chars: &[c_char], operation: &'static str) -> Result<String> {
    let end = chars.iter().position(|v| *v == 0)
        .ok_or_else(|| Error::new(ErrorKind::Protocol, operation, "Unterminated native path"))?;
    String::from_utf8(chars[..end].iter().map(|v| *v as u8).collect())
        .map_err(|_| Error::new(ErrorKind::Protocol, operation, "Non-UTF-8 camera path"))
}

/// Copy event content before releasing this allocation with the same C runtime.
pub struct EventAllocation(pub *mut c_void);
impl Drop for EventAllocation { fn drop(&mut self) { unsafe { libc::free(self.0); } } }

pub fn null<T>() -> *mut T { ptr::null_mut() }
