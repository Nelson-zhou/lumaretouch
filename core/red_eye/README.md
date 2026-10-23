# Conservative flash red-eye correction

Status: **AUTHORED / UNRUN**. This is source, an explicit build hook and authored
fixtures, not a completed-feature or acceptance claim. No compiler, imports,
build, tests, typecheck, inference, benchmarks or real-image review were run.

## Scope and support ownership

This is an original, non-generative colour operator. It is not an AI model,
segmentation system, flash detector, medical assessment, iris recolouring tool
or replacement eye. The host supplies **target-owned inward central-iris
geometric candidate coverage**, bound to the exact source identity, face/eye,
source revision, transform and raster geometry. This conservative inward
candidate is not a measured pupil or semantic iris segmentation. A face/eye
bounding box, redness threshold or arbitrary unowned mask is not an equivalent
substitute. Landmark-derived geometry does not prove anatomical accuracy. The
native numerical API cannot authenticate its ownership or quality.

Coverage is float32 H×W in [0,1], including the host's feathering, permitted
support and correction density. The operator never grows support or samples
neighbouring pixels. At zero support every channel is copied bit-for-bit.
The host is responsible for excluding eyelids, sclera, lashes, surrounding skin,
unrelated faces and uncertain geometry, rather than treating this colour gate as
a repair for a wrong mask. Existing source-owned local protection must remain in
effect. Changing target/source/revision invalidates stale support. The current
integration supplies a crop bounding both inward eye candidates, with aligned
RGB and support arrays; full-source geometry must be recomputed/validated before
cropping. An invalid geometry is a refusal, not an inferred-eye fallback. A valid
candidate with no qualifying red is an exact no-op, not an error.

Colour alone cannot establish flash red-eye. **Natural dark red/brown iris
pixels can pass these gates and be darkened**, even within a correctly placed
inner-iris candidate; an explicit limitation fixture records that failure mode. Very dark
red, weak red-eye and non-red animal eyes may remain uncorrected. A saturated
red highlight is not distinguishable from a red flash artifact here. Near-neutral
catchlights are preserved by the gates, but there is no semantic highlight
detector. Review the original and the correction; lower the amount or omit the
operation when it damages natural iris colour. Missing/overexposed iris texture
and original eye colour cannot be reconstructed by this operator.

## Method and primary references

Sources read on 2026-10-23:

- [GIMP Red Eye Removal manual](https://docs.gimp.org/en_GB/gimp-filter-red-eye-removal.html)
  recommends selecting the iris boundary before applying its threshold filter.
- [GEGL operation documentation](https://www.gegl.org/operations/gegl-red-eye-removal.html)
  identifies a point filter for camera-flash red-eye and labels its license GPL3+.
- [GNOME's GEGL red-eye source](https://raw.githubusercontent.com/GNOME/gegl/master/operations/common-gpl3%2B/red-eye-removal.c),
  `operations/common-gpl3+/red-eye-removal.c`, compares weighted red with both
  weighted green and blue in encoded RGB, then changes only red. Its file header
  explicitly specifies **GNU GPL version 3 or later (GPL-3.0-or-later)**, credits
  Robert Merkel (2004), Andreas Røsdal (2006), Robert Sasu (2011), and identifies
  Geoff Kuenning's earlier GIMP Perl plugin as background. This operation's
  license must not be confused with GEGL library-wide LGPL licensing.
  [Upstream GPL text](https://raw.githubusercontent.com/GNOME/gegl/master/COPYING).

The references motivate selected-region, red-channel-only correction. **No GEGL
or GIMP source, coefficients or implementation is copied, linked or vendored.**
This Rust implementation uses original smooth ratio/absolute gates and an
unweighted green/blue mean, not GEGL's threshold formula or numerical behaviour.
The new files follow this repository's GPL-3.0-or-later licensing; see the root
`LICENSE`. The chosen constants are engineering starting points, not a published
calibration, a validated portrait setting or a claim of equivalence to GIMP.

Input is **encoded working-sRGB**, float32 H×W×3, finite SDR [0,1]. The operation
does not convert transfer functions or colour spaces. Do not pass linear RGB,
premultiplied channels, RGBA, HDR, negative values or another gamut as sRGB.
Colour conversion and alpha policy belong to the host.

There is one amount in [0,1]. For each covered pixel:

1. Let M = max(G,B), so red must dominate **both** other channels.
2. Ratio gate = smoothstep(1.5, 2.5, R / max(M, 0.000001)).
3. Absolute gate = smoothstep(0.08, 0.25, R − M).
4. Alpha = coverage × amount × ratio gate × absolute gate.
5. R′ = R + alpha × ((G + B)/2 − R). G′ = G; B′ = B.

Here smoothstep is the cubic t²(3−2t) after clamping the normalized t to [0,1].
Both gates have exact-zero regions and continuous first derivatives at their
ends. The absolute test suppresses near-black ratio amplification. The amount
controls correction strength, not detection threshold; no hidden second
setting is exposed. Arithmetic uses f64 intermediates and float32 output.

The result lowers only strongly excessive red, never below the existing G/B
mean, and never raises a channel. It is a blend with the same original pixel,
not replacement by black or newly generated iris detail. G/B are copied directly
and remain bit-exact, including signed zero. Zero amount, zero support and a
zero gate take exact-copy paths. Neutral colours and near-neutral highlights
(R ≤ 1.5×max(G,B)) remain unchanged; all highlights with max(G,B) ≥ 2/3 are also
excluded for valid SDR input. A red-dominant pixel below absolute excess 0.08
is unchanged. No clipping, blur, sampling, rescaling or global desaturation is
performed. All inputs are validated even when neutral or uncovered.

Always evaluate preview/export from the same original owned source snapshot.
Repeatedly applying the result to itself would accumulate correction and is not
the intended single-pass operation. This foundation does not wire host consumers
or change their composition, colour pipeline or layer ordering.

## Python contract and resource safety

`red_eye_native.apply(rgb, weight, amount, *, cancelled=lambda: False)` returns
an independent, writable, C-contiguous float32 array of the same shape. Inputs
must be exact NumPy ndarrays, including strided ones, with the exact dtype and
shapes. Booleans, strings, nonfinite and out-of-range amounts are rejected.
NumPy and Torch consumers must use this one native implementation. Torch hosts
explicitly stage float32 CPU arrays and restore the desired device afterwards;
this module neither imports Torch nor implements a second colour formula.

The bridge creates independent, read-only snapshots even for read-only or
contiguous inputs. **The caller must not mutate either input during snapshot
copying.** No input storage is mutated or retained. Output never aliases input.
Native failure, cancellation or callback exceptions do not publish partial
output. Final row-wise checks reject invalid SDR, G/B changes, increased red,
and changes outside support or with zero amount. These checks are invariants,
not a duplicate colour implementation or proof of a malicious library's safety.

`native()` loads `engine/src/lumaretouch_engine/bin/liblrt_red_eye.so` and checks
ABI and symbols. `available()` verifies that actual load, not only the path.
Missing/broken libraries fail closed, even at zero amount; there is no silent
fallback, runtime build, model invocation or download.

Admission applies to the supplied RGB/support crop and matches the existing
teeth-colour boundary: nonzero dimensions ≤65,536,
at most 64,000,000 pixels, and a conservative 3 GiB static full working-set cap.
The estimate is 44 bytes/pixel including caller inputs, snapshots and output,
plus 8 MiB bounded validation scratch. Additional allocation admission checks
28 bytes/pixel plus that allowance against the existing fail-closed CPU budget
reader. Missing/ambiguous budget metadata is an error; estimates do not guarantee
allocation success. There is no proxy image or precision downgrade on refusal.

Cancellation is checked before admission, around copying/allocation, during
native validation/rendering every ≤4,096 pixels, in final row validation, and
before return. Python copying is bounded by a 4,096-pixel row group or one
maximum-width row; individual allocator calls cannot be interrupted. Cancellation
callbacks cannot cross the ABI with an exception: the bridge catches, stops and
re-raises them on the Python side.

## C ABI 1

`lrt_red_eye_abi()` returns 1. `lrt_red_eye_apply_v1` arguments, in order:

1. source float32 pointer, source element count;
2. coverage float32 pointer, coverage element count;
3. width and height (`size_t`);
4. amount (`float`);
5. output float32 pointer, output element count;
6. optional `int (*cancel)(void*)`, opaque callback context.

Lengths count elements, not bytes: source/output are 3×width×height and support
is width×height. The allocation-free kernel checks null/aligned pointers,
lengths, overflow and output overlap before making slices. Read-only input/input
overlap is allowed. The caller still guarantees valid live allocations, immutable
inputs, exclusively writable output and a callback/context that cannot unwind,
reenter or mutate buffers. Numerical pointer checks cannot prove these facts.

Status codes: 0 success; 1 ABI, pointer, dimension, length or alias error; 2 invalid
amount; 3 invalid SDR RGB/support; 4 cancellation; 5 resource limit; 6 contained
Rust panic. All input validation precedes writes, but cancellation during or
after rendering can leave output partially or fully written. **Discard ALL
output for ANY nonzero return**, including cancellation after the last pixel.
The Python boundary enforces this rule. Rust panic containment does not make
invalid foreign pointers or callbacks safe.

## Build and acceptance still required

`packaging/build-red-eye.sh` is an **unrun**, explicit system-rustc hook with no
external crates or network steps. It compiles into a temporary file and replaces
the destination library only after success. Packaging stage/consumers are not
edited by this component. Invoke through `sh` when execution is authorized.

Authored Rust fixtures cover exact neutral/support/channel preservation, dual
dominance, smooth gates, feathering, correction bounds, the natural-red false
positive, invalid SDR/settings/resources, cancellation and C-ABI pointer/alias
rejection. Authored Python fixtures cover strict input, immutable snapshots,
memory admission, output publication, callback errors and optional real-native
checks including explicit Torch staging. Native fixtures skip if the binary is
absent; **a skip is not acceptance**. No tests have been run.

Before release, separately authorize and run compilation and fixtures, then
evaluate real flash and non-flash portraits with varied iris colours, exposure,
catchlights and valid inward central-iris candidates. Check host NumPy/Torch and preview/export
parity, target/revision rebinding, cancellation latency, actual memory use and
manual inspection of natural dark irises. The current source alone establishes
none of those acceptance outcomes.
