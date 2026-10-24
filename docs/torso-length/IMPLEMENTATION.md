# Reviewed upper-body length

Baseline: `ad5fae4b5f67fd9ea0abb4690e7125b8b7558049`.
Requirement: **LNX-REF-PC-32473-C-f1662d2dec**, 上身长度.
Status: **PARTIAL, AUTHORED / UNRUN**. This is source implementation, not numerical, UI, photographic or release acceptance.

## Requirement reconciliation

The exact desktop leaf is retained in `ui/src/spec/refine.json` and the original audit crosswalk. The [desktop guide](https://www.pixcakeai.com/guide/32473) timed out in two read-only retrievals on 2026-10-24; this is not evidence of unavailable product functionality. The [official mobile body-shaping guide](https://www.pixcakeai.com/guide/125979), lines138–146, separately describes upper-body length and waist length: left shortens, right lengthens. It corroborates direction, not desktop numerical coefficients, model equivalence or platform parity.

This operation is `lnx.torso_length.v1`, version1, signed amount[-1,1]. Its local UI range is not vendor calibration. Adjacent waist-length `LNX-REF-PC-32473-C-5d33f285bb` remains unimplemented here. Existing waist width, neck length and leg length remain separate unchanged operations. This is not global scaling or an interior warp that keeps both torso endpoints fixed.

## Source anatomy and method

The original Rust field uses actual visible shoulders11/12 and hips23/24 from the existing authenticated Body33 observation. Hips stay fixed; shoulder position changes along the image vertical axis. Complete reviewed head/hair and the associated face occupy a rigid translation plateau above the shoulders. Visible arms and garments below that plateau follow the same smooth torso field, not a promised rigid arm translation. Source-normalized manual boundaries explicitly admit the upper background and lateral transitions. No waist, hairline, clothing contour, hidden limb or 3D anatomy is invented.

A compact-support quintic field and certified inverse displacement provide a sufficient derivative bound, deterministic inversion/refusal and source-domain admission. Exact coefficients and bounds are original product policy, documented in [the numerical contract](NUMERICAL-CONTRACT.md). They are not a learned cosmetic model or physical body reconstruction. No source pixels are generated, copied from another person, or separately resampled through a second body pipeline.

The existing common body-to-face inverse map, final composed Jacobian checks and one source sampler remain authoritative. A new frozen operation-order version is used only when this operation is active; neutral state retains prior order identities and saved appearance. Full-source coordinates govern admission and displacement, with explicit decoder-scale conjugation for preview, not proxy-dependent strength. Exact render-grid endpoints map to exact source endpoints to avoid floating-point division moving an edge outside its domain; general outside or near-edge coordinates are not clipped.

## Ownership and review

Each support belongs to the exact immutable source, BodyRef, pose digest and operation. Confirmed same-person association plus the actual retained face reference, box and evidence binding are required. The complete associated face must fit the rigid plateau; another face or body meeting the support refuses. Human review cannot override low visibility, cropped/foreshortened or missing required anchors, insufficient headroom, source edges or excessive deformation.

The UI shows the real unretouched source preview and actual retained observations. Manual support review is not segmentation or a rendered result. The canonical body host is the sole edit/history/publication owner. Exact request receipts preserve uncertain outcomes as query-only, without blind replay. Supports are immutable and independent from other body effects; a scalar recipe does not grant ownership.

Original and derived sources use the existing verified source transport, source proof and full-resolution export reconstruction. There is no HDR clipping or new alpha promise. An unavailable native library refuses the effect rather than substituting another body control. Transport protocol1 remains available independently of the ABI-checked kernel flag, so exact neutral reset, disable and original-request status reconciliation are not blocked by a removed or unavailable kernel.

## Transfer and remaining limits

Operation-local portable recipe validation/history helpers do not constitute an end-user preset/batch workflow. Target support, pose and association must be recalculated and independently reviewed; no source support, FaceRef, BodyRef, mask or background boundary may be transferred. Until a real reviewed target flow is connected, UI preset/batch support remains unfinished rather than silently routed to generic portrait parameters.

This slice is deliberately limited to supported upright, visible, unambiguous 2D subjects with sufficient source clearance. Background lines, attached objects, crossed or occluded limbs, multiple people, perspective and inaccurate model observations may refuse or remain unsuitable. Manual review does not guarantee natural photographic output. Waist length, automatic body shaping, full AI equivalence and runtime/photo acceptance remain incomplete.

## Primary references and licenses

- [OpenCV inverse image mapping](https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html) explains destination-to-source sampling; no OpenCV implementation is copied into this kernel.
- [MediaPipe Pose Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker) describes estimated33-point pose, not measured skin/clothing outlines.
- [Official BlazePose GHUM model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf) records model limitations and Apache-2.0 licensing. Existing pinned model acquisition/provenance remains unchanged; no weights were downloaded or executed here, and model readiness is not newly claimed.
- Existing project kernels and new implementation are GPL-3.0-or-later. The local forward/inverse field and admission policy are original; no new third-party solver or copied proprietary algorithm is introduced.

All source fixtures are UNRUN. Static AST/JSON/hash/source inspections do not establish compiler, ABI, numerical parity, UI behavior, naturalness, preview/export consistency, performance or memory-peak acceptance. No product import, execution, tests, build, typecheck, inference, download or Git write was performed.
