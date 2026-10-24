# Visible clavicle source-light enhancement: exact requirement and limits

Baseline `b32af87d662f7c7423d353dd6e6a33ccf867a031`.
Requirement **LNX-REF-PC-32465-C-abf0a5c8c9** remains **PARTIAL / UNRUN**.
This is not a renamed shoulder deformation, skin-gloss, generic sharpening or
manual dodge/burn tool. It does not close the official automatic AI 3D feature.

## Official semantics

The [official PixCake guide](https://www.pixcakeai.com/guide/32465), read on
2026-10-24 and displaying an update date of 2026-05-26, describes automatic 3D
clavicle point detection and stronger clavicle light/shadow, restricted to its
female and elder-female person categories. The baseline manual lines 508–510
agree. The mapping marks this P1; its dedicated acceptance_case_ids is empty.
Linked RENDER-001/PORTRAIT-002 cases are not proof of this feature's acceptance.
No official slider range or default was established; this implementation's
versioned 0..1 amount is an original bounded interface, not asserted equivalence.

The [MediaPipe pose guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)
provides shoulder landmarks 11/12, not clavicle curves or medial endpoints.
Shoulder interpolation is therefore not an anatomical measurement. No verified
clavicle model/code/weights contract is installed or introduced here. Manual
category selection is an explicit product applicability attestation, not an
inferred demographic classification or medical/anatomical diagnosis.

## Bounded independent operation

`lnx.collarbone.v1` retains only version and amount as portable intent. The
operation-specific `collarbone_visibility` support retains actual source,
BodyRef, own FaceRef/person association, pose observation, body-skin semantic
observation, manual add/erase coverage and a separate manual clavicle review.
Old body-skin review families cannot authorize this operation.

A user marks one or two visible image-left/image-right clavicle polylines and
transverse half-widths on the actual immutable source canvas. Half-width is
measured on either side of the centerline, not the whole band width. The source
review admits 4..256 pixels, segments at least two pixels, total length at least
twice the half-width and turns under 90 degrees. The actual render grid may
still be too small and refuse; no scaled width or trace is silently clamped. No default points,
shoulder-derived curves, hidden anatomy completion or generated bone template
is provided. The metadata includes explicit eligible category and visible
anatomy confirmation; it lives inside the content-addressed support review,
never in a transferable scalar preset.

The original Rust method measures broad signed source log-luminance contrast
across the reviewed local trace normal. Farther samples provide a local
reference, not a claimed physical illumination estimate. Near-source averaging
limits pore-scale amplification. A trace selects where and in which direction
to measure, not the sign of a manufactured highlight or shadow. Inadequate
coverage, border context, scale, source signal or budget refuses rather than
substituting a generated ridge or a proxy field. Source and all reference
samples must remain in the admitted person's body-skin/manual support.

The immutable field is prepared from the actual effective source/verified
repair stage and composed against the current ordered stage. Linear RGB common
gain and current headroom protect channel ratios without channelwise clipping.
Neutral and protected pixels remain unchanged. Active texture amplitude can
change; no claim of unchanged texture bytes, recovered reflectance, relighting,
3D measurement or naturally correct cosmetic appearance is made.

## Primary practice and licensing

- [darktable tone equalizer manual](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/tone-equalizer/)
  documents linear-RGB local exposure with a smoothed luminance guide to avoid
  flattening fine detail. Its [actual source](https://raw.githubusercontent.com/darktable-org/darktable/master/src/iop/toneequal.c)
  declares GPL-3.0-or-later. No code copied into this implementation.
- [Paris, Hasinoff and Kautz, Local Laplacian Filters](https://people.csail.mit.edu/sparis/publi/2011/siggraph/)
  supports separating edges and small-scale detail. Author implementation archive
  license was not verified; no archive downloaded, code copied or vendored.
- [He, Sun and Tang, Guided Image Filtering](https://people.csail.mit.edu/kaiming/eccv10/index.html)
  provides edge-aware local filtering principles, not clavicle detection or
  validation of this implementation's thresholds. No author code reused.
- [GIMP Dodge/Burn manual](https://docs.gimp.org/3.0/en/gimp-tool-dodge-burn.html)
  establishes local light/dark adjustment as a mature workflow, not proof of
  automatic anatomy or this numerical method's photo quality.

All new code is repository-original GPL-3.0-or-later. These references do not
validate our trace normals, widths, smoothing, contrast thresholds, eligibility
policy or aesthetics. PixCake documents desired behavior but grants no license
to its code, model weights, training data or example photography.

## Remaining acceptance and workflow gaps

The AI 3D detector and fully automatic workflow are absent. Manual traces may
be wrong; visible folds, tattoos, necklaces, coloured light, skin markings,
clothing boundaries and low signal can confuse source contrast. Manual and
semantic masks are not guaranteed instance segmentation or occlusion truth.

Actual private before/after review and canonical confirmation are required for
new support. Any scalar preset/people transfer uses each target's existing own
review, never source traces, masks, identity, category or measured source field.
The confirmed/one-time people-batch route now has authored target-by-target
actual before/after images, lazy frozen-image retrieval and exact per-target
acknowledgments. See [TRANSFER-VISUAL-CONTRACT.md](TRANSFER-VISUAL-CONTRACT.md)
for source/owner fences, shared-graph handling, bounds and remaining paths.
This is source-connected only, not runtime or photographic acceptance.
Persistent source-and-target collarbone cohort review is subsequently authored
in [COHORT-VISUAL-CONTRACT.md](COHORT-VISUAL-CONTRACT.md), including inherited
intent and unlink. Current-photo complete mixed-preset visual review is now
source-authored in [PRESET-VISUAL-CONTRACT.md](PRESET-VISUAL-CONTRACT.md), with
unchanged generic derived-preset refusal and explicit source/support limits.

All tests, builds, native execution, numerical precision, RGB16 preservation,
preview/export equivalence, history/project round trips, photographic quality,
noise/texture behavior, performance and memory acceptance remain UNRUN. Broader
alpha/HDR source-return limitations remain; no silent flattening or clipping.
