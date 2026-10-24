# Facial skin chromatic-evenness numerical contract

Status: **AUTHORED / UNRUN**, 2026-10-24. Source and acceptance fixtures only.
No product import, test collection/execution, build, compiler, typecheck, model
inference, download, benchmark or Git write was performed. Nothing here establishes
numeric correctness, photographic quality, native installation, CPU/GPU parity,
latency or completion of the full reference feature.

## Exact scope and separation from old smoothing

Exact partial requirement: `LNX-REF-PC-32465-C-60b7c0e3d1`, AI肤色统一（脸部）.
The [official PixCake guide](https://www.pixcakeai.com/guide/32465) describes uneven
facial tone, red cheeks and color patches. This is a behavioral reference only;
it does not disclose an algorithm, trained model or proprietary numerical parity.

The new operation is `lnx.skin_evenness.v1`, with exactly:

    {"version": 1, "amount": 0.0}

Amount is finite0..1; zero, including negative zero, is neutral. Boolean numbers,
wrong versions, unknown keys and stored radius/source/face/reference data refuse.
`None` returns fresh neutral intent. Capability keys are exactly
`skin_evenness_available` and `skin_evenness_reason`; they describe required native
symbols/ABI loading, not anatomy confidence or image acceptance.

This dedicated source-owned chromatic operation is distinct from old
`skin.broad` frequency smoothing, scalar brightness/whitening, uniform target skin
color, generic blur/heal, texture/clarity, finish and gloss. Old recipe meaning is
unchanged. This is not a learned defect classifier, physical material/illumination
separation, ethnicity/skin-class target, body coverage or cross-person matching.

The same-face statistical reference assumes a useful population of valid skin
samples. A face with widespread color bias may retain that bias because it is its
own reference. Legitimate makeup, shadows, blush, lighting or skin variation can
be affected. Conservative photometric gates are not proof of skin identity or a
calibrated uncertainty model. Host anatomy evidence/exclusions remain mandatory.

## Input ownership and source scope

All image inputs are exact native float32 HWC3 opaque, unpremultiplied, encoded
working-sRGB-D65 SDR in [0,1]. Coverage is exact float32 HW in [0,1], not an alpha
channel or calibrated probability. HWC2 displacement is separate signed data, not
encoded RGB. Reject nonfinite, HDR/out-of-range, tensors, implicit color conversion,
wrong channels, wrong sizes and oversized resources. No RGB8 image path exists.

The host must authenticate photograph/revision, original effective-source pixels,
person/face, geometry/transform and source-grid scale. Actual measured face-skin
coverage must exclude eyes, lips, teeth, nostrils, hair, clothing, background,
occlusions, foreign people and protected regions. A bare rectangle is not semantic
permission. Array contents cannot prove ownership; the host binds provenance.

Preparation sees every positive same-face coverage sample. It may use the full
source grid, or the whole own-face positive-support bounding window plus a real
`2*radius+1` source halo clipped only at true image bounds. The guided dependency
needs2*radius; the extra pixel is conservative host policy. A small output tile
plus halo is insufficient for the global reference. Solve once for the complete
own face, then crop/merge the prepared field for rendering. Never rerun reference
selection per tile or feed an edited current stage/previous result into prepare.
Pixels with zero coverage do not influence any statistic, including guidance.

Radius is a strict Python int4..256, derived on the actual source/render grid from
`ceil(.08*min(measured FACE_OVAL width,height))`. Refuse unsupported/degenerate
scales rather than clamp or invent scale. No radius is saved in the recipe.
Preview/export derives its own measured-grid radius and source-owned field; no
silent proxy/downsample or fabricated/replicated halo is permitted. Real image
borders truncate to actual samples. ROI/full-frame equivalence is mathematical,
not a promise of bitwise rolling-sum identity on every platform.

## Source reference and original masked guided chroma

All statistics use float64 arithmetic on the owned source snapshot. Decode sRGB:
`v/12.92` for encodedv<=.04045; otherwise `((v+.055)/1.055)^2.4`.
Linear source luminance is `I=Y=.2126R+.7152G+.0722B`.
Let `S(a,b,z)=t²(3−2t)`, `t=clamp((z−a)/(b−a),0,1)`.
This bounds evidence, never clips RGB output.

1. Photometric reliability is
   `r=S(.01,.04,Y)*(1-S(.70,.90,Y))*S(.002,.008,min(linear RGB))`
   `*(1-S(.95,.995,max(encoded RGB)))`. Set `w=coverage*r`.
   When w=0 the sample is absent, not a zero-valued observation. Positive w
   guarantees genuinely positive channels, so log ratios use actual values with
   no epsilon pseudo-channel: `u=log(R/G)` and `v=log(B/G)`.
2. Global reference eligibility is `w>=.75`. Require at least64 actual eligible
   same-face source pixels. Otherwise status7 refuses active preparation.
   Reference `(tu,tv)` is the exact componentwise sample median, with the arithmetic
   midpoint of the two central values for even counts. It is a robust statistical
   reference, not a necessarily observed pixel or a perceptual target palette.
   Original deterministic median-of-medians selection uses groups of five,
   cancellable bounded work and one reusable float64 sample buffer. No quantized
   histogram, RGB8 reduction, randomized selection or uncancellable library sort.
3. Within each real radius-r square, first sum `w,w²,w*I,w*I²,count(w>0)`.
   A center must have w>0; require total weight>=4, at least8 actual valid samples,
   effective count `(sum w)²/sum(w²)>=8` and weight/actual window area>=.15.
   Missing neighborhoods remain absent. Compute meanI and
   `varianceI=max(sum(w*I²)/sum(w)-meanI²,0)`; this only removes negative moment
   roundoff, not signal values. The source reference is independent of this gate.
4. A second independent moment pass over the same original samples sums
   `w*u,w*v,w*I*u,w*I*v`. For each admitted center, separately for c=u,v:
   `meanC=sum(w*c)/sum(w)`,
   `aC=(sum(w*I*c)/sum(w)-meanI*meanC)/(varianceI+.03²)`,
   `bC=meanC-aC*meanI`.
   Store `(w*aU,w*bU,w*aV,w*bV,w)` only for admitted coefficient centers.
   Unsupported coefficient centers store zero mass, never pseudo observations.
5. A radius-r box over valid coefficients yields
   `baseU=(sum(w*aU)*I+sum(w*bU))/sum(w)` and likewise for V.
   The center must itself have valid coefficients; require coefficient mass>=4
   and mass/actual window area>=.15. Coefficient support is distinct from source
   sample support. If no output center has adequate final context, status8
   refuses the active transaction, even if the global reference had64 samples.
   Individual unsupported centers may have zero shift when valid context exists
   elsewhere. Already-even valid context is distinct from unavailable context.
6. Let `d=(tu-baseU,tv-baseV)` and `n=norm(d)`. For n<=1e-6 set zero shift; this
   explicit deadzone covers float32 source decode/moment roundoff on constant
   chroma. Otherwise the displacement is
   `delta=amount*w*.45*.20*tanh(n/.20)*d/n`.
   Its Euclidean norm is bounded by .09. Both components are cast to float32;
   boundary validation allows only1e-7 norm tolerance. Local/current luminance is
   never replaced by a filtered base. The current fine chroma is not replaced by
   the source base either: application adds the bounded log-chroma displacement.

These are original conservative engineering thresholds and a coverage-normalized
adaptation of local linear guidance, not empirically calibrated perception/noise
bounds, official PixCake coefficients, a published algorithm reproduced exactly,
or proof that unwanted redness has been separated from legitimate skin detail.
Regression can retain meaningful color boundaries but cannot guarantee no halo,
bleeding or undesirable color changes. Actual-photo acceptance remains open.

## Pointwise application to actual current-stage luminance

    prepare(source_rgb, coverage, amount, *, radius, cancelled=lambda: False)
        -> owned read-only contiguous float32 HWC2 log-chroma displacement
    apply(current_rgb, shift, *, cancelled=lambda: False)
        -> owned writable contiguous float32 HWC3 encoded RGB

The current stage can already contain color/finish/gloss/texture edits. Do not add
an encoded RGB delta measured from the original source: that would not preserve
actual current-stage luminance. The explicit two-channel field is the only
prepared contribution. `du` shifts log(R/G); `dv` shifts log(B/G).

For each actual current pixel:

1. Exactly zero shift, pure black or pure white returns the original pixel bits,
   including signed zero. No unnecessary decode/re-encode occurs.
2. Decode actual current RGB `q` and calculate its own `Yq`.
3. Form `p0=[qR*exp(du), qG, qB*exp(dv)]`, then
   `p=p0*Yq/Y(p0)`. Multiplicative ratios support zero current channels without
   inventing them or taking log(0). The proposal has the same linear Y as q.
4. Choose one scalar t initially1. For each channel with `d=p[c]-q[c]>0`, bound
   t by `(1-q[c])/d`; with d<0 bound by `-q[c]/d`. If t=0, copy current bits.
   If t<1, multiply by `1−1e−12` to stay inside the gamut boundary under roundoff.
   Then `result_linear=q+t*(p-q)`. Since both endpoints have the same Y, this one
   interpolation preserves Y and all three channels' gamut together. There is no
   independent-channel clamp, RGB clipping repair, luma smoothing or luma gain.
5. Encode with the sRGB inverse transfer and cast to float32. Refuse nonfinite or
   out-of-gamut numerical results rather than silently clip. The Python boundary
   independently verifies `abs(Y(result)-Y(current))<=2e-7` per pixel. This covers
   intended float32 encoding roundoff, not permission to change luminance texture.

The same algebra is the contract for host CPU/GPU renderers. A separately authored
Torch implementation is not native parity evidence until executed and compared.
Preserving linear Y is not identical to preserving perceived brightness or all
perceptual skin texture. Gamut restraint can attenuate the requested chroma edit.

## ABI, ownership and atomic refusal

`lrt_skin_evenness_abi()` returns1. See `core/skin_evenness/skin_evenness.h` for the
full declarations. Both v1 entrypoints accept explicit source/current, coverage/
field and output float-element lengths, dimensions, cancellation callback/context.
Prepare additionally takes amount and measured radius. RGB lengths are3*N,
coverage N, displacement2*N. Output must overlap no input; inputs may overlap
one another because they remain immutable. Pointers must be live and aligned.

Status0 succeeds;1 ABI/length/dimensions/alias;2 settings;3 pixels/numerical refusal;
4 cancellation;5 resource admission/allocation;6 contained panic;7 insufficient
own-source reference;8 insufficient supported guided context. Null/alignment,
checked byte ranges, expected lengths and output/input overlap are checked before
creating slices. Actual allocation validity and safe callbacks remain the caller's
responsibility. Panic containment does not protect foreign faults or aborts.

All active native computation writes only private Rust results. Every nonzero
native status leaves the caller output untouched. After all fallible work and the
last cancellation poll, one final non-cancellable copy publishes success. That is
atomic error/publication behavior, not inter-thread synchronization, crash safety
or a promise to cancel during the final copy. Neutral prepare validates every
input, polls, then publishes its zero field without demanding source references.

Python makes independent contiguous read-only snapshots of inputs, allowing
strides but requiring the caller not mutate during snapshotting. Preparation
returns an owned read-only field; application returns a new owned writable image.
No caller input is mutated or retained. Private outputs are checked before return;
callback exceptions re-raise after leaving the C boundary, and late cancellation
discards even a successful private native result. Missing native code refuses
neutral requests too. No runtime download, build, fallback or broad-skin alias.

## Resource and cancellation contract

Dimensions1..65536, at most32,000,000 pixels. This unchanged pixel ceiling is not a
promise that every32M request fits the host's combined pipeline memory/latency.
Checked arithmetic and a4GiB numerical budget precede native slices/allocations.

Preparation native scratch peak is88 B/pixel by allocated array accounting:
- First moments40 plus reusable coefficient/statistics storage40 =80 B/pixel.
- After explicitly dropping first rows, cross moments32 plus coefficients40 =72.
- After dropping cross rows, coefficient rows40 plus coefficients40 plus private
  output shift8 =88. Reference-selection scratch8 exists earlier and is dropped.

FFI caller inputs source12+coverage4 and output8 add24 B/pixel, for native
admission112 B/pixel. Python additional estimate is snapshots16+output8+native88
=112 B/pixel plus8MiB validation/allocator allowance. Existing caller inputs add16,
so Python total admission uses128 B/pixel+8MiB. Pure
`memory_estimate((H,W))` returns the additional estimate, with no native load,
image allocation or cgroup query.

Application native scratch is12 B/pixel private RGB. FFI current12+field8+output12
plus scratch12 totals44. Python additional estimate is snapshots20+output12+
native12=44 B/pixel+8MiB; caller inputs add20, giving64 B/pixel+8MiB total.
`application_memory_estimate((H,W))` is likewise pure. Actual calls admit additional
memory against the existing fail-closed CPU/cgroup estimate. Host still owns its
combined frame/anatomy/multi-face/intermediate/GPU admission. Estimates are not
measured process peaks, OOM immunity or latency guarantees.

All box passes are O(N) sliding sums independent of radius-squared work; source
samples are recalculated from immutable RGB to keep memory bounded. Exact median
selection is worst-case O(N) with cancellable groups/partitions and logarithmic
recursion depth. Repeated sRGB decoding is a compute tradeoff, not a performance
claim. Native validation, fill, reference collection, selection, rows/columns and
rendering poll at bounded loop intervals; most loops poll every256 samples, small
selection groups also poll. Python copies/checks at most4096 pixels per block and
polls around native loading/call and before publication. Allocation/loading system
calls and the final successful copy are not interruptible.

The authored offline build hook `sh packaging/build-skin-evenness.sh` builds
original dependency-free Rust with unwind enabled and atomically replaces the
finished `.so`. It was not run; Cargo is also not authorized/executed. No binary,
Cargo.lock, model, downloaded implementation or runtime compiler is added.

## Primary background and license decision

All new implementation is original GPL-3.0-or-later project source, with the full
license at the repository LICENSE. Existing local ABI, ownership and resource
conventions are reused. No external code, assets, paper text or model is vendored.
Conceptual research supplied by the parallel source review, dated2026-10-24:

- [He, Sun and Tang, Guided Image Filtering](https://people.csail.mit.edu/kaiming/publications/pami12guidedfilter.pdf):
  local linear guidance and luminance-guided chrominance provide conceptual
  motivation. Our masked moments, coefficient-domain validity, split source field,
  exact robust reference, bounds and error contracts are original adaptations,
  not a copied implementation or a claim of identical published behavior.
- [Barron, Convolutional Color Constancy](https://arxiv.org/html/1507.00410):
  log-chrominance translation is conceptual background only. We do not implement
  its learned color-constancy estimator or claim physical illumination removal.
- [Official PixCake facial-skin guide](https://www.pixcakeai.com/guide/32465):
  supports the named uneven-tone behavior, not proprietary implementation parity.

Publicly readable descriptions are not a license to proprietary code or models.
No benchmark or market behavior inference establishes maturity or full completion.

## Authored acceptance and remaining gates

Rust fixtures cover exact medians, neutral/constant-chroma identity, own-tone
statistical distinction, chromatic patch response, actual current-Y/detail
preservation, unsupported/background independence, retained sub-RGB8 differences,
amount and vector bounds, robust reference outliers, common gamut interpolation,
explicit reference/context refusal, cancellation/private publication, full-own-face
halo equivalence, ABI parity/null/alias/alignment/length and32M resource limits.
Python fixtures cover portable state, independent strided snapshots, strict
fields/controls/radii, pure estimates, missing-core refusal, callback exceptions,
status distinctions, corrupt-field rejection, independent current-Y verification
and late cancellation. Protocol fakes do not exercise image mathematics.

Every fixture is **UNRUN**, including collection/imports. Still required: compiler
and native tests; real installed ABI; engine/UI/serialization/rollback acceptance;
CPU/GPU parity; preview/export source-scale consistency; memory/latency/cancellation
measurement; multiple skin tones, makeup, freckles, lighting/color casts, shadows,
noise/compression, masks, exclusions and multi-face isolation; halo/perceptual
review and calibrated reference/admission policy. No full-body or proprietary AI
completion is claimed by these authored changes.
