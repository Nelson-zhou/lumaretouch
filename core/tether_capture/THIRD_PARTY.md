# Component provenance and notices

Source-authored, not built or distributed as a binary in this task. No camera
driver, SDK, package, model, sample executable or third-party implementation was
downloaded, installed or vendored.

## Public libgphoto2 / libgphoto2_port ABI

`ffi.rs` translates only the narrow public C type/function declarations and
constants needed for this adapter. The header copyright notices identify Scott
Fritzinger (2000), Lutz Mueller (2001), and Marcus Meissner (2008-2009). The public
headers license these declarations under LGPL version 2 or any later version;
`ffi.rs` is marked `LGPL-2.0-or-later`. The remaining original module code is
`GPL-3.0-or-later`, matching the repository. No sample's deletion policy was
copied; the adapter does not resolve a camera deletion symbol.

Primary sources inspected on 2026-10-25:

- https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-camera.h
- https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-abilities-list.h
- https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-file.h
- https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-context.h
- https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-widget.h
- https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-list.h
- https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-result.h
- https://github.com/gphoto/libgphoto2/blob/master/libgphoto2_port/gphoto2/gphoto2-port-info-list.h
- https://github.com/gphoto/libgphoto2/blob/master/libgphoto2_port/gphoto2/gphoto2-port-result.h
- https://github.com/gphoto/libgphoto2/blob/master/libgphoto2/gphoto2-file.c
- https://github.com/gphoto/libgphoto2/blob/master/libgphoto2/gphoto2-filesys.c
- https://github.com/gphoto/libgphoto2/blob/master/libgphoto2/gphoto2-camera.c

The linked upstream `COPYING` contains LGPL-2.1. An unmodified local system copy
of that license is included as `LICENSE-LGPL-2.1`:
https://github.com/gphoto/libgphoto2/blob/master/COPYING

The separate trigger API was additionally checked against the public
`gp_camera_trigger_capture(Camera*, GPContext*)` declaration, the independent
`GP_OPERATION_TRIGGER_CAPTURE = 1 << 5` ability bit, and its implementation in
`gphoto2-camera.c`. Trigger success is not a camera-file or import receipt; no
sample event synthesis/deletion policy is used. All trigger fixtures and runtime
verification remain UNRUN.

The libraries are free software, supplied without warranty, including implied
merchantability or fitness for a particular purpose. See the complete license.

Dynamic linkage uses `libgphoto2.so.6` and `libgphoto2_port.so.12`, supplied by the
user's system. This module never installs or bundles them. The system libraries
remain replaceable. Binary packaging must retain applicable notices and fulfill
the license/source obligations for every actual library/camlib version included.
Do not treat this source-only notice as completed binary distribution compliance.

## Existing Rust registry components

- `libc` 0.2: MIT OR Apache-2.0, https://github.com/rust-lang/libc
- `sha2` exactly 0.10.9: MIT OR Apache-2.0,
  https://github.com/RustCrypto/hashes/tree/sha2-v0.10.9/sha2

`sha2` is already pinned by the native application's existing lockfile. This
crate only declares dependencies, does not modify any lockfile or registry
source, and has not resolved/downloaded them. Actual distribution must preserve
their own notices and transitive dependency licenses.
