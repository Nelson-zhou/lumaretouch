# USB device port: handbook 47251

Status: source authored only. All tests, build, ABI shim checks, runtime camera
interaction, physical-shutter verification, transfer/hash verification on real
files, preview and remote shutter are **UNRUN**. No Linux camera compatibility
claim follows from this source. Reference workflow:
https://www.pixcakeai.com/guide/47251

## Replaceable boundary

`core/tether_capture` is an isolated Rust 2021 library named
`lrt_tether_capture`, Rust floor 1.77. No host, engine, UI, frozen root document or
lockfile is changed by this module. It has no startup hook, hidden process,
installer, CLI shell, camera-config setter, camera-delete function or upload.

`TetherDevicePort` exposes:

- `enumerate(cancel) -> Vec<DeviceId>`
- `open_selected(&DeviceId, cancel) -> DeviceCapabilities`
- `capabilities() -> DeviceCapabilities`
- `read_settings(cancel) -> Vec<CameraSetting>`
- `wait_event(timeout, cancel) -> DeviceEvent`
- `download_to_staging(&CameraObject, &StagingRequest, cancel) -> DownloadReceipt`
- `request_capture(cancel) -> CameraObject` (explicit optional shutter command)
- `trigger_capture(cancel) -> ()` (explicit optional event-based shutter trigger)
- `capture_preview(max_bytes, cancel) -> PreviewFrame` (one explicit frame)
- `close() -> Result<()>`

The concrete Linux constructor is `LinuxGphotoDevice::load()`. It only loads the
two fixed system ABI SONAMEs and creates a context; it does not discover/open a
camera. Construct it inside the dedicated owner thread. `Rc` makes the entire
adapter !Send/!Sync; never put it in a shared UI mutex or move it across threads.
Thread-safe cancellation tokens are the only cross-thread primitive provided.
Use a bounded host command queue with session/generation/request fences.

System loader configuration, including LD_LIBRARY_PATH and libgphoto2's camlib
configuration, must be trusted by the host. There is no arbitrary library path
argument. Loading code with a trusted SONAME is not verification of its vendor
or integrity. Missing libraries/symbols return `Unavailable`; no auto-install.

## Device selection and honest capabilities

`DeviceId` is an exact `{model, port}` pair from fresh USB detection. The adapter
rejects bare `usb:`, non-USB/network/directory/MTP-audio devices, stale selection,
and selection while another camera is open. Both ability and port are set before
`gp_camera_init`; the library's first-camera fallback is never used. The USB
address is ephemeral, **not** a permanent serial identity. On disconnect/replug,
stop the session and explicitly select again; never silently reconnect to the
same address or infer serial identity from a matching model.

Capabilities are `Unknown`, `DriverAdvertised`, `Verified`, or `Unsupported`:

- `events`: initially unknown. A successful poll verifies the polling API, not
  physical shutter origin or future event delivery in every camera mode.
- `settings`: driver configuration bit, then the actual read result. Only ten
  known exposure/format/battery/target values are read. Missing keys remain
  absent. The adapter cannot change them, even when camera metadata says writable.
- `remote_capture`, `remote_trigger`, `preview`: independent actual driver operation bits,
  then the result of the explicitly requested operation. Unknown is not enabled.
- `original_download`: unknown until an actual transfer; no fabricated download
  support from the absence of a special file-operation flag.

Do not map advertised or merely detected to "tested". A host may explicitly
probe open/read/event polling/close without firing the shutter or downloading.
It must not fabricate proof of physical-shutter transfer to unlock itself.
The current settings/recording format must stay unknown if unavailable; file
extension does not prove the camera's current RAW+JPEG setting.

The two shutter APIs are deliberately distinct. `request_capture` uses
`gp_camera_capture` and returns its actual camera path; its behavior is unchanged,
and the API does not promise a matching `FileAdded` event. An event-based host
must instead require `remote_trigger`, sourced only from
`GP_OPERATION_TRIGGER_CAPTURE` (`1 << 5`), and call `trigger_capture`, which maps
to `gp_camera_trigger_capture(Camera*, GPContext*)`. A successful trigger returns
no path and means only that the native trigger operation succeeded. The camera
mode may produce one or more images. Only subsequently received real `FileAdded`
events become download occurrences. Do not manufacture an event, infer a file,
silently fall back to `request_capture`, equate dispatch with import, or collapse
events by path/content. `remote_trigger` verification does not verify event
delivery. A dispatched trigger error remains `outcome_unknown` except explicit
unsupported; cancellation, timeout and busy responses must not cause an automatic
retry or second shutter. Pre-dispatch validation/cancellation has no such claim.

Primary trigger semantics were checked against the public camera header,
abilities header and camera implementation on 2026-10-25:
https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-camera.h
https://github.com/gphoto/libgphoto2/blob/master/gphoto2/gphoto2-abilities-list.h
https://github.com/gphoto/libgphoto2/blob/master/libgphoto2/gphoto2-camera.c

Events are timeout, file added, file changed, folder added, capture complete or
unknown. File payloads carry `{folder, name}` on the **camera filesystem**.
They are copied before C-allocated event data is freed. No camera path is ever
used as a local path. Non-UTF-8 camera paths fail explicitly instead of lossy
round-trips to a different filename. A host owns bounded pending-file queues,
occurrence identity and retry policy. This event ABI provides only folder/name,
not an occurrence sequence, capture timestamp or persistent object handle.
Keep each received `FileAdded` as a distinct occurrence: matching path or hash
cannot distinguish duplicate delivery from filename reuse or equal-content
separate captures. Offer explicit duplicate review rather than silently dropping
an occurrence. `FileChanged` is not automatically a new capture. RAW and JPEG
remain separate actual files; never manufacture a companion or inferred pair.

## Original-preserving transfer and staging

The adapter requests `GP_FILE_TYPE_NORMAL`, which is the actual file view for
modern DSLR RAW files as well as JPEG. It does not decode, recompress, resize,
rename on camera, delete after download, set capture target, format media, change
settings or trigger capture while opening/polling/transferring. Any driver/camera
storage behavior remains device-specific. In particular, an optional remote
capture can use the camera's existing RAM target; the adapter does not promise
durable camera-card storage when the camera is not configured to provide it.

`StagingRequest` contains an absolute private existing directory, independently
generated safe UTF-8 `local_name`, explicit `max_bytes` and cooperative timeout.
The directory must belong to the effective uid and have no group/other access
(normally 0700); ancestors are host-controlled and not concurrently renamed.
The final directory is opened no-follow and pinned by descriptor; the file is
created with `openat(O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0600)`. Existing files
are never overwritten. The adapter does not create directories. The host should
use opaque unique `.stage` filenames, not camera-provided names, and must never
watch this private directory as an automatic import folder.

`CameraFileHandler` writes are checked against the remaining limit before any
write. Read/write callbacks contain panics and implement bounded byte counts;
cancellation is checked at operation entry, native context callbacks and each
chunk. SHA-256 uses the existing pinned RustCrypto `sha2`, not custom crypto.
Only nonempty successful native transfers with matching local length and
successful file/directory sync return `{path, local_name, bytes, sha256_hex,
mime_type, camera_object}`. This proves locally received bytes, **not** a
camera-provided cryptographic checksum. MIME is a driver assertion, not a decoder
validation. Failures attempt cleanup only of the adapter's private partial file;
cleanup is best-effort if the filesystem itself fails. Such files have no
successful receipt and must never be imported.
A crash can leave an orphan `.stage`; host startup cleanup must be bounded and
limited to its own private staging area.

The receipt is not a document-import receipt. The host must independently
verify/consume the staged file, preserve each occurrence, atomically promote it to
the explicit destination without overwriting, open it through the existing
import pipeline, and only then publish imported/document callbacks. The SHA-256
is byte-integrity evidence, never a unique occurrence id. Stop or
generation mismatch must prevent importing late receipts. Successful staging
files belong to the host for cleanup/promotion; camera originals remain intact.

## FFI ownership and bounds

Only the required public function symbols are loaded with exact prototypes.
Opaque C objects are never dereferenced. `CameraAbilities`, `CameraFilePath`, and
`CameraFileHandler` are the narrowly reproduced public layouts, with authored
layout assertions for the supported Linux C ABI. Runtime ABI checks are still a
release gate. The handler API's upstream header itself warns of possible ABI
instability; SONAME compatibility and required-symbol checks are not a substitute
for testing the actual packaged library/camlibs.

The upstream implementation stores borrowed pointers to both handler and private
state. A driver/cache can retain `CameraFile` references beyond one call and
beyond the caller's `gp_file_unref`. Therefore each callback state is boxed,
retired to a rejecting tombstone after the operation, and kept until camera
exit/unref has destroyed its filesystem/cache. The bytes/fds are released at
operation completion, not retained for the whole session. Callback owners are
freed **after** camera destruction, then context, then dynamic libraries.
Camera close also unrefs on error and never reuses the uncertain handle.

Bounds: at most 256 discovered entries, 1-second individual event polls,
512 MiB original sink, 16 MiB preview sink, maximum 10-minute requested transfer,
and 4,096 transfer/preview callback tombstones per open session. The host's lower
session/queue budgets take precedence. Budget exhaustion is explicit; no hidden
session restart. No continuous unlimited live-view claim is made.

Timeout/cancellation is cooperative: a native driver or USB call may block or
buffer internally before invoking a callback. The sink cap bounds application
output and preview allocation, **not** every camlib allocation or wall-clock
duration. For a hard process-memory/time budget, a later host must isolate the
device worker in a supervised process. The current owner-thread implementation
does not make that guarantee. Do not close the camera concurrently to interrupt
an in-flight call; wait for the serialized call to return. Failed remote shutter
after dispatch sets `outcome_unknown` unless explicitly unsupported; never retry
it automatically because the first shutter may already have fired.

Preview accepts only declared JPEG/PNG with matching signature, but the host
still needs bounded image decoding before display. Capture-preview is one frame,
not a synthetic image, a separate shutter capture, or an automatic live-view
configuration change.

## Authored fixtures and future verification gates (all UNRUN)

Pure source fixtures cover: cancellation, capability evidence distinctions,
concrete USB identity, camera/local path separation, fixed-array terminators,
C-layout sizes, safe staging names, chunk bounds, SHA-256 known vector, repeated
native reads, oversized/null callbacks and retired callback rejection.
Additional trigger fixtures cover independent capture/trigger capability bits,
no synthetic path return, unsupported versus uncertain dispatch errors. These
fixtures and real trigger/event-delivery checks remain **UNRUN**.

Before enabling the feature in a release, separately authorize/run:

1. Build/typecheck/lint on the supported Linux Rust/toolchain and actual locked
   dependencies, then pure fixtures. None ran during source authoring.
2. A C ABI shim compiled against the packaged public headers, including by-value
   `CameraAbilities`, callbacks, missing symbol, malformed event and retained
   `CameraFile` lifetime/failure injection. Sanitizer/leak coverage is required.
3. Filesystem failure tests: exclusive-name collision, symlink rejection,
   private-directory permission rejection, short/failed write, out-of-space,
   fsync failure, cancellation, orphan cleanup and zero imported partials.
4. Real explicit-user-selected camera tests: physical-shutter RAW/JPEG/RAW+JPEG,
   bursts and duplicate/file-changed events, unplug, device busy, permission
   failures, storage rollover, originals still present and hash/byte equality.
5. Optional preview/shutter only on devices that advertise and actually serve
   them, stale/late receipts, session fences and uncertain shutter outcomes.

The fixture source is not passing evidence. See
`core/tether_capture/THIRD_PARTY.md` for primary header/code/license provenance.
