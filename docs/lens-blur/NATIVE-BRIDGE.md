# Lens aperture Python bridge: authored, UNRUN

Owned source: `engine/src/lumaretouch_engine/lens_aperture_native.py`.
Owned fixtures: `engine/tests/test_lens_aperture_native_unrun.py`.
Native contract: `core/lens_aperture/lens_aperture.h` and its README.

This is numeric transport for the original aperture core, NOT a new history
owner, renderer registry, document service, model backend or UI integration.
No product imports, tests, compiler/build, numerical execution, typecheck,
model inference/download, dependency installation or Git write was performed.
Fixtures are expectations only; a mock copy is explicitly NOT blur evidence.

## Exact public boundary

`normalize_settings(value)` returns a fresh dictionary and never changes saved
input. It requires exactly:

    version: 1
    aperture: circular_disk | rim_weighted_disk | regular_pentagon |
              regular_octagon | cat_eye_intersection
    max_radius_px: 0..128
    focus_near: 0..focus_far
    focus_far: focus_near..1
    depth_falloff: 0.000001..1
    occlusion_tolerance: 0..1
    rotation_radians: -pi..pi

Unknown versions, extra keys, missing keys, booleans as numbers, nonfinite
numbers and unknown shapes reject instead of resetting intent. Controls are
validated as finite JSON numbers and rounded to f32 for native calls. Work
admission uses those same rounded controls. No physical lens metadata or
undocumented proprietary style mapping is inferred.

`capability(enabled=True)` performs an actual packaged native load/symbol/ABI/
kernel-mask query and reports available/reason, ABI 1, supported original kernels
and `quality_status='authored_unrun'`. Availability is NOT depth readiness,
performance or photographic acceptance. Explicit disable avoids loading.
`available()` returns only that availability boolean. Importing the bridge loads
neither NumPy nor the native library; it defines ctypes declarations only.

`apply(source_rgba, relative_depth, settings, *, refinement=None,
encoding='linear-srgb-d65', premultiplied=True,
depth_convention='near-zero-far-one', enabled=True,
max_candidate_taps=None, cancelled=lambda: False)` returns a new C-contiguous
native-endian float32 full-source RGBA array only after all work succeeds.

Source is exact H×W×4 native float32, linear-sRGB D65, premultiplied, finite,
alpha [0,1] and `abs(RGB) <= 65504*alpha`. Signed HDR is accepted, not clipped.
Depth is exact H×W native float32 in [0,1], near zero/far one. Optional refinement
is exact H×W native float32 in [-1,1]. No dtype coercion, tensor conversion,
resizing, alpha flattening, transfer conversion or implicit depth inversion.
Strided arrays are accepted only through an independent contiguous snapshot.

Private input copies are created in bounded blocks and marked read-only. They
have no caller-visible alias while ctypes releases the GIL. The caller must not
mutate original inputs DURING snapshot copying. The bridge cannot authenticate
an image ID, source revision, transform, model receipt or a real subject merely
from arrays; host identity and provenance validation must precede this call.

## Native loading and replaceability

Only the fixed packaged `bin/liblrt_lens_aperture.so` is queried. No environment
library override, alternate search, runtime compile/install/download or Python
pixel fallback. A successful ABI-1 handle stays resident until process exit.
All four required native symbols and the intended 28-byte settings struct are
checked. The kernel mask may advertise a subset of known kernels; requesting a
missing kernel fails explicitly. Unknown mask bits/empty masks fail admission.

Disabled, missing, incompatible or numerically rejected operations never become
successful identity output, including neutral calls. The saved recipe belongs
to the host and is not changed. A higher-level host can separately recognize a
provably neutral saved operation, but must not misreport absent native or AI
capability. Replacing the installed artifact requires a process restart; this
is not hot plugin unloading. ABI/semantic changes require explicit versioning
and migration rather than editing existing saved intent in place.

## Adaptive tiles and full-operation admission

`work_estimate((height,width), settings)` is pure: it loads no NumPy/library,
reads no live memory and allocates no pixel arrays. It returns:

- True source halo `0` when rounded R≤0.5, otherwise `ceil(R+0.5)`.
- Conservative candidate taps per output pixel:
  `min(width,2*halo+1) * min(height,2*halo+1)`.
- Full-image candidate upper bound, and that bound ×16 for the maximum 4×4
  aperture quadrature evaluations. Zero/in-focus/occlusion gates can do less.
- Admitted tile pixels `min(65536, floor(8388608/taps_per_pixel))`.

Tiles cover the source exactly once with integer rectangles of at most that
size. Every native tile receives the SAME COMPLETE frozen source/depth/plane,
not cropped buffers. Its coordinates are source-grid coordinates. Native halo
clipping therefore happens only at actual image boundaries, not tile seams.
No tile rejection causes automatic radius reduction or a lower-resolution image.

At R=128 on a sufficiently large image, halo=129, each pixel's upper candidate
count is 67,081, and admitted tiles have at most 125 pixels. A 6000×4000 image
has a conservative upper bound of 1,609,944,000,000 candidates, up to 16 times
as many aperture sample evaluations. This is plainly NOT interactive performance.
The direct CPU reference path needs measured quality-preserving acceleration
before a product claim. Per-tile bounded memory is not a whole-job speed promise.

The host can set an explicit positive integer `max_candidate_taps` after showing
or applying its job policy. Exceeding it rejects the whole operation with a
resource error; it never changes saved settings. If omitted, source/radius caps
still bound total work, but the host must separately own timeout/cancellation,
responsiveness and concurrent-job admission. No arbitrary hidden time limit is
claimed here.

## Memory, cancellation and publication

`memory_estimate((height,width), with_refinement=False)` is also pure. Its
conservative totals include:

- Borrowed source+depth: 20 bytes/pixel, or 24 with refinement.
- Independent private snapshots: the same amount again.
- Full private output: 16 bytes/pixel.
- Python tile and native staging: up to 2 MiB combined.
- Bounded validation/copy/allocator allowance: 16 MiB.

Total working-data estimate must not exceed 6 GiB; native source limit is 100m
pixels. Additional-memory admission uses the existing fail-closed Linux/cgroup
budget estimator at operation time. This is not an OOM guarantee: allocator
fragmentation, concurrent jobs, model memory and other document state require
host-level admission. Inaccessible budget metadata is a real blocker, not an
excuse to assume the host's entire RAM is free.

The complete snapshots pass native validation once before any render tile.
The native kernel separately checks each real-source halo. Callback exceptions
are captured and re-raised after native control returns instead of escaping
through ctypes. Native status 4 cancels; 5 is resource refusal; other nonzero
codes are explicit rejections. No failed tile reaches the full private image.

Successful tile output is independently checked for finite premultiplied HDR,
exact neutral R≤0.5 bytes and exact q=−1 clear pixels, then copied in bounded
blocks into the still-private full image. A later tile failure or cancellation
discards that entire private image. A final cancellation poll runs before return.
Allocation/callback latency and the last return-to-host race are not hard realtime
bounds. Host must recheck source/request generation and commit derived data,
history and display together after return; this bridge publishes no document state.

## Authored fixture coverage

The UNRUN tests cover strict settings/version preservation, native-rounded work
admission, adaptive coverage, memory accounting, independent snapshots, strided
float32 handling, invalid depth/refinement/HDR, explicit encoding, disabled/missing
modules, missing kernels, work/memory refusal before copies, complete-source
tiles, late-tile failure, corrupt neutral output, cancellation, callback exception
containment, struct layout and import-time loading boundaries.

Two additional UNRUN tests require the real native artifact: the independently
counted circular impulse kernel, plus signed HDR/clear-mask/tile-seam parity.
If the artifact is missing they skip with an explicit UNRUN reason, not simulated
numerical success. All photographic, depth, UI/history, export and performance
acceptance gates in RESEARCH-AND-GATES.md remain open.
