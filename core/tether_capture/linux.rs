// SPDX-License-Identifier: GPL-3.0-or-later
use crate::{ffi::{self, check, null}, transfer::{self, Control, Transfer}, *};
use libc::{c_int, c_void};
use std::{ffi::CString, mem, rc::Rc};

const READ_TIMEOUT: Duration = Duration::from_secs(20);
const CAPTURE_TIMEOUT: Duration = Duration::from_secs(60);
const MAX_TRANSFER_TIME: Duration = Duration::from_secs(600);
const MAX_RETAINED_CALLBACKS: usize = 4096;

// Handler/private pointers can outlive our CameraFile reference if a camlib
// caches it. Preserve stable, retired callback boxes until camera teardown.
struct RetainedTransfer { sink: Box<Transfer>, _handler: Box<ffi::CameraFileHandler> }

struct Owned<T> { raw: *mut T, release: unsafe extern "C" fn(*mut T) -> c_int }
impl<T> Owned<T> {
    fn new(raw: *mut T, release: unsafe extern "C" fn(*mut T) -> c_int, operation: &'static str) -> Result<Self> {
        if raw.is_null() { return Err(Error::new(ErrorKind::Protocol, operation, "Native success returned a null object")); }
        Ok(Self { raw, release })
    }
}
impl<T> Drop for Owned<T> { fn drop(&mut self) { unsafe { (self.release)(self.raw); } } }

struct CameraHandle { raw: *mut ffi::Camera, context: *mut ffi::Context, api: Rc<ffi::Api>, exit_needed: bool }
impl Drop for CameraHandle {
    fn drop(&mut self) { unsafe {
        if self.exit_needed { (self.api.gp_camera_exit)(self.raw, self.context); }
        (self.api.gp_camera_unref)(self.raw);
    } }
}

/// Load/construct on the dedicated device worker, not on the UI thread.
/// `Rc` prevents this handle, camera/context and dynamic libraries moving between
/// threads or being concurrently shared. No device calls occur in `load`.
pub struct LinuxGphotoDevice {
    api: Rc<ffi::Api>,
    context: *mut ffi::Context,
    camera: Option<CameraHandle>,
    selected: Option<DeviceId>,
    caps: Option<DeviceCapabilities>,
    control: Box<Control>,
    retained: Vec<RetainedTransfer>,
}
impl LinuxGphotoDevice {
    pub fn load() -> Result<Self> {
        let api = Rc::new(ffi::Api::load()?);
        let context = unsafe { (api.gp_context_new)() };
        if context.is_null() { return Err(Error::new(ErrorKind::Unavailable, "load_driver", "Cannot create libgphoto2 context")); }
        let mut control = Box::new(Control::new(CancellationToken::default(), READ_TIMEOUT));
        unsafe { (api.gp_context_set_cancel_func)(context, Some(transfer::cancel_callback), (&mut *control as *mut Control).cast()); }
        Ok(Self { api, context, camera: None, selected: None, caps: None, control, retained: Vec::new() })
    }
    fn begin(&mut self, cancel: &CancellationToken, timeout: Duration) -> Result<()> {
        // Replace contents, never move the pointee registered with GPContext.
        *self.control = Control::new(cancel.clone(), timeout);
        self.control.check()
    }
    fn camera(&self) -> Result<*mut ffi::Camera> {
        self.camera.as_ref().map(|c| c.raw)
            .ok_or_else(|| Error::new(ErrorKind::Closed, "device", "No selected camera is open"))
    }
    fn require(&self, support: Support, operation: &'static str) -> Result<()> {
        if !support.can_request() { return Err(Error::new(ErrorKind::Unsupported, operation, "Driver has not advertised this optional operation")); }
        Ok(())
    }
    fn update(support: &mut Support, code: i32) {
        if code >= 0 { *support = Support::Verified; }
        else if code == ffi::NOT_SUPPORTED { *support = Support::Unsupported; }
    }
    fn native_result(&self, operation: &'static str, code: i32) -> Result<i32> {
        // The driver can report generic cancellation for our elapsed deadline.
        if code < 0 { self.control.check()?; }
        check(operation, code)
    }
    fn reserve_callback(&mut self) -> Result<()> {
        if self.retained.len() >= MAX_RETAINED_CALLBACKS {
            return Err(Error::new(ErrorKind::SizeLimit, "transfer", "Session callback budget exhausted; explicitly close and start a new session"));
        }
        self.retained.try_reserve(1).map_err(|_| Error::new(ErrorKind::SizeLimit, "transfer", "Cannot reserve callback lifetime slot"))
    }
    fn mime(&self, file: *mut ffi::CameraFile) -> Option<String> {
        let mut value = std::ptr::null();
        if unsafe { (self.api.gp_file_get_mime_type)(file, &mut value) } < 0 { return None; }
        unsafe { ffi::text(value, 128, "mime") }.ok().filter(|v| v.contains('/') && !v.chars().any(char::is_control))
    }
    fn detected(&mut self, cancel: &CancellationToken) -> Result<Vec<DeviceId>> {
        self.begin(cancel, READ_TIMEOUT)?;
        let mut raw = null();
        check("enumerate_list", unsafe { (self.api.gp_list_new)(&mut raw) })?;
        let list = Owned::new(raw, self.api.gp_list_free, "enumerate_list")?;
        self.native_result("enumerate", unsafe { (self.api.gp_camera_autodetect)(list.raw, self.context) })?;
        let count = check("enumerate_count", unsafe { (self.api.gp_list_count)(list.raw) })?;
        if count > 256 { return Err(Error::new(ErrorKind::Protocol, "enumerate", "Too many detected devices")); }
        let mut devices = Vec::new();
        for index in 0..count {
            self.control.check()?;
            let (mut model, mut port) = (std::ptr::null(), std::ptr::null());
            check("enumerate_model", unsafe { (self.api.gp_list_get_name)(list.raw, index, &mut model) })?;
            check("enumerate_port", unsafe { (self.api.gp_list_get_value)(list.raw, index, &mut port) })?;
            let device = DeviceId { model: unsafe { ffi::text(model, 127, "enumerate_model") }?,
                port: unsafe { ffi::text(port, 256, "enumerate_port") }? };
            if valid_usb_port(&device.port) && !devices.contains(&device) { devices.push(device); }
        }
        Ok(devices)
    }
}

impl TetherDevicePort for LinuxGphotoDevice {
    fn enumerate(&mut self, cancel: &CancellationToken) -> Result<Vec<DeviceId>> {
        if self.camera.is_some() { return Err(Error::new(ErrorKind::AlreadyOpen, "enumerate", "Close the selected session before refreshing devices")); }
        self.detected(cancel)
    }

    fn open_selected(&mut self, selected: &DeviceId, cancel: &CancellationToken) -> Result<DeviceCapabilities> {
        if self.camera.is_some() { return Err(Error::new(ErrorKind::AlreadyOpen, "open", "Close the current device before selecting another")); }
        if !self.detected(cancel)?.contains(selected) {
            return Err(Error::new(ErrorKind::StaleSelection, "open", "Selected model/USB address is no longer detected; select again"));
        }
        self.begin(cancel, READ_TIMEOUT)?;
        let model = CString::new(selected.model.as_bytes()).map_err(|_| Error::new(ErrorKind::InvalidInput, "open", "Invalid model"))?;
        let port = CString::new(selected.port.as_bytes()).map_err(|_| Error::new(ErrorKind::InvalidInput, "open", "Invalid USB address"))?;
        let mut al = null();
        check("abilities_new", unsafe { (self.api.gp_abilities_list_new)(&mut al) })?;
        let al = Owned::new(al, self.api.gp_abilities_list_free, "abilities_new")?;
        self.native_result("abilities_load", unsafe { (self.api.gp_abilities_list_load)(al.raw, self.context) })?;
        let model_index = check("abilities_lookup", unsafe { (self.api.gp_abilities_list_lookup_model)(al.raw, model.as_ptr()) })?;
        // All fields are C integers and char arrays, hence zero is a valid value.
        let mut abilities: ffi::CameraAbilities = unsafe { mem::zeroed() };
        check("abilities_get", unsafe { (self.api.gp_abilities_list_get_abilities)(al.raw, model_index, &mut abilities) })?;
        if abilities.port & ffi::PORT_USB == 0 || abilities.device_type != 0 {
            return Err(Error::new(ErrorKind::Unsupported, "open", "Detected driver is not a USB still-camera driver"));
        }
        let mut pl = null();
        check("ports_new", unsafe { (self.api.gp_port_info_list_new)(&mut pl) })?;
        let pl = Owned::new(pl, self.api.gp_port_info_list_free, "ports_new")?;
        check("ports_load", unsafe { (self.api.gp_port_info_list_load)(pl.raw) })?;
        let port_index = check("port_lookup", unsafe { (self.api.gp_port_info_list_lookup_path)(pl.raw, port.as_ptr()) })?;
        let mut info = null();
        check("port_get", unsafe { (self.api.gp_port_info_list_get_info)(pl.raw, port_index, &mut info) })?;
        if info.is_null() { return Err(Error::new(ErrorKind::Protocol, "port_get", "Null port info")); }
        let mut port_type = 0;
        check("port_type", unsafe { (self.api.gp_port_info_get_type)(info, &mut port_type) })?;
        if port_type != ffi::PORT_USB { return Err(Error::new(ErrorKind::Unsupported, "open", "Only USB PTP camera ports are supported")); }
        let mut raw = null();
        check("camera_new", unsafe { (self.api.gp_camera_new)(&mut raw) })?;
        if raw.is_null() { return Err(Error::new(ErrorKind::Protocol, "open", "Null camera")); }
        let mut camera = CameraHandle { raw, context: self.context, api: self.api.clone(), exit_needed: false };
        // Both are set before init: libgphoto2 must NOT select the first camera.
        check("camera_set_model", unsafe { (self.api.gp_camera_set_abilities)(raw, abilities) })?;
        check("camera_set_port", unsafe { (self.api.gp_camera_set_port_info)(raw, info) })?;
        self.control.check()?;
        camera.exit_needed = true;
        self.native_result("camera_open", unsafe { (self.api.gp_camera_init)(raw, self.context) })?;
        self.control.check()?;
        check("camera_capabilities", unsafe { (self.api.gp_camera_get_abilities)(raw, &mut abilities) })?;
        let caps = capabilities_from_flags(abilities.operations);
        self.camera = Some(camera);
        self.selected = Some(selected.clone());
        self.caps = Some(caps.clone());
        Ok(caps)
    }

    fn capabilities(&self) -> Result<DeviceCapabilities> {
        self.camera()?;
        self.caps.clone().ok_or_else(|| Error::new(ErrorKind::Closed, "capabilities", "No open camera"))
    }

    fn read_settings(&mut self, cancel: &CancellationToken) -> Result<Vec<CameraSetting>> {
        let camera = self.camera()?;
        self.begin(cancel, READ_TIMEOUT)?;
        if self.capabilities()?.settings == Support::Unsupported {
            return Err(Error::new(ErrorKind::Unsupported, "read_settings", "Camera settings are unsupported"));
        }
        let mut root = null();
        let code = unsafe { (self.api.gp_camera_get_config)(camera, &mut root, self.context) };
        // Some drivers return a partially allocated tree on failure.
        let root_guard = if root.is_null() { None } else { Some(Owned::new(root, self.api.gp_widget_free, "read_settings")?) };
        Self::update(&mut self.caps.as_mut().unwrap().settings, code);
        self.native_result("read_settings", code)?;
        let root = root_guard.ok_or_else(|| Error::new(ErrorKind::Protocol, "read_settings", "Null configuration tree"))?;
        let mut output = Vec::new();
        // Bounded, read-only subset; no traversal of buttons or configuration write.
        for key in ["aperture", "f-number", "shutterspeed", "shutterspeed2", "iso", "exposurecompensation",
                    "batterylevel", "capturetarget", "imageformat", "imagequality"] {
            self.control.check()?;
            let name = CString::new(key).unwrap();
            let mut widget = null();
            let found = unsafe { (self.api.gp_widget_get_child_by_name)(root.raw, name.as_ptr(), &mut widget) };
            if found < 0 { continue; }
            if widget.is_null() { return Err(Error::new(ErrorKind::Protocol, "read_settings", "Null setting widget")); }
            let (mut kind, mut readonly) = (0, 0);
            check("setting_type", unsafe { (self.api.gp_widget_get_type)(widget, &mut kind) })?;
            let mut label = std::ptr::null();
            check("setting_label", unsafe { (self.api.gp_widget_get_label)(widget, &mut label) })?;
            check("setting_readonly", unsafe { (self.api.gp_widget_get_readonly)(widget, &mut readonly) })?;
            let label = unsafe { ffi::text(label, 512, "setting_label") }?;
            let value = match kind {
                2 | 5 | 6 => { // TEXT / RADIO / MENU: getter writes char*.
                    let mut value: *const libc::c_char = std::ptr::null();
                    check("setting_value", unsafe { (self.api.gp_widget_get_value)(widget, (&mut value as *mut *const libc::c_char).cast()) })?;
                    SettingValue::Text(unsafe { ffi::text(value, 4096, "setting_value") }?)
                }
                3 => {
                    let mut value = 0.0_f32;
                    check("setting_value", unsafe { (self.api.gp_widget_get_value)(widget, (&mut value as *mut f32).cast()) })?;
                    if !value.is_finite() { return Err(Error::new(ErrorKind::Protocol, "setting_value", "Nonfinite setting")); }
                    SettingValue::Number(value)
                }
                4 | 8 => {
                    let mut value = 0_i32;
                    check("setting_value", unsafe { (self.api.gp_widget_get_value)(widget, (&mut value as *mut i32).cast()) })?;
                    if kind == 4 { SettingValue::Toggle(value != 0) } else { SettingValue::Timestamp(value) }
                }
                _ => continue,
            };
            output.push(CameraSetting { key: key.into(), label, value, camera_read_only: readonly != 0 });
        }
        Ok(output)
    }

    fn wait_event(&mut self, timeout: Duration, cancel: &CancellationToken) -> Result<DeviceEvent> {
        let camera = self.camera()?;
        if timeout > MAX_WAIT { return Err(Error::new(ErrorKind::InvalidInput, "wait_event", "Poll at most 1000 ms per command")); }
        self.begin(cancel, timeout + Duration::from_secs(5))?;
        if self.capabilities()?.events == Support::Unsupported {
            return Err(Error::new(ErrorKind::Unsupported, "wait_event", "Driver does not deliver camera events"));
        }
        let mut event = 0;
        let mut data = null::<c_void>();
        let code = unsafe { (self.api.gp_camera_wait_for_event)(camera, timeout.as_millis() as c_int, &mut event, &mut data, self.context) };
        let data = ffi::EventAllocation(data); // Free on every path, including error.
        Self::update(&mut self.caps.as_mut().unwrap().events, code);
        self.native_result("wait_event", code)?;
        match event {
            0 => Ok(DeviceEvent::Unknown { description: if data.0.is_null() { None }
                else { Some(unsafe { ffi::text(data.0.cast(), 4096, "event_description") }?) } }),
            1 => Ok(DeviceEvent::Timeout),
            2 | 3 | 5 => {
                if data.0.is_null() { return Err(Error::new(ErrorKind::Protocol, "wait_event", "Missing file event payload")); }
                let path = unsafe { &*(data.0 as *const ffi::CameraFilePath) };
                let folder = ffi::fixed_text(&path.folder, "event_folder")?;
                let name = ffi::fixed_text(&path.name, "event_name")?;
                if event == 3 { return Ok(DeviceEvent::FolderAdded { folder, name }); }
                let object = CameraObject { folder, name }; object.validate()?;
                Ok(if event == 2 { DeviceEvent::FileAdded(object) } else { DeviceEvent::FileChanged(object) })
            }
            4 => Ok(DeviceEvent::CaptureComplete),
            _ => Err(Error::new(ErrorKind::Protocol, "wait_event", "Unknown event ABI value")),
        }
    }

    fn download_to_staging(&mut self, object: &CameraObject, request: &StagingRequest,
        cancel: &CancellationToken) -> Result<DownloadReceipt> {
        let camera = self.camera()?;
        object.validate()?;
        if self.capabilities()?.original_download == Support::Unsupported {
            return Err(Error::new(ErrorKind::Unsupported, "download", "Original retrieval is unsupported by this driver"));
        }
        if request.max_bytes == 0 || request.max_bytes > MAX_ORIGINAL_BYTES || request.timeout.is_zero()
            || request.timeout > MAX_TRANSFER_TIME {
            return Err(Error::new(ErrorKind::InvalidInput, "download", "Invalid byte limit or transfer timeout"));
        }
        self.begin(cancel, request.timeout)?;
        self.reserve_callback()?;
        let folder = CString::new(object.folder.as_bytes()).unwrap();
        let name = CString::new(object.name.as_bytes()).unwrap();
        let mut sink = Box::new(Transfer::disk(request, cancel)?);
        let mut handler = transfer::handler();
        let mut raw = null();
        check("transfer_file", unsafe { (self.api.gp_file_new_from_handler)(&mut raw,
            &mut *handler, (&mut *sink as *mut Transfer).cast()) })?;
        // No return between native get and retaining callback owner below.
        let file = Owned::new(raw, self.api.gp_file_unref, "transfer_file")?;
        let code = unsafe { (self.api.gp_camera_file_get)(camera, folder.as_ptr(), name.as_ptr(),
            ffi::FILE_TYPE_NORMAL, file.raw, self.context) };
        Self::update(&mut self.caps.as_mut().unwrap().original_download, code);
        let mime_type = if code >= 0 { self.mime(file.raw) } else { None };
        drop(file);
        self.retained.push(RetainedTransfer { sink, _handler: handler });
        let index = self.retained.len() - 1;
        let result = (|| {
            if let Some(error) = self.retained[index].sink.failure.take() { return Err(error); }
            self.native_result("download", code)?;
            self.retained[index].sink.complete_disk()
        })();
        self.retained[index].sink.retire();
        let (path, bytes, sha256_hex) = result?;
        Ok(DownloadReceipt { path, local_name: request.local_name.clone(), bytes, sha256_hex,
            mime_type, camera_object: object.clone() })
    }

    fn request_capture(&mut self, cancel: &CancellationToken) -> Result<CameraObject> {
        let camera = self.camera()?;
        self.require(self.capabilities()?.remote_capture, "remote_capture")?;
        self.begin(cancel, CAPTURE_TIMEOUT)?;
        let mut path: ffi::CameraFilePath = unsafe { mem::zeroed() };
        // Explicit one-shot command only. No automatic retry or trigger on connect.
        let code = unsafe { (self.api.gp_camera_capture)(camera, 0, &mut path, self.context) };
        Self::update(&mut self.caps.as_mut().unwrap().remote_capture, code);
        let result = (|| {
            self.native_result("remote_capture", code)?;
            let object = CameraObject { folder: ffi::fixed_text(&path.folder, "capture_folder")?,
                name: ffi::fixed_text(&path.name, "capture_name")? };
            object.validate()?;
            Ok(object)
        })();
        result.map_err(|mut error: Error| {
            // The command crossed the USB boundary. Even a malformed receipt can
            // represent a completed shutter. Only explicit unsupported is safe.
            error.outcome_unknown = code != ffi::NOT_SUPPORTED;
            error
        })
    }

    fn trigger_capture(&mut self, cancel: &CancellationToken) -> Result<()> {
        let camera = self.camera()?;
        self.require(self.capabilities()?.remote_trigger, "remote_trigger")?;
        self.begin(cancel, CAPTURE_TIMEOUT)?;
        // One explicit command, potentially one OR MORE images per camera mode.
        // No path is returned by this API. Only real FileAdded events can supply
        // later download occurrences. Never fall back to gp_camera_capture.
        let code = unsafe { (self.api.gp_camera_trigger_capture)(camera, self.context) };
        Self::update(&mut self.caps.as_mut().unwrap().remote_trigger, code);
        trigger_dispatch_result(code, self.native_result("remote_trigger", code))
    }

    fn capture_preview(&mut self, max_bytes: u64, cancel: &CancellationToken) -> Result<PreviewFrame> {
        let camera = self.camera()?;
        self.require(self.capabilities()?.preview, "preview")?;
        if max_bytes == 0 || max_bytes > MAX_PREVIEW_BYTES {
            return Err(Error::new(ErrorKind::InvalidInput, "preview", "Invalid preview byte limit"));
        }
        self.begin(cancel, Duration::from_secs(15))?;
        self.reserve_callback()?;
        let mut sink = Box::new(Transfer::memory(max_bytes, cancel));
        let mut handler = transfer::handler();
        let mut raw = null();
        check("preview_file", unsafe { (self.api.gp_file_new_from_handler)(&mut raw,
            &mut *handler, (&mut *sink as *mut Transfer).cast()) })?;
        let file = Owned::new(raw, self.api.gp_file_unref, "preview_file")?;
        let code = unsafe { (self.api.gp_camera_capture_preview)(camera, file.raw, self.context) };
        Self::update(&mut self.caps.as_mut().unwrap().preview, code);
        let mime = if code >= 0 { self.mime(file.raw) } else { None };
        drop(file);
        self.retained.push(RetainedTransfer { sink, _handler: handler });
        let index = self.retained.len() - 1;
        let result = (|| {
            if let Some(error) = self.retained[index].sink.failure.take() { return Err(error); }
            self.native_result("preview", code)?;
            self.retained[index].sink.complete_memory()
        })();
        self.retained[index].sink.retire();
        let bytes = result?;
        let mime_type = mime.filter(|v| matches!(v.as_str(), "image/jpeg" | "image/png"))
            .ok_or_else(|| Error::new(ErrorKind::Unsupported, "preview", "Preview is not a declared JPEG/PNG image"))?;
        let signature_ok = match mime_type.as_str() {
            "image/jpeg" => bytes.starts_with(&[0xff, 0xd8, 0xff]),
            "image/png" => bytes.starts_with(b"\x89PNG\r\n\x1a\n"),
            _ => false,
        };
        if !signature_ok { return Err(Error::new(ErrorKind::Protocol, "preview", "Preview signature does not match declared MIME")); }
        Ok(PreviewFrame { bytes, mime_type })
    }

    fn close(&mut self) -> Result<()> {
        let Some(mut camera) = self.camera.take() else { return Ok(()); };
        self.selected = None;
        self.caps = None;
        // Cancellation of the session must not skip driver resource cleanup.
        *self.control = Control::new(CancellationToken::default(), READ_TIMEOUT);
        camera.exit_needed = false;
        let code = unsafe { (self.api.gp_camera_exit)(camera.raw, self.context) };
        drop(camera); // unref even if exit fails; never reuse an uncertain handle.
        self.retained.clear(); // Only AFTER camera/filesystem/cache references die.
        check("close", code).map(|_| ())
    }
}
impl Drop for LinuxGphotoDevice {
    fn drop(&mut self) {
        let _ = self.close();
        // Cancel callback's box and library handles still live here.
        unsafe { (self.api.gp_context_set_cancel_func)(self.context, None, null());
            (self.api.gp_context_unref)(self.context); }
    }
}

pub(crate) fn valid_usb_port(port: &str) -> bool {
    let Some(tail) = port.strip_prefix("usb:") else { return false; };
    let Some((bus, device)) = tail.split_once(',') else { return false; };
    !bus.is_empty() && !device.is_empty() && bus.len() <= 3 && device.len() <= 3
        && bus.bytes().all(|v| v.is_ascii_digit()) && device.bytes().all(|v| v.is_ascii_digit())
        && bus.parse::<u16>().map_or(false, |v| v > 0 && v <= 255)
        && device.parse::<u16>().map_or(false, |v| v > 0 && v <= 255)
}
pub(crate) fn capabilities_from_flags(flags: i32) -> DeviceCapabilities {
    let advertised = |bit| if flags & bit != 0 { Support::DriverAdvertised } else { Support::Unknown };
    DeviceCapabilities { events: Support::Unknown, settings: advertised(ffi::CONFIG),
        remote_capture: advertised(ffi::CAPTURE_IMAGE), remote_trigger: advertised(ffi::TRIGGER_CAPTURE),
        preview: advertised(ffi::CAPTURE_PREVIEW),
        // Standard file retrieval has no affirmative ability bit. No assumption.
        original_download: Support::Unknown }
}

/// Called only after the explicit native trigger call crossed the FFI boundary.
pub(crate) fn trigger_dispatch_result(code: i32, result: Result<i32>) -> Result<()> {
    result.map(|_| ()).map_err(|mut error| {
        // A failed/cancelled/timed-out trigger can still have fired the shutter.
        error.outcome_unknown = code != ffi::NOT_SUPPORTED;
        error
    })
}
