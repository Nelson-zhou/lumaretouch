# Original source-measured face-skin gloss

Status: **AUTHORED / UNRUN**. Rust source, Python boundary/state, build hook,
ABI header and authored fixtures only. No product import, test, build, compiler,
typecheck, inference, image-quality comparison, benchmark, download, installation
or Git write was performed for this change. Static source review and Python AST
parsing do not establish numerical correctness, compilation, photographic quality,
speed or feature completion. Separately authorized execution and real-image review
are still required.

## Exact behavioral scope

Reference `LNX-REF-PC-32465-C-1eed7cf9a9` is the public
[PixCake skin guide, gloss subsection](https://www.pixcakeai.com/guide/32465),
read 2026-10-24, lines 165–167. It describes detecting existing facial-skin
highlights and suppressing/enhancing them with a signed slider. The guide does
not disclose an algorithm, coefficient, license to source code or numerical
equivalence. This implementation copies none of its assets, code or models.

The operation is `lnx.skin_gloss.v1`, with exactly:

    {"version": 1, "amount": 0.0}

Amount is a finite number in [-1,1], negative suppresses, positive enhances,
zero is neutral. No other keys, booleans, wrong versions or embedded source,
mask, radius or person identity are accepted. `None` produces fresh neutral intent.
`capability()` returns exactly `skin_gloss_available` and `skin_gloss_reason`.
Availability checks native loading, required symbols and ABI 1, not anatomy,
host support or photographic acceptance.

This is a conservative **appearance edit of source-measured existing highlights**,
not a global exposure/curve alias, blur, sharpening, texture synthesis, makeup
highlight placement, skin segmentation, physical albedo reconstruction or AI model.
Host skin coverage only grants permission. Highlight evidence is measured inside
the Rust core from the authenticated original source, not fabricated by a mask.

## Primary research and license decision

Primary sources inspected on 2026-10-24:

- [Shafer, Using color to separate reflection components, 1985,
  publisher abstract](https://onlinelibrary.wiley.com/doi/abs/10.1002/col.5080100409):
  a mature physical rationale for decomposing body-colour and interface-reflection
  directions. Used only as conceptual background, not a source implementation.
- [Klinker, Shafer and Kanade, Using a Color Reflection Model to Separate
  Highlights from Object Color, CMU, 1987](https://publications.ri.cmu.edu/using-a-color-reflection-model-to-separate-highlights-from-object-color):
  describes colour differences and linear mixtures. Its repository explicitly
  retains author/rightsholder copyright and restricts republication. No paper,
  image or source was copied into this repository; that notice is not a software
  redistribution license.
- [Tan's author publication list](https://tanrobby.github.io/pub.html) identifies
  Tan and Ikeuchi's mature single-image reflection-separation work, including
  the 2005 TPAMI article. No external implementation or dataset was downloaded,
  vendored, run or relabeled. No software reuse permission was inferred from
  public research access.

The code here is independently authored GPL-3.0-or-later, consistent with the
existing original local cores. It has no external crates or new dependency,
no copied third-party algorithm implementation, coefficients or model weights.
The chosen fit, confidence gates, support scale, signed strength and restraint
coefficients are original conservative product choices. They are not calibrated
skin thresholds, recovered commercial values or proof of visual equivalence.
This provenance decision is not a patent-clearance or legal conclusion.

## Exact colour and ownership boundary

    apply(current_rgb, coverage, amount, *, reference_rgb, radius,
          cancelled=lambda: False)

Current and reference RGB are exact native float32 H×W×3 **encoded working-sRGB,
D65, SDR [0,1]**, matching the existing colour/finish renderer. Coverage is exact
float32 H×W in [0,1]. Both Python and Rust reject nonfinite or out-of-range values,
including on neutral or unsupported pixels. There is no implicit colour-profile
conversion, HDR policy, alpha handling, premultiplication or tensor conversion.
Values cannot prove their colour-space label.

`reference_rgb` is mandatory and is the immutable **original effective source**
before these skin colour, finish and gloss edits. `current_rgb` is the colour then
finish intermediate to which gloss is applied. They share the exact photograph,
revision, transformed geometry, grid and dimensions. The estimator never reads
current RGB or amount. Colour/finish edits cannot change which original highlights
are evidenced, though current gamut feasibility can limit the resulting correction.
Re-render from these snapshots; never use a previous gloss result as reference.

The host authenticates source/revision, face/person, measured face geometry, grid,
transform and actual semantic facial-skin support/exclusions. Eyes, lips, teeth,
hair, clothing, background, other people, occlusions and protected regions must be
excluded. A bare face rectangle is not skin evidence. The core cannot authenticate
ownership or inspect anatomy. Coverage is not a calibrated probability.

All local statistics are weighted by this same source-owned face support, so
changing finite valid RGB outside support cannot affect that face's estimate.
Each face is estimated independently, not by mixing different people.

Radius is a strict Python integer 2..256 in the current render's pixels. It is
not a saved slider setting. The host uses measured FACE_OVAL width and height:
`ceil(0.025 * min(width,height))`, refusing an unavailable/degenerate measure or
an out-of-range result instead of clamping it or inventing global scale.

## Source-only local evidence

All calculations below are in f64 linear light after standard sRGB decoding,
with float32 intermediate horizontal sums and evidence planes. Let p be a source
pixel, m its arithmetic RGB mean, c=p-m the neutral-opponent vector, and
Y=0.2126R+0.7152G+0.0722B. These opponent vectors are linear RGB, not CIELAB.

Define S(a,b,v) as clamped smoothstep, t²(3−2t), for
t=clamp((v−a)/(b−a),0,1). This clamps evidence only, never RGB.

1. Source reliability is `S(.008,.035,Y) * (1-S(.96,.995,max(encoded RGB)))`.
   At/above encoded .995 in any channel, source evidence is exactly zero.
   Reliability also goes to zero in dark/noisy data.
2. Relative chroma is r=norm(c)/m. Reference-sample weight is
   `coverage * reliability * r²/(r²+.16)`. Achromatic samples are not references.
   Nine source-only statistics are summed over the square radius-r neighborhood:
   weight, weight², weighted RGB, weighted unit opponent vector and reliable
   support mass. There is no fixed skin-hue or ethnicity classification.
3. Require weight sum at least 4, effective sample size `(sum w)²/sum(w²)` at
   least 12, reliable support mass at least 35% of actual window area and a
   window at least three pixels in each dimension. These are conservative
   heuristic admission values, not statistical guarantees.
4. Let q be weighted local mean RGB, cq its opponent vector. Fit
   `p ≈ a*q + s*[1,1,1]`, using
   `a=dot(cp,cq)/dot(cq,cq)` and `s=mean(p)-a*mean(q)`.
   This measures an excess relative to the local mixed baseline, not a complete
   diffuse/specular decomposition. It assumes a neutral illuminant in the
   working space. The algorithm neither estimates nor silently changes it.
5. Evidence is the product of source reliability and smooth gates:
   - q relative chroma: S(.035,.12,rq).
   - coherent local opponent directions: S(.94,.985,norm(sum w*unit(c))/sum w).
   - positive brightness excess: S(.03,.20,(Yp−Yq)/Yq).
   - reduced relative chroma: S(.035,.18,(rq−rp)/rq).
   - positive neutral excess: S(.015,.12,s/Yp).
   - bounded body-colour scale: S(.55,.80,a) * (1-S(1.20,1.60,a)).
   - neutral-mixture fit residual:
     `1-S(.02,.08,norm(cp−a*cq)/max(norm(cp),.02*mean(p)))`.
   Nonpositive excess, achromatic baseline or invalid fit is zero evidence.
   Excess is bounded above by the minimum original linear RGB channel.
6. A second radius-r separable box sum smooths only `(excess*evidence,evidence)`,
   not RGB. Require summed evidence at least 3 and region confidence
   `S(.04,.16,sum(evidence)/actual window area)`. This rejects isolated bright
   pores/noise under the authored synthetic contract; it is not a general noise
   classifier. Smoothed excess is the evidence-weighted local mean, limited to
   the center's own measured excess. Center evidence exactly zero ALWAYS means
   exact copy, even beside a valid highlight. No new highlight locations appear.

Local neighborhoods use actual in-domain samples, never edge replication. The
two stages need a **real 2*radius halo**. Render the full authenticated grid, or
include that halo and crop after evaluation. Cropped neighborhoods without the
halo are a different estimate. Exact halo/full-domain parity is mathematical,
not promised bitwise: rolling float summation order may differ. Preview/export
must derive the radius from their own measured face-grid scale and keep reference,
current and coverage aligned, without silent resampling or a proxy fallback.

## Signed correction, gamut and texture limits

Requested neutral-light delta is:

    amount * 0.65 * center coverage * center evidence
        * regional confidence * smoothed existing excess

Decode current RGB and add that same scalar to all three channels. Coverage
blends the correction once at application; its earlier role in evidence weighting
can change confidence, so total behavior is not claimed linear in mask opacity.

For positive correction, cap the common scalar by the minimum channel headroom.
For suppression, additionally limit subtraction to both 20% of current linear
mean and 25% of its minimum channel. Use a small `1−1e−12` interior factor to
avoid boundary-roundoff, not a channel clamp. Thus, in exact arithmetic:

- All current channels remain in gamut with one common neutral-direction scalar.
- Suppression retains at least 80% of current mean and 75% of its darkest channel.
- Opponent RGB differences are unchanged by a fixed neutral scalar; relative
  opponent chroma can rise at most 1.25× under suppression.
- Neutral/zero-support pixels and pure-black/pure-white current endpoints are
  bitwise copies, bypassing decode/encode. Unsupported/clipped original source
  pixels and zero evidence also bypass the round trip.

Only modified pixels are re-encoded to float32 sRGB. Every result is checked
before publication. No RGB channel clipping occurs, even as numerical repair.
Near-equal values can quantize together; these mathematical bounds are not
bit-level proofs after float32 encoding. No perceptual hue constancy is claimed.

No RGB neighborhood is averaged into the output, and no texture is invented.
The current image's fine detail is retained under an additive, spatially varying
neutral-light field, rather than replaced by a blurred image. This does not
promise identical local-contrast amplitude or global tone ordering: spatially
varying evidence, coverage and gamut restraint can alter them. Real-image
review is required for skin texture, gradients, halo behavior and every skin tone.

## Honest refusal and ambiguity limits

Flat or wholly achromatic input, fully clipped highlights, insufficient sample
support, isolated weak/small evidence, dark unreliable data, inconsistent local
colour and strong non-neutral fit residuals return unchanged pixels, not an
exposure/curve fallback. No semantic specular mask is claimed to exist.

Single-image reflectance separation is ambiguous. A lighter, less-chromatic
albedo patch or suitably coloured illumination can satisfy this local model.
The gates cannot certify every coloured-light image as unsupported, prove that
each candidate is truly specular, or recover details lost to clipping. Highly
achromatic skin, makeup, mixed illumination, near-white highlights, extreme skin
shading, broad uniform gloss larger than the neighborhood, occlusions and weak
contrast can be missed or misclassified. The safe behavior for detectable poor
evidence is no change; uncertain photography requires review, not a stronger claim.

## Resources, cancellation and ABI

Dimensions 1..65536, at most 32 million pixels. Radius 2..256. Neighborhood work
uses bounded separable rolling sums, O(N) independent of radius, not a nested
radius-square scan. Peak native image scratch is 44 B/pixel: nine float32
horizontal statistics plus two float32 raw-evidence planes. The later two-plane
horizontal smoothing is smaller. No decoded full-image copy is allocated.

Native referenced inputs/output plus peak scratch are 84 B/pixel, capped at
3 GiB. Python accounts for caller arrays (28 B/px), independent read-only
snapshots (28), output (12), native scratch (44), plus 8 MiB allowance, capped
at 4 GiB. `memory_estimate((H,W))` returns additional `84*N + 8 MiB` and validates
dimensions/pixel/total limits without loading native or reading live memory.
`apply` separately admits that additional estimate against the existing
fail-closed cgroup/CPU helper. The host must also reserve its anatomy, buffers
and other stages; this local estimate is not an OOM guarantee or process budget.

Inputs can be strided but are independently snapshotted into contiguous arrays;
the caller must not mutate during snapshotting. Native allocations use
`try_reserve_exact`. Initialization, validation, copies and filter/fit loops poll
cancellation at least every 256 pixels and at row/column transitions, with
initial radius sums bounded by 257 entries. Python copies/validates at most
4096 pixels per block. System allocation latency itself is not bounded.

`lrt_skin_gloss_abi()` returns 1; `skin_gloss.h` defines the ABI. Lengths count
float32 elements, not bytes. Statuses: 0 success, 1 invalid ABI/dimensions/lengths/
alignment/output alias, 2 invalid amount/radius, 3 invalid pixels or numerical
refusal, 4 cancellation, 5 resource rejection, 6 caught Rust panic.

Native validates checked lengths/address ranges and output disjointness before
forming slices. Read-only inputs may overlap. Range checks cannot prove allocation
ownership/lifetime or make invalid pointers safe. Callback/context must stay live,
must not unwind/reenter/mutate buffers, and native callers discard ALL output
after nonzero status. Python catches callback exceptions and re-raises outside
FFI, never returning private partial output. `catch_unwind` needs unwind-enabled
builds and does not contain invalid pointers, process aborts or foreign faults.

The library must be installed with the exact symbols and ABI, even for neutral
`apply`. There is no fallback, runtime compile, install or download.
`packaging/build-skin-gloss.sh` is authored only and has not been executed.

## Authored verification, all UNRUN

`tests.rs` covers signed selectivity, neutral/signed-zero/zero-support bit copies,
flat chromatic and achromatic refusal, same-chromaticity diffuse shading, a broad
neutral additive lobe, isolated pore and inconsistent coloured patch, clipping,
out-of-support independence, current/amount-independent source evidence, current
black/white endpoints with a distinct highlight reference, suppression/chroma
restraint, genuine halo tolerance, strict settings/SDR, cancellation/resources,
and safe/FFI parity plus alias/null/length rejection.

`engine/tests/test_skin_gloss_native_unrun.py` covers strict recipe/input/shape contracts,
mandatory original reference, owned strided snapshots, pure memory estimation,
resource/cancellation ordering, callback errors, and unavailable native behavior.
Its protocol fake tests only boundary paths; it is never a production algorithm.

These are written acceptance intentions, not passed tests. Compiler checks,
numerical execution, sanitizers/FFI fault review, threading/cancellation timing,
large-photo resource/performance, real skin-tone/lighting/clipping cases,
preview/export agreement and photographic before/after quality remain UNRUN.
