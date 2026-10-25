# Native tether session host

Status: source authored and statically reviewed only. All fixtures, builds,
link/ABI checks, hardware checks and end-to-end imports are **UNRUN**. No camera
was connected or operated, no app was launched, and no build, test, dependency
installation, download, inference or Git write was performed for this work.

## Integration

The native module is `ui/src-tauri/src/tether_host`. Parent integration owns the
Cargo path dependency `lrt_tether_capture`, main module/command registration,
actual UI adapter, engine receipt validation, engine dispatch and shutdown.

The implementation separates public admission/mailbox (`mod.rs`), strict UI
envelopes/naming (`wire.rs`), private storage (`storage.rs`), thread/command
ownership (`worker.rs`), ingestion lease/readback (`worker/lease.rs`) and actual
device/transfer/frame work (`worker/capture.rs`).

Commands, all with the existing `Arc<AppState>` and Tauri `AppHandle` injection:

- `tether_capture_state() -> TetherSnapshot`
- `tether_capture_request(request: TetherRequest) -> TetherReceipt`
- `tether_capture_receipt(request_id: string) -> TetherReceipt | null`
- `tether_capture_destination(path: string) -> TetherDestination`

The application adapter must invoke the actual system directory picker first,
then pass its selected absolute local path to destination registration. A cancel
returns null from the adapter and does not call registration. Registration walks
every component without following symlinks, pins an open directory descriptor,
and returns a runtime-owned opaque token. Subsequent Start accepts that token and
its matching display path, not an arbitrary import path. Each import also sends
`root_identity: [device_decimal, inode_decimal]` from the original pinned FD. The
engine must enforce that proof on its actual opened root FD before any output is
created, and retain its precommit/path-identity checks. Host-only postcommit
checking would not prevent a swapped directory from receiving files.

Listen to the real Tauri event `tether-capture://event`, whose payload is the
`TetherHostEvent` union from `ui/src/tetherCapture/protocol.ts`: `snapshot`,
`imported_document`, or `live_frame`. No DOM custom event or demonstration camera
provides this transport. Keep one port per `host_id`; replace it on runtime
identity change. A mount/unmount changes observers, not device ownership.

Call `tether_host::shutdown()` before engine shutdown. It closes the producer
publication gate, signals cooperative cancellation and requests owner-thread
cleanup. It never joins a blocked native call or claims a hard driver timeout.

## Ownership, admission and stop

`LinuxGphotoDevice::load()` and every actual device call execute on one named
owner thread. The device contains `Rc` and native pointers and never crosses the
thread boundary. Typed commands cross an eight-slot bounded channel. Stop has a
separate priority mailbox so refresh traffic cannot crowd it out. Snapshots and
receipts are cloned immutable JSON values matching the public UI ABI.

Native request identity, exact public envelope and the private saved-project
binding visible at admission are persisted before a request enters the command
queue. Duplicate identity with identical arguments reads the existing receipt;
it never replays the command. Different arguments for an old identity fail.
Session and host revisions are checked at admission. A newer engine read cannot
silently replace the project binding captured with the user's Start request.

Start calls the actual epoch-bound `ingest_session_api::submit` with `owner:
"tether"`, the complete saved-project binding, and a maximum of 64 operations,
bounded further by real engine capacity and retained transfer rows. Only the
original validated arm result can open the device. No project switch, implicit
save, preset application or recipe edit occurs. The engine guards saved project,
workspace, disk digest and original editor selection throughout the lease.

A fresh read of the same lease is required before remote shutter or starting
live view. Continuous event/frame production also requires a recent successful
lease read. Stale state responses are fenced from newer admission/readback by an
internal serial. While a managed import owns the engine, the host issues only
its exact operation query, not a state request that would bypass that writer.

A stop request is durable before cancellation is signaled. Engine import
admission holds the same mutex as stop acceptance across its final active/token
check and transport send. Therefore a stop already accepted cannot race into a
new managed import. A running import can still finish and be recorded; no late
import notification or frame is emitted after the stop gate. Driver close and
engine lease release are separate steps. `phase: stopped` and a successful stop
receipt require both the returned local driver close and an exact successful
release receipt. Native calls may block indefinitely despite cooperative tokens.

## Real event-to-document path

1. Probe re-enumerates the selected USB model/address, opens it, reads available
   settings and performs one bounded event poll, then closes. It never takes a
   photo, downloads an original or writes settings. Poll timeout verifies the
   polling API only. A probe event does not become a capture/session import.
2. Verified event polling permits bounded Start unless original download is
   explicitly unsupported. Download remains honestly `unknown` until the first
   actual transfer succeeds or fails; no unsupported bootstrap download is hidden
   inside Probe. Fresh open and polling are repeated for the admitted session.
3. Each observed `FileAdded` allocates a new UUID occurrence and durable transfer
   row. Neither equal paths nor equal content deduplicate occurrences. There is
   no camera event sequence number in this public ABI. `FileChanged`,
   `CaptureComplete` and folder/unknown events never synthesize captures.
4. Each occurrence gets an exclusive private 0700 directory. The device's
   bounded transfer exclusively creates a 0600 file. The host then reads all
   bytes again, compares full SHA-256, checks stable metadata and basic supported
   RAW/JPEG container evidence. Incomplete or changed files are not imported.
5. Complete evidence carries path, full digest, byte count, exact five-element
   stat array as decimal strings, distinct occurrence ID and
   `completion: "completed_transfer"`. The actual managed-copy importer receives
   one explicit file, the pinned destination proof and the original engine lease.
6. The deterministic operation UUID is derived before sending by the shared
   UUIDv5 helper. It is a query address, never retry authorization. A transport
   failure, missing response, cancellation ambiguity or unknown commit pauses
   receiving and queries that same operation; there is no automatic resend.
7. Only the original epoch-bound engine success plus exact actual document rows
   can produce `phase: imported`. The host checks operation/request identities,
   session/project/workspace, source path/name, full hash, bytes, decimal stat,
   occurrence, completion, actual document/source/recipe IDs and the exact
   deterministic managed path. A completed download is never an import receipt.

The event loop does not drain unbounded camera-side buffers while an import is
pending. One transfer/import is in flight. Cameras/firmware may buffer or drop
events; no lossless hardware-buffer guarantee is made. A repeated camera path
identifies only the object returned by the current read, not an invented shot
sequence or historical version. Camera originals are never deleted, renamed,
formatted or uploaded. RAM/card capture target is untouched and no guarantee is
made about where firmware retains captures.

## Naming and optional controls

All five modes are implemented: custom-counter, custom-original-filename,
UTC-date-counter, UTC-date-original-filename and original filename. UTC date is
frozen at session start; each observed FileAdded reserves one monotonically
increasing ordinal, including later skipped/failed events. Counters never wrap.
Names preserve exact safe UTF-8 and extension, with a 255-byte final-component
limit, explicit reserved/control/separator rejection, and no transliteration,
normalization or silent truncation. Unique per-occurrence directories prevent
filename collisions without changing the selected pattern. Managed storage uses
its existing deterministic UUID filename while actual document display names
retain the selected original/staged filename.

Vendor recording-setting text is shown read-only, not guessed into a format.
Unknown recording format allows only `raw_jpeg`, meaning all actual supported
RAW/JPEG objects, not that the camera records both. No missing mate is invented.

Remote shutter uses only the separate driver-advertised `remote_trigger`
capability and explicit `trigger_capture()` operation. This is the public
event-driven API. The synchronous `request_capture()` path is not used, so a
valid synchronous object return is never discarded or guessed to be a later
FileAdded. An unsuccessful post-dispatch trigger stays outcome-unknown and is
never automatically fired again.

Live view starts only after an explicit request. It uses real bounded JPEG/PNG
preview bytes with checked dimensions (at most 16 megapixels), at most two
frames per second, and the
same single driver thread. Frames carry host/session/generation/sequence fences
and a native-generated data URI. Stop discards late frames. This is a camera
preview, not evidence of imported full-image quality or pixel review.

`keep_current` is supported. `follow_latest` is explicitly unsupported by this
host because the current engine lease pins editor selection. Start/change with
that mode returns a reason; the panel should default to keep-current and visibly
disable the unsupported mode. Import events may refresh library/project metadata
but must not navigate the editor or re-import files. Transfer retry is likewise
explicitly unsupported; no transfer is marked retryable.

## Durability, bounds and recovery

The private app-data ledger is written through a same-directory exclusive temp
file, full file sync, atomic rename and directory sync. It retains native
requests/receipts, engine mutation intents/validated receipts, current session,
transfers and unresolved engine intent. No persistent row calls a transfer
imported before exact readback passes. Preview bytes are not logged.

Bounds: eight queued commands plus a priority stop mailbox, 192 retained native
requests (last 16 reserved for stop/recovery), 256 retained engine intent rows,
64 transfer rows per runtime, at most 64 imports per lease, 512 MiB per original,
4 GiB completed staging per runtime, 16 MiB per live frame, 16 destination tokens,
and a 4 MiB ledger. Capacity refusal is visible, not silent eviction. Complete
private staging remains available for recovery; it is not automatically removed.

A UI remount sees unresolved current-runtime native requests again. Missing
native mutation receipts are never proof of nonexecution. The transport may
prune completed state/query reads; only those read-only requests can be replaced
with new read identities when absent. Retained pending reads are not multiplied.
An engine-epoch change blocks all further session mutations/publication and does
not reinterpret old receipts in a new engine.

A process restart does **not** recover an old engine lease. If the previous
ledger has an unresolved request, active session or engine intent, the new host
fails closed without loading/operating a camera or overwriting that ledger. It
reports the need to inspect the original saved project/managed-import evidence;
there is no fabricated reopen-recovery API. A fully completed ledger is archived
before a fresh runtime can replace it, with a 32-history-file limit and no
automatic history deletion. The restart-recovery user workflow remains pending.

## Acceptance plan, all UNRUN

Pure authored fixtures cover exact Unicode naming, byte limits, invalid/reserved
names, counter overflow, strict request envelopes, private-binding exclusion,
unknown receipt semantics, actual JPEG dimension parsing and deterministic
operation/managed-name roles.

Runtime acceptance still needs authorized execution and hardware:

- compile/typecheck the final shared integration and validate actual libgphoto ABI;
- real picker cancel, token mismatch, symlink ancestors and destination-inode swap
  between native admission and engine open (must fail before destination create);
- missing driver, multiple devices, unplug/replug, unknown recording format,
  unknown-download bootstrap and first real transfer;
- repeated FileAdded with equal name/hash, RAW/JPEG pairs, FileChanged-only events,
  partial transfers, filename collisions, Unicode and unsupported container types;
- engine project/workspace/disk/selection changes and exhausted receipt budgets;
- lost arm/import/release responses, retained pending queries, pruned read-only
  replies, original-operation reconciliation and epoch replacement;
- stop during open/download/hash/import/preview, bounded queue saturation,
  fsync/rename failure, blocked native close and no late event publication;
- explicit trigger capability including synchronous-only cameras, unknown trigger
  outcome without retry, actual preview dimensions and two-fps pacing;
- crash before and after dispatch/commit, retained private sources and honest
  restart-recovery block, with no duplicate import or false imported log entry.
