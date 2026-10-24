# Body-to-own-face chromatic matching numerical contract

Status: **AUTHORED / UNRUN**, 2026-10-24. Baseline
`e30f53da51dbfa9b3c5c11598ee210eeb79fb387`. This is original source and authored
acceptance coverage, not a tested/released capability. No product imports, test
collection/execution, compiler, build, typecheck, inference, benchmark, download
or Git writes were performed for this implementation. Static AST/source/hash
checks are not numerical, photographic, ABI or preview/export acceptance.

## Requirement and honest scope

Partial requirement: **LNX-REF-PC-32465-C-d8b09012a9**, guided by the
[official PixCake skin guide](https://www.pixcakeai.com/guide/32465), body/face
colour-difference and uneven-body-colour description. The public guide describes
behavior, not coefficients, licensed source, training or numerical equivalence.

Operation `lnx.body_face_match.v1` stores exactly:

    {"version": 1, "amount": 0.0}

Amount is finite0..1, neutral zero including negative zero. Reject Boolean
numbers, wrong versions, unknown keys, stored source/reference/field/mask data
and saved radius. `None` returns a fresh neutral dictionary. Structural validation
covers active, undo and redo leaves without claiming historical support is live.
Capability keys are `body_face_match_available` and `body_face_match_reason`.

The operation uses a same-person SOURCE FACE robust chroma reference and the
existing SOURCE BODY luminance-guided low-frequency chroma construction. It
reduces source body-to-face chroma difference and body chromatic unevenness,
subject to conservative bounded correction. It does not necessarily make body
and face identical. Application preserves each actual CURRENT body pixel's
linear luminance. This is explicitly not body brightness matching, smoothing,
whitening, learned AI defect classification, material/illumination separation,
an ethnicity/skin-class palette, or brightest/cross-person reference selection.

The separate `lnx.body_skin_evenness.v1` measures its own body reference and is
unchanged. Face-only `lnx.skin_evenness.v1` remains unchanged. Neither old values
nor review permission are silently migrated, promoted or substituted. A missing
matching extension refuses rather than falling back to either older operation.

Natural pigmentation, blush, makeup, lighting and colour casts can affect the
reference. A median is a statistical target, not healthy-skin or illumination
truth; matching it can be undesirable. Human before/after review and diverse
real-photo acceptance remain necessary. Sample gates are conservative engineering
choices, not calibrated confidence or guaranteed skin identity.

## Two actual source grids and permissions

The Python preparation API is:

    prepare(body_rgb, body_coverage, face_rgb, face_coverage, amount,
            *, radius, cancelled=lambda: False)
        -> owned read-only contiguous float32 body-grid HWC2

Both RGB inputs are strict native float32 HWC3 opaque, unpremultiplied, encoded
working-sRGB-D65 SDR, finite[0,1]. Both coverage arrays are native float32 HW,
finite[0,1], matching their OWN RGB dimensions. Coverage is permission/evidence,
not alpha or calibrated probability. Reject HDR, nonfinite values, implicit dtype
or colour conversions, nonnative-endian floats, wrong shapes/channels and tensor
substitutes. There is no RGB8 conversion or quantized reference path.

The body and face arrays can have different dimensions. They must be true ROIs
of the same immutable effective source and authenticated person. They are not
two arbitrary photos, later portrait-stage pixels, per-output-tile samples or
a face image rescaled/repeated to body size. The authenticated effective source
stage can include the existing verified frozen repair base; both regions then
use that same repaired source, not a mixture of raw and repaired samples. Array
values cannot prove ownership: the host authenticates effective-source identity,
revision, retained FaceRef/BodyRef/person association, exact observations,
geometry and operation-specific reviewed support before calling the kernel.

Body coverage must contain only actual reviewed visible own-body skin, excluding
all retained face regions, other people, clothing, background, known occluders
and protected regions. Face reference coverage must be actual permitted own-face
skin with eyes, mouth/lips/teeth, hair, other faces, known occluders and protected
regions removed. A bounding rectangle or body region review alone cannot grant
face-reference permission. The host must bind both observations to the effective
source and invalidate stale reviews/references rather than reuse them.

The body window contains every admitted body region plus real `2*radius+1`
source halo, clipped only at the actual photograph boundary. Body guidance needs
2r and the additional pixel is conservative host policy. Disconnected permitted
regions still participate in one whole-body solve. The face window contains ALL
admitted same-face reference samples; it needs no guided-filter halo because it
is used only for robust reference selection. Window rectangles choose storage,
not permission. Zero-coverage samples do not influence any statistic.

Radius is strict Python int4..256, measured by the host on the actual body source
grid. Unsupported or degenerate anatomy/scale refuses rather than clamps or
invents a proxy. It is not persisted. Solve once against source, then crop and
compose the prepared HWC2 field for preview/export. A body-only output tile or
incomplete face-reference crop cannot replace the complete source preparation.

## Reliability, face reference and unchanged guided construction

Existing original Rust primitives in `core/skin_evenness/lib.rs` are reused. All
statistics use float64 on immutable source snapshots; stored displacement is
float32. The full original equations and primary conceptual references are in
the [skin-evenness contract](../skin-evenness/NUMERICAL-CONTRACT.md) and
[implementation review](../skin-evenness/IMPLEMENTATION.md).

For each source grid independently, decode sRGB to linear RGB; let
`I=.2126R+.7152G+.0722B`. With smoothstep `S(a,b,z)` over[0,1], use

    reliability = S(.01,.04,I) * (1-S(.70,.90,I))
                  * S(.002,.008,min(linear RGB))
                  * (1-S(.95,.995,max(encoded RGB)))
    w = coverage * reliability
    u = log(R/G), v = log(B/G), only for positive w

No artificial epsilon channels are inserted. Zero weight is absent evidence,
not a zero-valued observation. All four buffers are validated before any active
solve, including at amount zero.

1. Active BODY must have at least64 reliable samples with w>=.75. This is a
   sample-admission count only. The new path does NOT compute/select a body
   median to serve as the target. A shortage returns status7.
2. Active FACE must independently have at least64 samples with w>=.75. Use the
   existing exact componentwise median of their (u,v), with midpoint of central
   samples for even counts. This robust FACE value alone is target(tu,tv).
   Existing original cancellable deterministic median-of-medians selection
   uses groups of five and one reusable float64 buffer. No histogram, external
   target, donor face, brightness selection or learned estimate is involved.
   No face local-guided-context condition is imposed because face supplies only
   the reference. Face reliability failure also returns status7.
3. On BODY only, the unchanged first moments are `w,w²,wI,wI²,count(w>0)` in
   each real radius-r window. A supported center needs w>0, total mass>=4,
   actual positive count>=8, effective count `(sum w)²/sum(w²)>=8`, and
   mass/actual window area>=.15. Only admitted centers get mean/variance.
4. The unchanged body cross moments `wu,wv,wIu,wIv` derive two local linear
   regressions. Guidance regularizer is `.03²`. Coefficient centers retain
   `(w*aU,w*bU,w*aV,w*bV,w)`; unsupported centers are absent, not invented
   observations. A second radius-r box yields local body base chroma.
5. Final context requires a valid center coefficient, coefficient mass>=4 and
   mass/actual area>=.15. If no body center has valid final context, status8
   refuses the active transaction. Individual unsupported neighborhoods remain
   exact zero only when adequate context exists elsewhere.
6. Set `d=(tu-baseU,tv-baseV)`, n=norm(d). For n<=1e-6 use exact zero to suppress
   constant-chroma float32 decode/moment noise. Otherwise:

       shift = amount * body_w * .45 * .20 * tanh(n/.20) * d/n

   The two-component vector norm is <=.09, with only1e-7 float32 validation
   tolerance. The face luminance never becomes a body output target. The body
   source luminance is guidance, not replacement luminance or exposure gain.

The dependency-free project implementation is original GPL-3.0-or-later. Guided
local linear chroma and log-chroma translation are conceptual inspirations,
not claims to reproduce full published/learned algorithms. No external code,
model, asset, implementation download or proprietary license is incorporated.

## Application and unchanged legacy behavior

There is no new body-face application algorithm. Python `apply` is the exact
existing `skin_evenness_native.apply` function; native application remains
`lrt_skin_evenness_apply_v1`. The current pixel's linear RGB is multiplied by
`[exp(du),1,exp(dv)]` and jointly normalized to that CURRENT pixel's Y. One common
gamut-feasible interpolation between current and proposed RGB preserves Y
without per-channel clipping. Existing zero-shift/black/white bit identity and
independent Python absolute current-Y check<=2e-7 remain in force. Perceived
brightness need not be identical; later operations may change luminance.

The legacy `prepare_into` retains its exact dimensions, length/settings/pixel
validation, neutral handling and own-source reference selection. Only its
guided-solve body was extracted into `prepare_guided_into`. The extracted
arithmetic, loop order, allocation/drop order, context checks, cancellation
polls and final publication body are byte-identical to baseline. Existing
`corrected` and `apply_into` source text is also byte-identical. A new
`let n=width*height` reconstructs the already-admitted size in the private helper;
it does not change numeric arithmetic or poll order.

Static source comparison confirms these text properties only. The authored
UNRUN native fixtures include a test-only pre-refactor `prepare_into` oracle
copied from repository baseline, changing only its name/visibility. Its source
hash is recorded beside the fixture. Comparisons cover bitwise fields, result
statuses and cancellation poll counts across source tones, masked support,
amounts, reference refusal and interruption. Existing numerical fixtures are
retained. Neither fixture authoring nor common-helper comparison is a compiled
or executed claim of legacy parity.

## Optional ABI extension and failure publication

`lrt_skin_evenness_abi()` still returns1. Old prepare/apply declarations and
semantics remain unchanged. The optional new symbol is:

    lrt_body_face_match_prepare_v1(
        body_rgb, body_rgb_len, body_coverage, body_coverage_len, body_w, body_h,
        face_rgb, face_rgb_len, face_coverage, face_coverage_len, face_w, face_h,
        amount, radius, output, output_len, cancel, context)

See `core/skin_evenness/skin_evenness.h` for C types. Lengths count floats:
body3B/coverageB, face3F/coverageF, output2B. Check actual presence of the optional
symbol as well as existing ABI1 entrypoints before reporting availability. An
old installed ABI1 library can still perform old operations but is unavailable
for body-face matching. No rebuild/download happens at runtime.

Before constructing slices, checked dimension/resource/length admission and
aligned nonnull checked spans validate all four input buffers and output.
Output must overlap NONE of the inputs. Read-only inputs may overlap each other;
the host still must not pass face-as-body as an anatomical shortcut. Allocation
validity, immutable input lifetime, exclusively owned output and safe callback
lifetime remain the caller's responsibility. Callback must not unwind, reenter
or mutate buffers. Panic containment does not repair foreign faults or aborts.

Statuses:0 success;1 ABI/length/dimensions/alias;2 settings;3 pixel/numerical
refusal;4 cancellation;5 resources;6 contained panic;7 insufficient reliable
BODY support or FACE reference;8 no supported BODY guided context. The extension
does not reinterpret legacy statuses in old entrypoints.

All fallible active work uses private Rust storage, including face selection
and body solve. Every nonzero return leaves caller output unchanged. A final
poll precedes a single non-cancellable successful copy. Neutral preparation
validates all four inputs, polls, then fills exact positive zero without needing
reference/context. This is atomic error publication, not concurrency
synchronization, crash safety or interruption during the final copy.

Python separately snapshots four arrays as contiguous read-only owned buffers,
supports input strides, and requires caller immutability during snapshotting.
It validates finite bounded HWC2, neutral/unsupported zero output and late
cancellation before returning an owned read-only field. Callback exceptions
re-raise after the C boundary. Missing optional code refuses neutral calls too.
No caller pixels or face reference are mutated or retained by prepare.

## Aggregate resource and cancellation accounting

Each grid has dimensions1..65536; the SUM of body and face pixels must be<=32M.
Large separate ROIs cannot each claim a private32M allowance. Native checks use
checked multiplication/addition before slices/allocations and total<=4GiB.

Let B=body pixels and F=face pixels. Conservative native admission is:

    112*B + 24*F bytes

Body accounts for input RGB12+coverage4+output8+guided scratch88 B/pixel. Face
accounts for input RGB12+coverage4+reference selection scratch8 B/pixel. The
reference scratch is freed before body guided allocation; summing both peaks
deliberately overestimates their simultaneous allocation. No body-median scratch
is needed. Existing solver scratch peak and apply accounting are unchanged.

Python pure `memory_estimate(body_shape, face_shape)` returns ADDITIONAL bytes:

    112*B + 24*F + 8MiB

Body additional snapshots16+output8+native88=112; face snapshots16+selection8=24.
Existing caller arrays add16*B+16*F, so Python total admission is:

    128*B + 40*F + 8MiB <= 4GiB

The pure estimate does not allocate images, load native code or query live
memory. Actual preparation additionally checks the combined additional estimate
against the existing fail-closed CPU/cgroup availability estimate before any
snapshot. Host composition must independently admit frame/support/analysis,
both source ROIs, retained fields, renderer and GPU/intermediate memory. These
figures are allocation accounting, not measured process peak or OOM immunity.

All original bounded-loop cancellation remains: reference/body sample loops,
validation, filling, selection, horizontal/vertical passes and final publication
poll at bounded intervals (generally256 native samples). Python copies and
checks blocks up to4096 pixels and polls around loading/call/publication. Native
allocation, shared-library loading and final successful copy are not interruptible.
No latency, throughput or memory benchmark has been executed.

## Authored acceptance and remaining gates

Native UNRUN fixtures cover distinct face/body grids, face reference rather than
body-self median, face-luminance independence within reliable samples, robust
face outliers, body patch response, true equal-chroma/amount-zero neutrality,
actual current-Y preservation, protected-body/reference independence, separate
body/face sample shortage, body context refusal, every-buffer invalid-neutral
validation, early/late cancellation, unchanged output on refusal, new ABI spans,
null/alignment/alias/length failures, aggregate resource limits and legacy oracle
parity. Their source exists; none was compiled or run.

Python UNRUN fixtures cover scalar state, forbidden saved reference fields,
independent strided snapshots of both grids, strict arrays/controls/radii,
combined pure estimates, old-ABI-only capability refusal, missing-extension
neutral refusal, status distinctions, callback exceptions, corrupt fields,
unsupported/neutral output and late cancellation. Protocol doubles do not
exercise numerical mathematics, real shared-library loading or source identity.

Still required: Rust compilation/native tests, actual installed optional-symbol
loading, all legacy regression/parity tests, engine/UI/history/serialization and
review freshness checks, preview/export and CPU/GPU parity, unsupported-source
failures, measured memory/latency/cancellation, and diverse real photographs
including lighting/makeup/pigmentation/occlusion/multiple people/uneven body
regions. Valid references, halo behavior, face protection, exact person isolation
and perceptual benefit require acceptance. Source authoring alone cannot mark
the complete guide requirement, proprietary AI equivalence or release readiness
as finished.
