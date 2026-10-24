# Reviewed body skin chromatic evenness

Baseline: `76b35c827c10a27b5cfe81a5a04adec6608da155`.
Requirement: **LNX-REF-PC-32465-C-d5ac2d4606**, `AI肤色统一（身体）`.
Status: **PARTIAL, source implementation only; all runtime/numerical/UI/photo acceptance UNRUN**.

## Exact distinction

The [official guide](https://www.pixcakeai.com/guide/32465), checked 2026-10-24, distinguishes body-region colour unevenness (d5ac2d4606) from the adjacent body/face matching item (d8b09012a9). This slice targets only the former with an original deterministic method and explicitly reviewed body ownership. It does not supply learned AI, automatic person-instance segmentation, body-to-face matching, brightest-person matching or eyedropper colour targeting. The adjacent IDs are not counted as implemented.

`lnx.body_skin_evenness.v1` stores only version 1 and amount [0,1]. Zero is neutral. It is separate from face evenness, skin temperature/tint, whitening/rosiness and legacy smoothing. Existing recipes are not reinterpreted or migrated.

## Actual source and permission

The family `body_skin_evenness` uses its own immutable descriptor `body_skin_evenness_visibility`, exact operation ID and manual review. Existing skin-colour or skin-finish consent does not authorize this operation. A confirmed same-person face/body association, immutable effective source, BodyRef, measured pose digest, actual body-skin semantic observation and manually reviewed visible/unoccluded body coverage are independently required.

All retained face boxes are excluded, including disabled/unresolved faces. Other owners' attached body coverage is protected across all three review families; overlap refuses rather than assigning pixels by face-list order. Manual brushes are source-normalized vector intent rasterized by the existing Rust mask worker at the current render extent. A proxy bitmap is not promoted to a full-resolution ownership mask. Semantic observations may be resampled from their documented producer grid; this does not claim new full-resolution model inference. Unknown occlusion and semantic/model mistakes remain review limitations.

Active intent without its own valid body support refuses. First-use review therefore supplies an explicit positive candidate amount together with its manual region. Both are staged privately on the exact local face, actual before/after and source coverage are shown, and confirmation atomically publishes that exact candidate through the existing people owner. No unsupported nonzero intermediate graph is committed. Old colour/finish review payloads remain unchanged. Detach requires this effective operation to be neutral first; it cannot silently erase shared/inherited intent. An invalid/stale active review can be reset before replacement.

## Reused original Rust, not a new model claim

The unchanged `core/skin_evenness` prepares a bounded two-channel log(R/G), log(B/G) field from the reviewed body's own reliable source samples. It does not use the person's face as a colour target. Source ROI includes all admitted body coverage and genuine guided-filter dependencies; radius derives from measured current-grid body evidence, not brush bounds invented as anatomy. The measured shoulder landmarks 11/12 and hip landmarks 23/24 must be visible/present at confidence at least 0.5 and inside the normalized frame. Radius is ceil(0.08 times the smaller shoulder span or shoulder-to-hip midpoint distance), constrained to 4..256 current-grid pixels. Cropped/occluded torsos can therefore refuse even when a limb is visible; no hidden anatomy is invented. Unsupported scale, inadequate samples or inadequate context refuse explicitly, without proxy fallback.

The dedicated `body_skin_evenness` stage reuses pointwise current-stage composition, before face evenness and existing skin colour. It preserves actual current-stage linear luminance using diagonal gains, common normalization and one gamut-feasible interpolation, not RGB clipping, old-source delta addition or texture blur. Later operations can still alter final luminance. Fields are retained readonly, memory-counted, cropped into actual tile coordinates and never re-solved per tile. Original PNG16 and genuine immutable derived-source inputs use their existing full-source contracts; opaque SDR remains the limit.

The [official MediaPipe pose guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) documents normalized image-coordinate landmarks. The [v0.10.21 primary pose enumeration](https://raw.githubusercontent.com/google-ai-edge/mediapipe/v0.10.21/mediapipe/python/solutions/pose.py) identifies shoulders 11/12 and hips 23/24 (Apache-2.0 source; no code copied). These indices substantiate the scale anchors, not a guarantee of hidden anatomy, physical 3D measurement or model accuracy. The 0.5 point-level confidence and radius policy here are original conservative admission choices, not official cosmetic calibration.

Primary technique and licence evidence are documented in [face-evenness implementation](../skin-evenness/IMPLEMENTATION.md) and [numerical contract](../skin-evenness/NUMERICAL-CONTRACT.md): He/Sun/Tang luminance-guided filtering and log-chroma diagonal gain coordinates. This slice reuses repository-original GPL code, not copied OpenCV/author code, proprietary models or new weights. Existing reviewed body semantics/manual raster retain their existing model/code provenance. No download or inference was performed.

## Persistence, export and transfer

Operation-specific leaf/project validation covers active and dormant undo/redo graphs. A strictly neutral body-evenness recipe whose only retained local asset is its own dormant body descriptor does not demand fresh face/body analysis just to reset; malformed leaves, unresolved inheritance, active effects and every other asset retain their normal evidence requirements. Export passthrough remains conservative and takes the checked path when a descriptor exists. Support records remain in the canonical content-addressed people support bank with exact source/body/person/observation revisions. Current consumers use the corresponding bank from the same original or derived document. No second command/history owner is introduced.

Preset/batch transfer carries only scalar intent. Every target must already own independently reviewed support for this family; no donor masks, BodyRefs, source reference samples or shifts travel. Target rendering and frozen coverage disclosure must agree before confirmation. Generic derived preset installation remains guarded; explicit reviewed mapping uses the existing target-owned canonical path. No source-association or stale-proof guard is removed.

Native actions and dedicated UI expose source review, candidate preview, correlated confirm/detach, scalar control and neutral reset. Pending/uncertain requests remain fenced and queried rather than blindly retried. The previous face-only requirement and legacy broad controls stay distinct.

## Remaining limits

This is manually assisted visible body skin, not automatic instance separation. A body's own statistical reference is not a recovered healthy-skin target, true illuminant or material reflectance. Natural pigmentation, makeup, coloured light, tattoos or semantic false positives can be mistaken for unwanted chromatic variation. There is no automatic meaning-based protection. Sparse or disjoint regions may lack guided context and refuse or leave unsupported cells unchanged.

No body/face matching, learned lesion removal, dedicated recovery brush, arbitrary alpha/HDR pipeline or complete official AI acceptance is claimed. No tests, product imports, build/compiler/typecheck, inference or photo/performance evaluation was run. Authored fixtures and static checks are not functional acceptance.
