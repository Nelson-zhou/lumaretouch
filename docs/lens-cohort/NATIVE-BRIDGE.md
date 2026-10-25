# Cohort lens native bridge, ABI 2

Status: **AUTHORED / UNRUN**. The Python bridge, mock contracts and opt-in native
fixtures have not been imported, executed, built or numerically validated during
this authoring task. Static syntax/source inspection is not a runtime pass.
There is no measured 24MP result, timing, interactive-latency or RSS claim.

## Separate implementation and explicit input scope

`engine/src/lumaretouch_engine/lens_cohort_native.py` is a separate adapter for
`core/lens_cohort/lens_cohort.h`. The original `lens_aperture_native.py` remains
unchanged. The only runtime library path is the package's
`bin/liblrt_lens_cohort.so`; external symlink escapes, missing symbols, ABI other
than 2 or math identity other than `0x00020001` fail closed. No compile, install,
download, alternative library search, version-1 fallback or NumPy pixel path is
used. Loading happens only during an explicit capability query or render.

The bridge requires little-endian, 64-bit CPython and the exact C layouts:
settings 44 bytes, budget 72 bytes, plan 232 bytes. Other runtimes/layouts are
unsupported, not silently copied or byte-swapped.

The source is exact built-in immutable `bytes`, tightly packed full-resolution
little-endian float32 RGBA in linear sRGB D65. Native create checks the entire
source: finite RGB in [0,1], alpha exactly 1. Optional refinement is another
exact immutable full-grid little-endian float32 byte sequence, finite [-1,1].
Arrays, bytearrays, memoryviews, subclasses, wrong lengths, HDR and partial
alpha are not coerced into this input scope. A neutral radius is not an escape
from input validation or native availability checks.

Depth is explicitly manual and constant. `manual_depth_acknowledged` must be
the actual boolean `True`; the host authenticates the user's acknowledgement
and matching source/refinement identities. Pass the actual retained constant
u16-plane value divided by 65535, not the original slider value. The bridge
rounds this to the ABI's f32 once. It does not infer depth, inspect an AI model,
accept a varying depth plane or decide whether old intent may be migrated.

The settings dictionary keeps the existing version-1 scalar vocabulary and
five original aperture names. This does **not** select or reinterpret a saved
version-1 recipe: the host must separately select the new version-2 render
recipe and preserve its distinct math identity.

## Public boundary

`capability(enabled=True)` reports `available`, `reason`, `abi`,
`math_identity`, `kernels`, `quality_status` and `input_scope`. Availability is
an actual packaged ABI/symbol check, not a successful render or quality claim.

`default_budgets(width, height, ...)`, `DEFAULT_WORK_BUDGETS`,
`DEFAULT_NATIVE_SCRATCH_BYTES`, `DEFAULT_MAX_LIVE_BYTES`, and
`memory_estimate(width, height, ...)` are pure arithmetic/default helpers. They
do not load native code, inspect pixels, allocate image storage or promise that
any input will be admitted. Work ceilings are explicit and are never loosened
or clamped to hide failure. Resource refusal never reduces resolution, radius,
aperture quality or refinement values.

Typical host call, after independent provenance/current-source admission:

```python
result = lens_cohort_native.render(
    immutable_source_bytes, width, height, scalar_settings,
    manual_depth=retained_u16_depth / 65535,
    manual_depth_acknowledged=True,
    refinement=immutable_refinement_bytes_or_none,
    budgets=lens_cohort_native.default_budgets(
        width, height, max_scratch_bytes=admitted_native_scratch),
    max_live_bytes=admitted_job_live_bytes,
    cancelled=is_job_cancelled,
)
```

The frozen `CohortResult` contains `rgba: bytes`, width, height, ABI, math identity,
and read-only `plan` / `memory` mappings. It is an unpublished derived candidate.
The host still checks identity/revision/cancellation and atomically commits
document/history state. The bridge performs no document write, callback with
output, partial publication or UI mutation.

## Borrow lifetime and transactional rendering

The bridge obtains a borrowed pointer with CPython's `PyBytes_AsString`, using
a private `PYFUNCTYPE(c_void_p, py_object)` wrapper. `c_void_p` is essential:
using a `c_char_p` result would create a Python string copy and mishandle embedded
zero bytes. No `from_buffer_copy`, full-source snapshot, writable source view,
temporary-buffer pointer or array conversion is used. The byte object is held
strongly both by the render frame and an owner/pointer record until after native
destroy, including while CDLL calls release the GIL. Alignment is checked.
Native code must obey the const-pointer/immutable-source contract in the header.

1. Check the exact settings, scalar depth acknowledgement, byte types/lengths,
   enabled state, explicit budgets, cancellation and pre-create memory phases.
2. Retain borrowed source/refinement pointers and a cancellation callback.
3. Native create validates all source/refinement pixels and plans the entire
   job. Only a valid handle with matching ABI, math identity, geometry, byte
   counts and admitted work counters may proceed.
4. Admit the plan's render peak, then allocate one private full-image bytearray
   and one bounded float32 tile, at most 254 × 254 RGBA pixels.
5. Invoke `render_next` once per index in ascending row-major order. Copy each
   successful tile row directly into the private bytearray using `memmove`.
   There are no per-row byte strings or full-array output intermediates.
6. Require every tile and `finish` to succeed. Any status, callback exception,
   cancellation, allocation error or failed plan check abandons all output.
7. Destroy the native job on every handle-owning exit. Release the tile and its
   private bytearray view before freezing the sink into independent immutable
   bytes. Poll cancellation before and after the copy, then return the result.

The callback catches exceptions rather than letting them unwind through C and
re-raises the original Python exception after the call. No user callback sees a
native handle or source/output pointer. The native single-job non-reentrancy
contract still applies. A process crash, malicious unsafe extension or a broken
native const-pointer implementation is outside a Python ownership guarantee.

## Memory and work accounting

Let N = width × height, S = 16N source/sink bytes, R = 4N refinement bytes or 0,
T = 16 × min(width,254) × min(height,254) external output-tile bytes,
K = native required scratch including its owned plan and native allowance,
and A = the separately named 1 MiB Python metadata/allocator allowance.

- Retained input payload: S + R; source-copy payload: exactly zero.
- Create admission: S + R + supplied maximum native scratch + A.
- Planned render phase: S + R + S + T + K + A.
- Freeze phase, after native destroy and tile release: S + R + 2S + A.
- Planned peak: maximum of the applicable phases. The full bytearray-to-bytes
  conversion is explicitly counted, not hidden behind an ndarray conversion.

The bridge admits the create ceiling and final-copy peak before native create,
then checks actual planned render/freeze peak before allocating its sink. The
result records exact image/tile payload sizes, derived phase totals, the create
admission ceiling, completed tile count and total tile payload bytes copied.
Allocator allowances are not measured exact allocator usage. These counters do
not measure wall time, peak RSS, cgroup availability or process-wide memory.

The host must separately account for other concurrent jobs, original images,
retained u16 depth planes, ICC/display caches, and any image leases not passed
to this bridge. Source/refinement sizes are counted here because the native job
keeps their allocations live, even when their storage was allocated earlier.

`plan` retains the native derived counters without relabeling them as observed
execution: validation pixels, classification bounds, repeated-halo work,
FFT dimensions/counts/butterflies, kernel quadrature bounds, residual candidate
pairs, support-probe bounds, repair reservations, direct-work ceiling, owned
plan bytes, required scratch and borrowed/sink/tile bytes. Actual numerical
repairs and elapsed work are not reported by this ABI; `finish` only checks
completion of the ordered tile sequence. Do not call these measurements.

## Authored verification coverage and remaining gates

`engine/tests/test_lens_cohort_native_unrun.py` authors fixture checks for exact
ABI layouts, full-grid/tail tile transport, pointer identity, temporary-byte
lifetime, input refusal, explicit manual depth, whole-source validation before
tiles, admission before allocation, immutable metadata, cancellation/exception
cleanup, post-tile/finish failure, missing implementation and no partial return.
The mock only copies source tiles; it does not implement the lens algorithm.

Opt-in real-native fixtures require `LRT_TEST_LENS_COHORT_NATIVE=1` and a separately
packaged exact artifact. They never build or install one. These fixtures also
remain unrun. ABI conformance, numerical/FFT correctness, photographic quality,
full-resolution 24MP behavior, memory measurement and benchmark acceptance are
separate remaining gates, not inferred from static source checks or mocks.
