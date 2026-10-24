# Original skin texture and fine-sharpening core

Status: **AUTHORED / UNRUN**. This is original source, a Python ABI/state boundary,
an offline build hook and authored acceptance fixtures. No product imports,
tests, compilation, builds, typechecks, inference, benchmarks, downloads,
installation or Git writes were performed for this change. Static source/AST
review is not numerical or photographic acceptance. Separately authorized local
execution and genuine diverse photographs remain required before acceptance.

## Product semantics and scope

The official [PixCake skin guide](https://www.pixcakeai.com/guide/32465), read
2026-10-24, distinguishes signed skin texture decrease/increase from skin
sharpening. The exact reference IDs are:

- `LNX-REF-PC-32465-C-1c80d411ce`: skin texture, left decreases/right increases.
- `LNX-REF-PC-32465-C-46e0c819b6`: skin clarity, described as skin sharpening.

The second is **not Adobe's coarse local-contrast Clarity**. The guide supplies
behavioral intent, not source code, numeric bounds, algorithms, proprietary
weights or proof that this independent implementation looks equivalent. The
texture/clarity entries do not explicitly promise a face/body scope. This host
integration supports authenticated measured **face skin only**. Broader body
skin support and photographic feature completion remain incomplete.

`lnx.skin_texture.v1` accepts exactly:

    {"version": 1, "texture": 0.0, "clarity": 0.0}

Texture is a finite number in [-1,1]; clarity is a finite number in [0,1]. Both
zero is neutral. Booleans, missing/extra keys, other versions, radius, masks,
source identity and support data are rejected. `None` creates a fresh neutral
recipe. Recipe transfer moves only these portable controls, never evidence.
`capability()` returns exactly `skin_texture_available` and
`skin_texture_reason`. Availability means the dedicated native library and ABI
load; it is not skin-support, rendering or photographic acceptance.

This is neither a rename nor a call-through to `ops/guided.py`'s legacy detail
gain, the whole-frame `photo_detail` operation, smoothing, exposure or a global
tone curve. It has its own original Rust algorithm, state and ABI. It does not
claim AI, blemish removal, synthesis, detail recovery or physical skin/albedo
reconstruction. No proprietary code, model, image, parameter or dataset is used.

## Exact original numerical design

All computations below are source-owned: **ORIGINAL effective source** determines
bands and gates. The **CURRENT colour -> finish -> gloss intermediate** supplies
only the pixel to be corrected. Both must share one authenticated source/grid.
Changing a current-stage neighbor cannot alter another pixel's measurements.

1. Decode finite encoded working-sRGB-D65 SDR RGB to f64 linear light. Form
   `Y = 0.2126 R + 0.7152 G + 0.0722 B`, then `L = ln(max(Y,1e-6))`. The floor
   belongs to analysis, not output clipping. Unsupported samples are not decoded
   into the analysis field and contribute exactly zero statistical weight.
2. Independently calculate two masked self-guided bases from this same L. Fine
   radius is `rf=max(1,r//4)` with epsilon `0.04^2`; coarse radius is `r` with
   epsilon `0.11^2`. The second scale is **not** a cascade on the first output.
3. In each real in-domain radius window, compute coverage-weighted source
   moments `W=sum(w)`, `W2=sum(w^2)`, `mu=sum(wL)/W` and
   `var=max(sum(wL^2)/W-mu^2,0)`. No background or other-person pixel is an
   observation. Require center support >0, W>=1, effective sample count
   `W^2/W2>=4`, and `W/window_area>=0.20`. Then `a=var/(var+epsilon)` and
   `b=(1-a)mu`. Nonfinite computations refuse the operation.
4. Average the coefficients over another radius window, weighting each **valid
   coefficient** by its center coverage, and normalizing by the sum of those
   valid weights. Invalid or unsupported coefficients have zero coefficient-domain
   support, not synthetic zero-valued observations. Require a valid center
   coefficient, valid coefficient mass >=1 and mass/window_area>=0.20. Set
   `base=mean(a)L+mean(b)`. Missing bases remain unavailable and cannot render.
5. The medium texture band is `T=fine_base-coarse_base`; the fine sharpening band
   is `D=L-fine_base`. They are edge-adaptive overlapping residual bands, not
   orthogonal Fourier bands or a perfect signal/noise decomposition.
6. Source reliability is `smooth(0.005,0.03,Y)` times
   `1-smooth(0.94,0.995,max(encoded source RGB))`. Here smooth is clamped
   cubic smoothstep. The source edge gate is
   `1-smooth(0.10,0.35,max(abs(L-L_axial_neighbor)))`; all four actual axial
   neighbors must have positive support, otherwise this gate is zero. This is a
   conservative local gate, not proof that halos cannot occur elsewhere.
7. For the clarity gate, calculate a source-only noise proxy from the real
   four-neighbor Laplacian, `noise2=(4L-Lleft-Lright-Lup-Ldown)^2/20`. A sample
   contributes only with a valid fine base and four supported neighbors; its
   weight is the minimum coverage of that center/cross. In a fine-radius window
   normalize the weighted residual mean/variance and mean noise2. Require the
   same >=1 mass, >=4 effective samples and >=0.20 coverage density. Then
   `g=max(energy-1.25*noise,0)/(energy+0.002^2)`, bounded above by one. Missing
   evidence gives g=0. This is not calibrated camera noise estimation. Genuine
   Nyquist detail and low-amplitude detail may be refused; medium-scale noise
   may still be affected by the texture control.
8. Bound the source bands smoothly: `t=0.08*tanh(T/0.08)` and
   `d=0.025*tanh(D/0.025)`. Absolute band values <=1e-10 map to zero to make flat
   fields exact no-ops despite f64 moment roundoff. The requested log change is
   `delta=coverage*reliability*edge_gate*(0.75*texture*t+0.55*clarity*g*d)`.
   Thus `abs(delta)<=0.07375` before gamut restraint. Texture can decrease or
   increase the medium residual; clarity adds only gated fine residual gain.
9. Decode the current pixel to linear RGB, then multiply **all three channels
   by one gain** `exp(delta)`. For positive delta, reduce that gain to at most
   `1+(1/max(current_linear_RGB)-1)*(1-1e-12)`. If peak=0 or gain=1, copy current
   bits. This preserves linear-RGB channel ratios in exact arithmetic and avoids
   independent-channel clipping. Gamut restraint can attenuate positive detail.
   Encode to float32 and validate finite SDR output. No output RGB clipping is
   used as normal processing or numerical repair.

All thresholds, epsilons, gains, bounds and the host scale policy are original
conservative engineering choices, not measured perceptual thresholds, recovered
PixCake parameters or a validated skin/noise solver. Common linear scaling does
not promise unchanged perceived hue/saturation in every display condition.
Color/finish/gloss changes can alter how original bands look when applied to the
current pixel. No blanket quality, noise immunity or no-halo claim is made.

### Source, support and halo contract

The host must authenticate photograph, revision, person/face, geometry and
transforms, measured face skin and exclusions: eyes, lips, nostrils, hair,
clothing, occlusion, background, foreign people and protected pixels. A rectangle
is not semantic permission. The numerical kernel cannot authenticate an array's
origin or color-space label. Coverage is bounded editing permission, not a
calibrated probability. All local moments normalize by actual permission mass.

Radius is a strict host-derived integer 4..256 in the **current render grid**,
not portable recipe data. The renderer's original policy is
`ceil(0.08*min(measured face-oval width,height))`; it must recompute on the
preview/export grid and refuse unsupported scales rather than silently clamp.
The fine/coarse spatial support separation is an original design choice, not a
claimed proprietary setting. Very small or very large faces may be unavailable.

Each guided base depends on a real 2*radius source neighborhood. The clarity
gate adds at most a fine-radius neighborhood to the fine base dependency,
giving 3*rf, or rf+1 for its Laplacian source samples. Both are <=2*r. Consequently
full-source evaluation or a **genuine 2*r halo** is sufficient before cropping
the requested output. No invented, replicated, resampled or other-person halo
is permitted. True image borders are truncated to the real domain; a cropped
tile border without the dependency halo is not an equivalent image border.

## Boundary, identity and error semantics

    apply(current_rgb, coverage, texture, clarity, *, reference_rgb, radius,
          cancelled=lambda: False)

Inputs are exact native float32 HxWx3 RGB and HxW coverage, finite [0,1]. RGB is
opaque, unpremultiplied encoded working-sRGB-D65 SDR, not alpha/HDR, tensors,
linear RGB or an implicit profile conversion. Strided arrays are accepted by
making independent contiguous read-only snapshots. The caller must keep inputs
immutable during copying. Return is a new owned writable C-contiguous float32
RGB image; no caller array is mutated or retained.

Both controls zero, exactly zero coverage, and pure black/white **current**
endpoints are exact bit copies, including signed zero. Validation still runs on
neutral/unsupported paths. Flat or unavailable source evidence is unchanged.
Python independently checks output range, neutral identity and protected pixels.
Render from the original source/current chain, never repeatedly from a previous
texture result. Missing native code refuses even a neutral apply request, with
no fallback, download or runtime compilation.

The separate 64-bit host ABI is `lrt_skin_texture_abi()` returning 1 and:

    int32_t lrt_skin_texture_apply_v1(
        const float *current, size_t current_len,
        const float *reference, size_t reference_len,
        const float *coverage, size_t coverage_len,
        size_t width, size_t height, float texture, float clarity, size_t radius,
        float *output, size_t output_len,
        int32_t (*cancel)(void *), void *context);

Lengths count float elements. Statuses: 0 success; 1 ABI/length/dimension/alias;
2 controls/radius; 3 pixel/numerical refusal; 4 cancellation; 5 resources;
6 contained Rust panic. The FFI checks nulls, alignment, checked lengths/address
addition and output/input overlap before creating slices. Inputs may overlap
one another. Caller still owns live allocation validity, pointer lifetimes,
immutable inputs and exclusive output. Panic containment cannot repair invalid
pointers, foreign faults or aborts. Callback/context remain alive; callback must
not unwind, reenter or mutate buffers. Python catches callback exceptions and
reraises after the C boundary. Output is private scratch and must be discarded
after **any** error or cancellation, even when some pixels were written.

## Resource accounting and cancellation

Dimensions are 1..65536 with at most 32 million pixels. All allocation/image
arithmetic is bounded and checked before FFI slices. The core uses fallible
reserved vectors and O(N) sliding box sums, not radius-squared neighborhoods,
global resampling or proxy/downsample fallbacks. Radius is bounded by256.

Peak native scratch is72 B/pixel: source log8 + retained fine base8 + first-pass
moment rows32 + coefficients24, or source log8 + retained fine base8 +
coefficients24 + coefficient rows24 + new base8. First-pass rows are explicitly
dropped before coefficient rows allocate. Later final noise rows40 plus three
scalar fields24 fit below that peak. Caller-owned FFI inputs/output add40 B/pixel,
so native admission uses112 B/pixel capped at4GiB.

Python additional allocation estimate is112 B/pixel (snapshots28 + output12 +
native scratch72) +8MiB bounded validation/allocator allowance. Caller inputs add
28 B/pixel, yielding140 B/pixel +8MiB capped at4GiB. Pure
`memory_estimate((H,W))` returns the additional estimate and does not load native
code, allocate image buffers or query live memory. `apply` admits additional
memory against the existing fail-closed CPU/cgroup estimate. Host still owns the
combined render/anatomy/intermediate admission. These caps do not guarantee
runtime latency or eliminate all allocation failures.

Rust polls cancellation in validation, initial copies, source conversion,
allocation fill, sliding-window initialization/updates and final rendering, at
least every256 loop samples and at row/column boundaries. Python snapshots and
checks in <=4096-pixel blocks, polls around native loading/call and before return.
Allocation/system library loading are not interruptible inside system calls.
A late cancellation or callback failure discards the private result.

The authored offline build hook is `sh packaging/build-skin-texture.sh`. It builds
dependency-free Rust with unwind enabled and atomically replaces only the
finished `liblrt_skin_texture.so`. It was not executed. Cargo likewise requires
separate authorization. No binary or Cargo.lock is added.

## Primary background and licenses

Read2026-10-24. All implementation is original project GPL-3.0-or-later source.
Local ABI/resource/transport conventions are adapted from the project's other
dedicated Rust skin cores. No external implementation, assets or paper text are
vendored. Links are research references, not claims that publication licenses
grant rights to proprietary software or that external authors endorse this edit.

- [He, Sun and Tang: Guided Image Filtering author project](https://people.csail.mit.edu/kaiming/eccv10/index.html)
  describes local linear guidance, edge-aware filtering/detail enhancement and
  radius-independent linear-time filtering. Our support-normalized coefficient
  domains, log source bands, reliability/gamut/resource guards and combination
  are independently written. This is not the unmodified published algorithm or
  an implementation copied from its linked code.
- [Adobe Texture introduction by the ACR Texture lead](https://blog.adobe.com/en/publish/2019/05/14/from-the-acr-team-introducing-the-texture-control)
  motivates separating medium texture from fine sharpening and cautions that
  medium-frequency noise can also be affected. It supplies conceptual context,
  not a source implementation or permission to reproduce proprietary behavior.
- [darktable contrast equalizer manual](https://docs.darktable.org/usermanual/4.6/en/module-reference/processing-modules/contrast-equalizer/)
  documents independent detail scales and warns about halos, gradient reversals
  and noise amplification. We did not copy darktable's wavelet implementation or
  its documentation prose; our two guided scales are a different construction.
- [PixCake skin guide](https://www.pixcakeai.com/guide/32465) provides only the
  two high-level control meanings and exact reference alignment above.

## Authored acceptance and remaining gates

`tests.rs` authors exact no-ops/endpoints, flat-source independence, distinct
signed medium/fine axes, no background/foreign-face statistics, unavailable
coefficient domains, permission-weighted log changes, current-stage independence,
conservative high-frequency/edge rejection, common-gain chroma/gamut bounds,
real-halo comparison, resource/settings validation, staged cancellation and
safe-entry/FFI parity/null/alias/alignment/length tests. All are **UNRUN**.

`engine/tests/test_skin_texture_native_unrun.py` authors strict recipes,
snapshot ownership/strides, numeric/radius/input validation, pure resource
preflight, missing-core refusal, callback/native-error handling and corrupt-output
rejection. Its copy-only fake tests the protocol, not image mathematics. It is
**UNRUN**, including collection and all imported modules.

Still required: compilation/native tests, engine/UI/integration tests, ABI parity
on supported hosts, prebuilt-native installation checks, preview/export scale
comparisons, actual memory/latency/cancel behavior, real skin at multiple tones,
age/detail levels, makeup, noisy/compressed inputs, lighting/exclusions/foreign
people, halo/gradient-reversal review and usability. Broader body-skin texture
coverage remains unavailable. Source presence and static parsing are not proof
of correctness, image quality, speed, parity or release readiness.
