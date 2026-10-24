# Original skin whitening and rosiness core

Status: **AUTHORED / UNRUN**. New Rust source, Python boundary/state, build hook,
and authored fixtures only. No product imports, tests, builds, compiler,
typechecker, inference, benchmarks, downloads, installs or Git writes were run
for this change. Static source review/AST parsing does not establish compiled
correctness, photographic quality, speed, host integration or feature completion.
Qoder's separately authorized local execution and real-image review remain open.

## Distinct behavior, not a renamed existing control

Operation `lnx.skin_finish.v1` accepts exactly:

    {"version": 1, "whitening": 0.0, "rosiness": 0.0}

Both amounts are finite numbers in [0,1]. Zero is neutral; signed zero is accepted
as zero. Booleans, missing/extra keys, wrong versions, masks, IDs and source data
are rejected by `skin_finish_state.check`. `None` yields a fresh neutral recipe.
This recipe is portable intent only, never transferable skin-support evidence.
`active` tests for a nonzero amount. `capability()` returns exactly
`skin_finish_available` and `skin_finish_reason`; its check proves library/ABI
availability only, not semantic masks, final rendering or photographic acceptance.

The public [PixCake skin guide](https://www.pixcakeai.com/guide/32465), read
2026-10-24, distinguishes whitening toward a brighter/cool-white skin appearance
from increasing rosiness. These correspond to handbook references
`LNX-REF-PC-32465-C-d82f09f52f` and `LNX-REF-PC-32465-C-60936d5259`. The guide
supplies behavior, not an algorithm, numerical scales, colorimetric equivalence
or source code. No proprietary implementation, assets or model were copied.

This is an original independent per-pixel operation. Existing temperature/tint
and exposure behavior and ABIs remain untouched. This is not smoothing, texture
synthesis, skin detection, automatic complexion matching or a full-body detector.
No neighboring pixel is read. It can operate only where the host supplies valid
semantic skin coverage. A face/body rectangle alone is not sufficient evidence.

## Exact original mathematics

Decode encoded working-sRGB to f64 linear light with the standard transfer curve.
Use the existing local original sRGB-primary matrix and D65 reference white
(x=0.3127, y=0.3290) to form XYZ and CIELAB. This is D65-relative CIELAB, not the
D50-adapted CSS `lab()` color. Low-light L*/inverse-L* branches are expressed
without subtractive cancellation; f64/float32 quantization still applies.

Let `l=L*/100`, whitening `w`, rosiness `r`, and `e=4l(1-l)`, using source l.

1. Lift `l' = l + 0.18 w l(1-l)`, then `L*' = 100 l'`.
2. Retain `s = 1 - 0.12 w e` of source chroma. Set `a_w = s a*` and
   `b_w = s b* - 1.5 w e`. This is a restrained move toward a cool-neutral target,
   not a plain luminance exposure multiplier. For ordinary positive-b* skin it
   decreases yellow chroma; already very blue pixels can become less blue as they
   move toward that target. No arbitrary input color is assumed to be skin.
3. Compute `d = 5 r e / (1 + (max(a_w,0)/20)^2)`. Set
   `a*' = a_w + d`, `b*' = b_w + 0.25 d`. This small warm-red direction, its
   luminance gate and already-red restraint distinguish it from constant +a* tint.
   Its requested increase is bounded by 5 a* and 1.25 b*. Rosiness does not change
   the whitening-adjusted L*; when w=0 use the source Y directly.
4. Invert L*' to target Y. Attempt the requested Lab at that Y. If out of gamut,
   jointly scale a*' and b*' toward zero using exactly 24 bisection steps, keeping
   only strictly in-gamut linear-sRGB candidates. The exact neutral `[Y,Y,Y]`
   anchor is the fallback. There is **no RGB channel clipping**, including as a
   numerical repair. This bounded search need not find globally maximal chroma.
5. Blend source and corrected RGB using coverage as a convex linear-light mix,
   and encode to float32 sRGB. Validate every output before publication.

All numeric coefficients are original conservative product choices, not standard
whitening settings, Kelvin, measured perceptual thresholds, medically meaningful
values, recovered commercial parameters or proof of visual equivalence.

### Guarantees and important limits

The lift fixes l=0 and l=1, is nonnegative, and adds at most 4.5 L*. Its derivative
with respect to l is `1+0.18w(1-2l)`, within [0.82,1.18]. Thus it is strictly
monotone in l and nondecreasing in w on [0,1]. Gamut reduction keeps requested
Y, so in exact arithmetic the lift's tone order is independent of source chroma.
For fixed coverage c, output Y is `(1-c)Y+cY'(Y)`, also monotone. This retains
luminance ordering/local detail without spatial smoothing, not unchanged contrast
amplitude. The lift deliberately compresses highlight contrast modestly.

Those mathematical statements are not bit-level tone-order proofs after matrix
roundoff or float32 output. Very close inputs may quantize to the same value;
near a gamut threshold, numerical differences need tolerance. Different coverage
or settings between pixels can reverse global order. No monotonicity of every
RGB channel, output chroma, perceived hue or perceived redness is promised.
Gamut compression can attenuate or even offset the requested red shift on highly
saturated colors. Common Lab chroma scaling does not guarantee perfectly stable
perceived hue, and conservative search can desaturate too much in nonconvex gamut
regions. These limits need photographic validation, not a blanket quality claim.

All-zero or all-one RGB endpoints are source bit copies at all controls. Neutral
controls and exactly zero support are also bit copies, including signed zeros.
Both native and Python reject nonfinite/out-of-range input even on these paths.
Python independently verifies the exact protected-pixel invariants on output.
No output is published on cancellation or errors; raw FFI callers must discard
all private output after any failure even if some pixels were already written.

The host must authenticate photograph, revision, person/face, ROI, geometry and
transform, plus semantic skin masks and exclusions (eyes, lips, hair, clothing,
background, occlusions, protected pixels). Coverage is permission, not a
calibrated probability. This kernel cannot authenticate an array's origin or
color-space label. It accepts opaque, unpremultiplied SDR RGB only, not alpha,
HDR, tensors or unlabelled implicit color conversions. Re-render from the
chosen original stage snapshot, never repeatedly apply to a prior result.

## Python, ABI, resource and cancellation contract

`skin_finish_native.available()` checks loading, actual symbols and ABI 1.
Missing/unloadable/wrong-ABI libraries are unavailable, never a Python fallback,
runtime build or exposure/tint substitution, even for a neutral `apply` request.

    apply(rgb, coverage, whitening, rosiness, *, cancelled=lambda: False)

RGB is exactly H×W×3 native float32 encoded working-sRGB in [0,1]. Coverage is
H×W native float32 in [0,1]. Strided inputs are allowed but copied into independent
contiguous read-only snapshots; callers must not mutate during copying. Return
is an owned, writable, C-contiguous float32 RGB array. No input is retained or
modified. The cancellation callable must remain valid for this synchronous call.

`lrt_skin_finish_abi()` returns 1. The separate ABI is:

    int32_t lrt_skin_finish_apply_v1(
        const float *source, size_t source_len,
        const float *coverage, size_t coverage_len,
        size_t width, size_t height, float whitening, float rosiness,
        float *output, size_t output_len,
        int32_t (*cancel)(void *), void *context);

Lengths count float32 elements, not bytes. Status 0 means success; 1 ABI, length,
dimension or buffer error; 2 invalid controls; 3 invalid pixels; 4 cancellation;
5 resource rejection; 6 contained Rust panic. Native checks alignment, checked
sizes/address addition and no output/input overlap before forming slices. This
cannot establish allocation ownership, lifetime or pointer validity. Callers must
provide live immutable inputs, exclusive output and valid callback/context. The
callback must not unwind, reenter or mutate these buffers. `catch_unwind` requires
unwind-enabled builds and does not contain invalid pointers, callback faults or
aborts. Python catches callback exceptions then re-raises outside the C boundary.

Dimensions are 1..65536 with at most 64 million pixels. Native admission permits
at most 1.6 billion gamut evaluations (25 per pixel worst case); seven float32
buffer values per pixel must fit 2 GiB. Native uses constant stack scratch and no
image heap. Python estimates caller RGB/mask + snapshots + output at 44 B/pixel
plus 8 MiB allowance, capped at 3 GiB; its additional allocation estimate is
28 B/pixel plus allowance, admitted against the existing fail-closed cgroup/CPU
memory budget helper. These ceilings are not speed or OOM guarantees.

Native polls before validation, every 256 pixels in validation/render and after
render. Worst-case 6400 gamut evaluations occur between rendering polls. Python
copies/validates in blocks of at most 4096 pixels with cancellation checks, and
polls before returning. Allocation/library loading are not interruptible inside
their system calls. A callback exception or final late cancellation discards output.

The separately authorized build hook is `sh packaging/build-skin-finish.sh`.
It uses dependency-free Rust with unwind enabled and atomically replaces only a
completed `liblrt_skin_finish.so`; it was authored, not run. Cargo builds likewise
require explicit local execution authorization. No Cargo.lock or binary is added.

## Primary research and licenses

Read 2026-10-24. All source is original project GPL-3.0-or-later code. Reused local
math/FFI/boundary patterns come from `core/skin_colour` and its Python bridge;
those files and ABI were not changed. No external code, paper prose, image, model
or dataset is vendored, and no external dependency is introduced.

- [CIE ISO/CIE 11664-4:2019 public description](https://cie.co.at/publications/colorimetry-part-4-cie-1976-lab-colour-space-1)
  establishes CIELAB's lightness/chroma/hue purpose and reverse conversion. Only
  the public description was read, not the purchased standard. Copyright CIE;
  no publication material redistributed and no conformance certification claimed.
- [W3C CSS Color 4](https://www.w3.org/TR/css-color-4/) supplied mature
  color-conversion/gamut-mapping background. Its discussion warns that chroma
  reduction can over-desaturate and that Lab hue paths are not perceptually
  uniform. Its specific CSS algorithms/sample implementations were not copied.
  The standard's D50 Lab and CSS gamut policy are not this operator's contract.
- [W3C document license](https://www.w3.org/copyright/document-license-2023/)
  and [software/document license](https://www.w3.org/copyright/software-license-2023/)
  distinguish specification and marked code-component redistribution terms.
  This change links research and independently expresses standard mathematical
  relations rather than adapting W3C code or redistributing specification text.
- [PixCake guide](https://www.pixcakeai.com/guide/32465) was used solely to align
  high-level whitening/rosiness direction with the handbook references. No reuse
  license for its proprietary implementation is assumed or needed here.

The quadratic lift, cool-neutral control, gated red vector, parameter bounds and
safety composition are original engineering designs. CIE/W3C do not validate
these product controls or imply that their photograph-level appearance is good.

## Authored, unrun acceptance fixtures

`core/skin_finish/tests.rs` covers bitwise no-ops/endpoints, exact original formula,
lift monotonicity and bounds, distinct axes, linear-light coverage, saturated and
near-endpoint gamut/L*, chroma feasibility, gray-detail order/no neighbor effects,
repeatability, invalid pixels/settings, budget/shape/length guards, staged
cancellation, pointer overlap/misalignment and ABI callback behavior.

`engine/tests/test_skin_finish_native_unrun.py` covers transport ownership,
strides, inputs, callbacks, cancellation, error publication, resource checks,
strict recipe/capability shape and real-ABI numeric fixtures gated on a prebuilt
library. Stub fixtures test transport only, not pixel mathematics. Every fixture
is **UNRUN**. Qoder must run native and engine tests, then diverse genuine skin,
colored light/makeup/occlusion, exclusion-edge, highlight/shadow, preview/export,
resource and cancellation review. Source presence is not a passed test.
