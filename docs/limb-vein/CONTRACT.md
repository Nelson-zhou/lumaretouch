> Integration update: current-photo shared source wiring is now authored; see INTEGRATION.md. The isolated-slice description below records the component contract. All execution and acceptance remain UNRUN.

# Manual reference-assisted hand / forearm / foot vein softening

Status: **AUTHORED / UNRUN, isolated module only**. No shared registration or
runtime activation is included in this slice. No tests, builds, type checks,
product imports, inference, image acceptance or performance tests were executed.
This is cosmetic photograph editing, not vascular diagnosis or health analysis.

## Requirement and evidence

Original collected specification `ui/src/spec/refine.json` identifies
`control:PC-46608:2` (hand/arm vein softening) and
`control:PC-9XYcMCvHXW:1` / `:2` (foot veins and manual painting).
Foot behavior describes colour reduction followed by appearance of relief
softening, with texture preservation and avoidance of excessive correction.
The exact product numerical ranges and model are not disclosed. Our [0,1]
control and radius 2..128 source pixels are local choices, not PixCake parameters.
Hand shaping and hand neutral-grey controls remain separate missing requirements.

Official mature reference read on 2026-10-25:
https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/retouch/
Its retouch manual describes frequency-separated skin edits; it supports the
concept of modifying coarser colour/shading separately from fine detail. It is
not evidence that this implementation removes veins or matches that product.
No darktable code, models, assets or numerical constants were copied.

## Reused architecture and licensing

GPL-3.0-or-later local `fabric_sweat` source patterns supply the bounded C ABI,
manual-mask raster admission, capture/render ports and review lifecycle. This is
explicit local source reuse, not a claim that renamed garment logic implements
hand anatomy. The **numerical behavior differs**: substantially tighter gain
caps, zero-mean log chroma, and progressive chroma-first / tone-second control.
Local mask recipes remain authoritative; canonical document/history/receipts and
export remain shared owners. There is no second project or receipt bank.

## Canonical contract

Family `limb_vein`, operation `lnx.limb_vein.v1`, ABI/algorithm version 1.
Persisted state slot `_limb_vein` is `None` or exactly
`{version:1,source,input_sha256,repair_sha256,amount,radius_px,review}`.
`source` is `{sha256,width,height}`; source / repaired-input identities must match
at preparation and publication. Capture pixels are immutable full-resolution
encoded working-sRGB-D65 SDR float32; Rust measurement receives decoded linear
RGB. A fitted display image must never become measurement input.

Review is `{version:1,domain:'source-normalized',limb,target,reference,protect,
limb_kind,same_limb_confirmed:true,clean_reference_confirmed:true}`.
`limb_kind` is `hand`, `forearm` or `foot`, explicitly selected, not classified.
Each role is an existing local-mask v1 stack of manual add/subtract brush objects.
Protect is a hard union of enabled opaque add strokes, zero feather.
All masks use the unrotated source grid. Limb support confines target and clean
reference; protect excludes both target AND donor observations. Target/reference
overlap refuses. Users must exclude nails, tattoos, jewelry, edges and other limbs.
This is not automatic skin, anatomy, vein or same-person identification.

Action payloads inside existing document/revision/request envelopes:
- `reference {}` -> family/protocol, reference_id, fence, source, source_image,
  current_amount, capability.
- `preview {reference_id,amount,radius_px,review}` -> preview_id, fence,
  before/after complete-render images, source-grid eligibility mask, facts,
  candidate_sha256.
- `confirm {preview_id,reviewed:true,before_sha256,after_sha256,mask_sha256,
  candidate_sha256}` -> internal ConfirmedEdit only, NOT independent publication.
- `clear {}` -> neutral intent without needing installed numerical capability.

Images are bounded PNGs with byte hashes. Source-grid mask and cropped final
comparison images are intentionally not required to have equal dimensions.
Edits invalidate review; UI draft changes cannot silently reuse confirmation.

## Algorithm, limits and honest interpretation

One same-limb clean reference estimates log-channel means from explicitly painted
pixels. It requires mass >=16 pixels and bounded per-channel log spread <=0.35;
dark/clipped reference samples refuse. A support-normalized box low-frequency
field is measured on real full-source pixels, radius 2..128. Protected pixels
supply no observations. Targets with <75% real local support are not corrected.
Reference and target lighting still require human judgment; no numeric threshold
proves correct tissue ownership or comparable illumination.

The mean log-channel correction is capped at ±ln(1.12). Channel deviations are
clamped to ±ln(1.10), then their mean is removed. At amount <=0.5 only zero-mean
log chroma is scaled by 2*amount; above 0.5 full chroma remains and common tone
scales by 2*amount-1. Geometric RGB mean is not perceptual luminance. This may
soften photographed vein colour and shading; it does not alter geometry, infer
vessels, or prove preserved anatomical structure. Fine detail is not blurred by
application, but a spatially varying gain is not a guarantee of untouched texture.
One common headroom factor avoids per-channel clipping. Zero amount / zero field
retain source bits; output outside target/protection is unchanged.

Full-grid maximum is 32 MP. Native measurement reserves 128*N+8 MiB; host source,
masks and snapshots reserve conservatively 196*N+160 MiB, capped at 4 GiB. This
is admission accounting, not whole-process peak memory or 24 MP availability.
Runtime compilation/download/fallback are absent. Missing installed library
refuses positive correction. Neutral clear remains possible.

## Shared integration instructions (not implemented here)

1. Register canonical `_limb_vein` with `limb_vein_state.check`, history snapshots,
   source validation, save/reopen and neutral default. Reject unsupported transfer.
2. Construct `limb_vein_host.Review(Ports(capture,render,budget))` using existing
   repaired original capture and complete candidate rendering. Render fields once
   with `limb_vein_measure.prepare`; apply or source-slice frozen fields in every
   normal preview, candidate, derived and tiled export route at the same stage.
3. Route `cmd:'limb_vein'` reference/preview/confirm/clear through the current
   native request/receipt owner. Publication calls `assert_publishable` under the
   existing lock; invalidate after successful commit. Unknown outcomes query the
   original request ID, never resubmit. Wire the supplied UI transport ports.
4. Build `core/limb_vein/build_limb_vein.sh` only in the authorized external build
   path, stage `liblrt_limb_vein.so` into engine bin with corresponding sources,
   header and GPL notice. No build was run in this slice.
5. Update traceability with implementation references but retain partial/UNRUN.
   Batch, presets, linked aliases, automatic masks and real-photo quality remain
   separate work, not silently closed by this current-photo module.
