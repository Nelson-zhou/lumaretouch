# Original-pixel local review v1 — SOURCE CONNECTED / UNRUN

Requirement: original handbook `workflow:230984` AI挑图, `LNX-PICK-001` / `PICK-001`.
Base: `4981a22f5f19656311600042de9922db0ea0b27e` (proxy evidence repair v3).
This extends the actual library/pick workflow. It is **not completed AI selection**,
a sensor-focus verdict, an aesthetic classifier or real-photo acceptance.

## Source path and ownership

Mounted library controls → `runPick('focus')` → existing Tauri `pick` forwarding
→ `server.cmd_pick` → `pick_focus_host.start` → existing `_picks`/`_pick_stop`
→ `pick_original_focus.review` → **existing**
`portrait_fit_source.capture_original` → `decode.load_full` /
`full_source_working.working_rgb` → native-pixel crop measurements and RGB8 PNG
→ existing session rows / filmstrip/library results. No second photo database,
model download, face inference, edit pipeline, rating/flag mutation or source-file
write. Results are ephemeral; no project persistence. Proxy picker results remain
separate and never become original evidence.

Select 1–8 explicit visible document identities. Indices and document IDs must
agree when admitted; frozen row objects and paths must still belong to the
session when published. Reordering cannot redirect a running result to another
row, including a virtual copy with the same path. A new review clears older crop
results, bounding retained display crops to eight; creating a virtual copy does not copy this transient evidence.
Existing stop interrupts between
phases/photos; a native decoder or digest already running is not preemptible.
Partial completed crops remain labeled as local evidence when a run is stopped.

Choose normalized original x/y, default center. Each photo uses that position
independently and returns its exact source extent, point and integer crop rectangle.
The same normalized location is **not** corresponding-subject registration or a
verified face. Crop size is at most 256×256, clamped to image bounds, never resized.
This version does not automatically locate eyes/faces or measure a complete image.
UI displays the PNG at intrinsic CSS dimensions; browser/device scale means this
is not a guarantee of one physical screen pixel per source pixel.

## Measurements, display and limitations

Canonical source is encoded-sRGB float32, normalized from genuine RGB8/RGB16.
Measurements are local luma contrast (standard deviation), centered-gradient
energy, four-neighbor Laplacian variance and Laplacian/contrast-variance ratio.
No resizing, denoising, learned scorer or thresholded focus verdict is performed.
For contrast variance below 1e-6, ratio is unavailable; this is a numerical
comparability guard, **not** a calibrated blur threshold. No cross-photo ranking.
Noise, texture, subject selection, sharpening, compression and RAW development
all affect readings; a high value does not establish good focus, and a flat sky
is not an out-of-focus certificate. Use the crop and existing manual ratings.

Display alone is rounded to RGB8 PNG (lossless after quantization); derivative
measurements use the original-resolution canonical float crop. No current edits,
retouch, HDR tone mapping or export effect is applied. RAW is developed RGB, not
sensor mosaic; existing canonical ICC/SDR conversion remains authoritative.

## Exact admission / formats / freshness

* Canonical owner max **32,000,000 pixels**, max **4 GiB compressed file**;
  source dimensions must be at least 3×3. Larger inputs fail, never downsample.
* Canonical conservative decode estimate is 128 bytes/pixel + two compressed
  input copies + 64 MiB scratch. Review additionally reserves 32 MiB for bounded
  crop math/display/cache and caps decode budget at 4 GiB, taking at most half
  the existing cgroup-aware available-memory estimate. This is admission, not a
  measured RSS bound or performance guarantee; concurrent allocations may change
  availability. Unknown/hidden cgroup hierarchy fails closed. Known heavy previews
  block admission; export/retry, benchmark, full inspection, image loading and
  the common edit guard reciprocally refuse while this worker is reserved.
* Ordinary opaque SDR formats accepted by canonical Pillow RGB8 export; genuine
  PNG16 and supported unsigned RGB16 TIFF use existing precision-preserving
  codecs/ICC conversion. Unsupported float/HDR, transparency, multi-page or
  high-bit layouts are refused by those owners, not flattened or quantized here.
* RAW requires an already opened row with established full oriented dimensions;
  unopened RAW explicitly asks to open it first. Existing LibRaw metadata API
  reports unrotated extent only, so this adapter does not guess orientation from
  a camera JPEG. `capture_original` rechecks dimensions and requires genuine
  RAW16/LibRaw; absent/unsupported codec, dimensions or precision fail closed.
  No embedded-preview/half-size/self-DNG8 fallback. RAW format coverage is exactly
  the installed canonical decoder's supported set, not all camera formats.
* Existing content digest + `(dev,ino,size,mtime_ns,ctime_ns)` authenticate source
  before/after decode and after crop encoding. Reduced/preview/wrong-precision
  decodes are refused by the canonical capture owner. A later session response
  suppresses crops whose stat changed or source disappeared. Stat freshness is
  best effort, not continuously watched or an atomic filesystem snapshot. The
  UI is not evidence of live source revalidation between responses.
* Same-path virtual copies deliberately review original pixels, not each copy's
  modified/creative/rendered output. The UI states this scope.

## Primary workflow research / open-source decision

Read official [darktable culling](https://docs.darktable.org/usermanual/development/en/lighttable/lighttable-modes/culling/)
for explicit selection comparison and zoom; its [full preview](https://docs.darktable.org/usermanual/development/en/lighttable/lighttable-modes/full-preview/)
sharp-region helper may use an embedded JPEG, so that helper is **not** authority
for this original-pixel path. Official [focus peaking limitations](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/shared/focus-peaking/)
explain that local contrast and applied sharpening can highlight detail without
proving focus. [OpenCV Laplace tutorial](https://docs.opencv.org/4.13.0/d5/db5/tutorial_laplace_operator.html)
is derivative background, not a universal quality classifier. No upstream code,
model, package or runtime was copied or added. Existing GPL-3.0-or-later project,
NumPy/Pillow and canonical decoder license owners are reused unchanged.

## Validation status and authored fixtures

`engine/tests/test_pick_original_focus_unrun.py` is **authored, UNRUN**: crop
bounds and edge points, invalid/NaN positions, flat-field ratio suppression,
texture measures without verdict, strict crop layout, stale source exclusion,
selection identity mismatch, removed/replaced row refusal and final worker state.
Only Python AST syntax parsing and source/diff inspection were performed.
No build, typecheck, test execution, product startup, model inference, install,
photo quality, color-management, RAW or performance validation was run.

Later authorized validator must cover canonical RAW orientation/16-bit refusal,
PNG16/TIFF16 ICC precision, same/different source replacements, low-memory/cgroup
refusal before decode, source changes during hash/decode/encode/publication,
cancel/retry/removal/project switch/reorder, multiple virtual copies, exact source
crop coordinates and CSS/device scaling, stale event/reconnect handling, data-URL
CSP, and realistic noisy/defocused/sharpened portraits at corresponding subjects.
No historical picker benchmarks certify this new path. Remaining original AI
selection requirements (scene/aesthetic/front-facing, requested-count optimizer,
smile/group rules, automatic detected-face focus review) remain explicit gaps.
