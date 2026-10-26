# Hand neutral-gray: source-bound local tonal correction

**PARTIAL / SOURCE AUTHORED / EXECUTION UNRUN.** This is a bounded implementation
slice for `control:PC-46608:1`, not acceptance of the whole hand-beautification
requirement. `ui/src/spec/refine.json` records hand-back/finger-joint smoothing;
PixCake's numerical algorithm, model and parameter ranges are undisclosed. The
original page https://www.pixcakeai.com/guide/46608 could not be fetched in this
pass; the retained exact requirement was read. Hand shaping remains separate.

## Method and evidence

Official GIMP Dodge/Burn documentation (read 2026-10-25):
https://docs.gimp.org/3.0/en/gimp-tool-dodge-burn.html describes localized tonal
lightening/darkening. Official darktable retouch documentation:
https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/retouch/
describes editing coarse detail while retaining finer texture. These support the
concept, not this implementation's photographic outcome. No implementation,
assets, weights, or third-party numerical constants were copied. This original
GPL-3.0-or-later Rust kernel reuses the local limb-vein ABI safety scaffolding;
it is neither a face smoother nor the vein colour-transfer algorithm.

From linear working-sRGB-D65 SDR source pixels, measure log Rec.709 luminance.
Compute source-support-normalized box moments at radius `r` and at
`max(1,floor(r/4))`, with `r` explicitly 2..128 **original source pixels**.
The difference of coarse and fine local means is a common RGB log gain, capped
at ±ln(1.08), faded by source support and a coarse log-luminance dispersion gate.
The method reduces a selected mid-frequency tonal band; it does not copy a clean
skin donor, flatten the entire hand toward a constant tone, or synthesize texture.
There is no clean-reference mask or extra donor-confirmation step.

The dependency region is the exact radius-r source box. Boxes crossing an image
edge, containing protected/black/clipped observations, or lacking >=95% hand
support are ineligible. Dispersion gate is full at sigma<=0.08 and smoothly zero
at sigma>=0.18. All constants are our conservative choices, not vendor values.
This may also reject genuine joint texture/high-contrast wrinkles; zero eligible
pixels refuses the preview with an explicit context error, never a success claim.

Amount 0..1 linearly scales the common gain. One shared headroom factor prevents
independent channel clipping. This preserves RGB ratios where nonzero, not a
claim of exact perceptual hue/texture preservation. Fine detail is not directly
blurred by application, but spatially varying gain can alter its appearance.
Exact zero field/amount, unpainted target and protection preserve source bits.
Masks must include sufficient context around the affected region. Hard protection
should cover nails, jewelry, tattoos and silhouette edges; the radius guard also
excludes their neighborhood. No automatic anatomical or edge identification is
claimed and unmarked structures can still be affected.

## State, source and review

Operation `lnx.hand_tone.v1`, family `hand_tone`, ABI/algorithm 1. Persisted
`_hand_tone` is `None` or `{version:1,source,input_sha256,repair_sha256,amount,
radius_px,review}`. `source` is `{sha256,width,height}`. Review is exactly
`{version:1,domain:'source-normalized',limb,target,protect,limb_kind:'hand',
same_limb_confirmed:true}`. Roles are existing manual local-mask v1 brush stacks.
Protect is an opaque unfeathered union. Every photo has its own source/masks;
there is no automatic anatomy/age/identity/hand detector or shared-person mask.

Existing repaired-source capture provides immutable full-resolution pixels,
input digest and repair digest. Original photographs are never overwritten.
Changing source/repairs invalidates the recipe. Reference action means acquiring
this canonical source (not painting a donor); preview produces exact-candidate
full-render before/after and source eligibility/protection overlay. Confirmation
binds image hashes, source/state fence and candidate recipe through the existing
request/revision owner. Clear is neutral and does not need this numerical ABI.

## Integration and limits

Current-photo UI → Tauri canonical ReceiptHost → hand_tone routes → ordinary
Engine DOC_FIELDS/history/project are connected in authored source. Unknown
writes use their existing request ID; they are not retried as new writes.
Capture/render/review all use the normal complete candidate owner. Normal preview
projects the source-grid field to the display grid only after measurement.
Confirmation and tiled export use full fields with exact source-origin slices.
The pipeline applies fabric sweat, limb vein, then hand tone before later portrait
and colour effects. RGB16 neutral passthrough and reduced edited captures refuse
to omit active hand tone. Source-bound recipes cannot be blindly batch/preset
copied. Existing original-focus and expression-donor paths remain unchanged.

Maximum source grid 32 MP. After canonical full-source capture and existing
source-grid mask rasterization, scan the real unprotected target in bounded
stripes. Measure only its bounding ROI expanded by the complete radius halo.
Pixels are cropped without resizing; every target reads the same finite source
neighborhood. Genuine source-edge windows still refuse. Native moments can have
small floating summation-order differences versus full-grid measurement, so no
bit-exact full-grid equivalence is claimed. The ROI field and eligibility are
scattered into zero-initialized full-source grids; preview/export retain their
existing exact source origins and no interpolation enters measurement.

Let N be original source pixels and R the halo ROI pixels. Native admission is
`160*R+8 MiB`. Host reserve is now `80*N+228*R+160 MiB`, with the same 4 GiB cap:
12N source + 9N masks + 13N full outputs + 18N immutable copies = 52N identified
full-grid residency; 80N includes additional mask/stripe/owner-view headroom.
228R reserves native160R plus Python conversions, ROI masks and outputs68R.
Before mask rasterization, the 80N+fixed reservation is checked; the full actual
ROI requirement is checked before numerical allocations. Upstream export uses a
conservative target-brush geometry + feather + kernel-halo envelope; subtraction,
hand intersection and protection can only shrink its real support.

For arithmetic illustration only, a 6000x4000 source with a 1000x1000 target and
radius16 has a 1032x1032 ROI and a 2,330,597,632-byte (~2.17 GiB) measurement
reservation. Thus localized work on ordinary unrepaired24MP is no longer
mathematically excluded by the cap; actual decoding, source size, other retained
effects, mask work and available-memory checks can still refuse. This is NOT a
24MP runtime/quality/performance acceptance result. Widely separated targets or
an almost full-image target can still exceed the cap. No proxy fallback is used.

A separate existing limitation remains: canonical repaired-source capture reserves
256N+64MiB for repair replay in addition to its full decoder budget. With this
family's 4GiB capture ceiling, a24MP source containing repair operations still
refuses before ROI measurement. This slice does not weaken that shared owner or
claim repaired24MP support. Full-source decoding is also not replaced by ROI JPEG
or RAW decoding.

Missing installed `liblrt_hand_tone.so` refuses positive operation: no runtime
compile, model download, or Python fallback. Packaging includes original
source/header/license. Build recipes are authored, not executed.

**UNRUN:** Rust build/ABI loading, Python/TS typechecks, all fixtures, UI interaction,
actual pixel output, history/reopen/export parity, image quality, 24 MP resource
usage and speed. Static Python AST parsing and whitespace checks are only source
checks. Real hand photographs at native zoom are necessary before any acceptance
claim, especially rings/nails, narrow fingers, dark skin, mixed lighting and
strong joint lines. This does not establish parity with the original product.
