# PC-32452 semantic colour transfer: implementation evidence

Current status: single-photo and dedicated global batch/preset source integration
are wired through UI,
native transport, engine, history, project, preview, export and packaging. Python/TypeScript AST inspection only. No model inference, Rust build,
product import, tests, typecheck, performance measurement or image-quality
acceptance was run. Qoder owns eventual local execution. This document is not a
claim that the commercial feature or all of PC-32452 is complete.

## What the implementation actually does

A user-owned sample comes from the existing sample library. Its exact retained
RGB-float reference is opened, and the current target is fully rendered through
manual edits, the common people warp, scene edits, manual liquify, optics, crop
and PC-32455. Only the earlier contribution of this new AI group is removed.
Neither image is reopened through an original-source semantic resolver.

The genuine fixed Apache-2.0 Google six-class model analyzes bounded RGB8 views of
both immutable rendered canvases. Optimization samples are spatially stratified
actual float pixel locations, not RGB8 analysis pixels or marginal histograms.
Rust uses semantic-conditioned joint OKLab prototypes, luminance strata,
stabilized entropic transport and bounded constrained fitting. See the native
README for exact budgets, training/held-out splits and diagnostic semantics.
No trained colour-transfer checkpoint is claimed. Extreme and harmonious are two
regularization policies of one backend, not two invented neural models.

The result is one AI-owned full-image group plus editable semantic residual groups.
Local residuals evaluate the same global base in parallel, with conserved overlap;
they are not sequentially stacked recolourings. Both fitter and production use the
same Rust point evaluator including float32 endpoint rounding. The first runtime
path has an explicit CPU bridge for Torch inputs. Its latency is **unmeasured**.

The 50 real values are: exposure EV; RGB log2 gains; encoded-luma saturation;
contrast; master/R/G/B five-knot PCHIP ordinates; and the existing 24-value HSV8
band contract. Automatic fitting is a declared subset. Neutral fields remain
editable. Existing manual fields and all legacy recipes are untouched. Extended
sRGB gain/PCHIP math is retained; nonzero legacy HSV8 remains explicitly SDR and
clamps to [0,1]. It is not renamed HDR HSL and has no orange/skin gate.

Global overall/tone/colour strengths are independently 0–200. Quick and precise
views edit the same recipe. Reset clears only this contribution. Group reset
restores that group's fitted baseline. Deletion removes a local group and its mask.

## Coordinate and source ownership

Public masks use `rendered-canvas-normalized-semantic-colour-v1`, never the
existing `source-normalized` domain. They retain source SHA/dimensions, complete
render SHA, candidate state identity, geometry SHA, document/revision, dimensions
and stage. People geometry uses `people_geometry_identity.record` on the
canonical all-face snapshot, excluding the editor cursor and nongeometry edits.

Analysis-grid float32 probabilities are persisted with strict bounded decompression
and SHA-256. Render tiles reconstruct these fields using explicit global half-pixel
coordinates. Manual brush/linear/radial objects are explicitly lowered to the
coordinate-independent LMR2 primitive rasterizer; source semantic, range and
prompted bindings are forbidden in that adapter. Rendered masks are never run
through the source/people warp a second time. Geometry/source changes preserve the
recipe and visibly suspend it until reanalysis and review. Ordinary colour slider
moves do not trigger costly inference or change geometry identity.

Local mode requires separate useful reference and target masks with independent
binding identities. Fitting selects the same actual model categories inside each
selection. The reference mask is never copied to target coordinates. Local mode
is rejected for batch/preset portability.

## Memory and lifecycle

Final output is full-resolution float before RGB8/RGB16 quantization. The existing
32 MP reference limit remains explicit. Two full-float images plus renderer
buffers are admitted before target decode. Frozen images are privately owned;
new temporary rendering output is adopted rather than redundantly copied.
The worker receives only bounded inference views and full-precision spatial
samples. It is offline, process-owned, cancellable, and bounded to 240 seconds.
Only a complete checked result can be published.

Production applies colour in 512² tiles and retains masks on the analysis grid.
It does not materialize six 32 MP float masks. Point operations generate no texture
and resample no image coordinates. Exact neutral and zero-mask paths preserve
unchanged pixels. A geometry suspension is explicit, never a silent stale mask.

Capture, start, poll, review and apply are separate. Stale document/revision/source
or reference-resource changes reject application. Request generations and named
sessions fence late UI replies and cancellation. Applied parameters and masks
replay without running or requiring the segmentation model. Missing reference
assets do not cause a fake alternative fit. Reanalysis can hydrate the existing
lossless bundled sample. A failed apply restores only this module's prior state.

## Honest current exclusions / incomplete work

- Shared server, preview/export, project, native transport and panel integration
  are source-wired, but have not been executed or accepted in a running product.
- Six classes are background, hair, body skin, face skin, clothes and others.
  Others is not background. There is no sky, lips or individual-person segmentation
  in this model. Existing OneFormer and measured lip/people capabilities are not
  falsely advertised as connected here.
- Generic SAM rendered-canvas selection is not connected; manual independent brush
  selection is implemented. Existing source-domain SAM masks cannot be reused as
  if they described an edited/cropped render.
- Global batch/preset target recomputation, explicit manual offsets/class intent,
  owned-field undo and portable full-reference archives are source-integrated.
  See ../semantic_colour_batch/INTEGRATION.md. Local/user-mask intent is refused;
  runtime, photographic and portability acceptance remain UNRUN.
- The local library, commercial official/cloud samples, colour-style family,
  AI追色2.0 and scene synthesis are separate tasks, not covered by these modules.

## Licensing and mathematical references

The model's actual admitted bytes have SHA-256
`c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`.
The adapter supplies those exact bytes to MediaPipe, not a second path reopen.
Existing `docs/model-licenses/models.json` and `NOTICE` provide retained attribution.

- Product requirement: https://www.pixcakeai.com/guide/32452
- Google model card, explicit Apache-2.0:
  https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Multiclass%20Segmentation.pdf
- PythonOT MIT mathematical reference (no weights or sample photos imported):
  https://pythonot.github.io/auto_examples/domain-adaptation/plot_otda_color_images.html
  and https://pythonot.github.io/gen_modules/ot.bregman.html
- PythonOT license: https://raw.githubusercontent.com/PythonOT/POT/master/LICENSE
- darktable GPL-3.0 nonsemantic baseline, not copied as semantic completion:
  https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/color-mapping/
- Existing optional SAM2 Apache-2.0 checkpoint grant:
  https://github.com/facebookresearch/sam2#license
- Existing optional OneFormer MIT model-card source:
  https://huggingface.co/shi-labs/oneformer_ade20k_swin_tiny

FastPhotoStyle/PhotoWCT CC-BY-NC-SA is excluded. WCT2 checkpoint redistribution was
not independently cleared and is excluded. PhotoWCT2 lacks established licensing
for this use and is excluded. No stock/sample photos were copied. Model license
is not a photo-redistribution license and not a quality-acceptance result.

## Masked endpoint and review bounds

Local residuals call the same Rust masked float32 endpoint directly, then sum
parallel residuals in bounded float64 tiles and round once. A single local group
therefore retains the native endpoint, including mask-zero/neutral bits. The
mask-aware support raster and final stage use one TileMask interpolation
contract. Frozen review hashing admits at most 24 MiB, matching the worker result
budget rather than inheriting the unrelated 2 MiB batch metadata limit.


## Small receipts and project mask assets

The 24 MiB bound is private worker/proof data only. UI requests remain capped at
2 MiB and public responses respect the existing 8 MiB ReceiptHost. State and
review responses omit all inline mask blobs. Commit sends only proof/session;
slider edits send parameters; mask edits send only ordered marks. One selected
mask overlay is generated lazily at a maximum 512px long edge.

At commit, bounded mask planes become immutable SHA-addressed cache assets.
Applied recipes carry dimensions/encoding/SHA only. The private owned
`_semantic_colour_mask_assets` map holds readonly uint8 arrays of float32 bytes,
which the existing project encoder deduplicates by content across history and
versions. Project validation rejects missing/mismatched assets; hydration restores
these exact bytes without ML. Mask edits do not resend or duplicate base planes.
The small retained initial-review receipt persists diagnostics, model/input
identities, reference binding and commit proof. Later manual edits retain that
receipt as the initial estimate, not as a newly computed quality measurement.


## Applied versus proposed lifecycle

A proposed fit is tied to the full frozen document revision/render proof. Once
applied, upstream exposure, WB, curves, HSV, ordinary background colour and sky
colour controls remain editable without new inference. Only source/canvas
geometry or material ownership suspends retained rendered masks: common people
warp, manual warp, optics/crop, repair content, matte ownership, sky asset or
placement/support and active studio object-removal support. Diagnostics are
labelled initial-fit only. No ordinary colour drag automatically launches a fit.

## Integrated host evidence

See INTEGRATION.md for the actual command path and small-receipt ownership. The
shared snapshot extraction keeps active and stored-document exports on one mapping.
The current project container is v14; semantic assets introduced in v12 and
earlier sky semantics remain supported and are not reinterpreted. Required next
evidence is Qoder runtime execution, not another source-only claim. Dedicated
batch/preset registration performs target recomputation and refuses generic copying.
