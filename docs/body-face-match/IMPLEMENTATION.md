# Reviewed body-to-own-face chromatic matching

Baseline: `e30f53da51dbfa9b3c5c11598ee210eeb79fb387`.
Requirement: **LNX-REF-PC-32465-C-d8b09012a9**, `肤色统一（身体）`.
Status: **PARTIAL; source implementation only, all numerical/runtime/UI/photo acceptance UNRUN**.

## Exact semantics and limits

The [official skin guide](https://www.pixcakeai.com/guide/32465), checked 2026-10-24, describes reducing body/face colour differences and uneven body colour. This differs from body-only evenness d5ac2d4606. The new `lnx.body_face_match.v1` stores only version 1 and amount [0,1]. It uses the same person's measured source-stage facial skin as a chromatic reference for separately reviewed body skin. No another-person reference, donor pixels, facial texture transplant or brightest-person matching is used.

The method is original deterministic guided log-chroma correction, not learned AI or proprietary equivalence. It preserves current-stage linear luminance, so it deliberately does not match body brightness to the face. Its bounded strength reduces differences rather than guaranteeing equality. Other active skin/colour/geometry operations can alter the final relationship; it does not promise matching to the final edited face.

## Source and independent ownership

- The family `body_face_match` and descriptor `body_face_match_visibility` are separate from colour, finish and body-evenness consent. Existing review records cannot authorize this operation.
- BodyRef, confirmed same-person face/body links, source dimensions, pose digest, association revisions, actual body-skin semantic observation and explicit manual visibility/ownership review remain required. All retained faces are excluded from the body target; competing other-owner body coverage is protected across all four families.
- The reference uses the selected own FaceRef, exact normalized 478-landmark digest and actual face_skin observation. Eyes, brows, lips, known occluders and foreign face regions are excluded. Reference adequacy comes from real reliable samples, not a fabricated face palette or enlarged ROI. The immutable support record additionally pins the face_skin observation.
- Body and face ROIs come from the same authenticated effective source stage, including a verified frozen repair base when present. No later portrait output feeds its own reference. The source-stage display must show that same source/repair plane rather than falsely labelling raw or later corrected pixels as the sampled reference.
- The body region remains source-normalized manual vectors intersected with actual semantic body skin. No proxy bitmap is promoted as full-resolution ownership, and resampled semantic evidence is not new full-resolution inference.

## Kernel and rendering

An optional `lrt_body_face_match_prepare_v1` symbol extends the existing original Rust library. Legacy ABI1 prepare/apply signatures and capability remain valid; the new capability specifically requires the new symbol. No Python effect fallback, runtime compilation or model download is introduced.

The original guided solve is extracted without arithmetic or loop-order changes. Legacy preparation still chooses its own reference. New preparation requires adequate body observations but chooses its robust target only from the separate face ROI. Both native grids are independently dimensioned and checked; input sizes, combined memory/pixel admission, cancellation, alias protection and atomic output publication remain explicit. Neither face pixels nor its spatial texture are copied into the body.

Only the body field is retained as readonly HWC2 log(R/G), log(B/G) displacement. Its local radius derives from actual visible/present shoulders and hips on the current body grid. Body support plus the genuine two-pass halo is solved once; the separate face reference has no unnecessary guided-face radius requirement. Invalid/cropped body scale, inadequate reference or missing local context refuses without a proxy fallback.

Stage order is body-to-own-face match, body-only evenness, face-only evenness, then existing skin colour and later portrait operations. Each has independent scalar intent and consent. Applying multiple colour operations is an explicit composition, not a guarantee that the last image equals one chosen reference. All fields enter the existing single common geometry path; tiles crop frozen fields and do not recompute references.

Pointwise application reuses the unchanged current-luminance-preserving operator: linear diagonal gains, normalization to actual current Y and one feasible gamut interpolation. No per-channel clipping or stale RGB delta addition. Original RGB16 and immutable derived float-source paths retain their existing ownership and precision contracts; this slice supports opaque SDR, not broader alpha/HDR.

## Review, persistence and transfer

First use privately stages an explicit positive amount together with an independently reviewed body region. Source-stage face-reference and body coverage displays accompany actual full-candidate before/after rendering. Correlated confirmation commits the exact face-scoped amount and support through the existing history owner. The private fence additionally hashes the sampled source-stage pixel bytes, dimensions and stage, so a changed repair plane cannot silently confirm a stale comparison. Reference images disclose their actual proxy review grid; full-source candidate/export reference is recomputed independently. No unsupported nonzero intermediate state is committed. Detach requires effective neutral amount first.

Only exact dormant body-evenness/body-face-match descriptor kinds with strictly neutral recipes can bypass fresh analysis for reset. Active, malformed, conflicted, wrong-kind or other owned intent keeps existing evidence guards. Project/descriptor ownership checks and conservative export fast-path checks remain unchanged.

Presets and batch transfers carry only scalar amount. Each target independently revalidates its BodyRef/person review and own-face observation, then rebuilds the field from its actual effective source. Frozen coverage receipts identify the target's review and own-face reference, not samples, masks or borrowed analysis. Commit re-renders/rechecks before publication. Generic derived preset installation stays guarded; explicit reviewed per-target mapping uses the existing owner.

## Primary method, provenance and acceptance

Technique sources are documented in [the original face-evenness implementation](../skin-evenness/IMPLEMENTATION.md): [He/Sun/Tang guided filtering](https://people.csail.mit.edu/kaiming/publications/pami12guidedfilter.pdf) and [log-chroma diagonal-gain coordinates](https://arxiv.org/html/1507.00410). The new reference policy and masked retouch method are original; neither the learned colour-constancy estimator nor copied reference implementation is used. Existing code is GPL-3.0-or-later. Existing segmentation/pose models keep their previously recorded provenance; no new weights are claimed.

The [MediaPipe primary pose enumeration](https://raw.githubusercontent.com/google-ai-edge/mediapipe/v0.10.21/mediapipe/python/solutions/pose.py) identifies shoulders 11/12 and hips 23/24. The conservative radius/confidence policy is this product's admission policy, not a physical 3D measurement or official cosmetic calibration.

Makeup, coloured lighting, natural pigmentation, tattoos and unknown occlusion remain ambiguous. The own-face median is a statistical target, not recovered healthy skin or true illumination. Manual ownership does not become automatic instance segmentation. Dark, clipped, small, noisy or occluded references can refuse. Body-to-face brightness matching, final edited-face equivalence, dedicated recovery painting and complete official AI behavior remain unfinished.

All fixtures are AUTHORED / UNRUN. Static AST/JSON/hash/source checks and source-identical extracted arithmetic do not establish numerical, compiler, native loading, UI, photographic, export parity, performance or memory-peak acceptance. No product import, execution, test collection, build, typecheck or inference was performed.
