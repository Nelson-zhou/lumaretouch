# Facial highlight / shadow structure, bounded source implementation

Status: AUTHORED / UNRUN. This is a new family, not a completion claim for the makeup family or parity with PixCake. No product execution, imports, compiler, build, test, model inference, download or installation was run for this work. Only source inspection and standard-library AST/JSON/hash checks are permitted in this development slice.

## Exact requirements and source verification

- LNX-REF-PC-32471-C-8f773e9125: 高光立体.
- LNX-REF-PC-32471-C-01b2ee2d32: 阴影立体.
- Both map to PC-32471, source https://www.pixcakeai.com/guide/32471, and are P1 in the canonical original mapping. Mapping evidence was read from original-mappings.tsv, lines 236–237, on 2026-10-24. The complete mapping file SHA-256 is 4d265066f86af5f8f1f490cd62f8940202d67be129e6b07de8530c6d96dfdfae. The in-repository historical handbook traceability independently identifies control:PC-32471:1 and :2 with these two labels.
- The official guide was read on 2026-10-24; its page states updated 2026-07-09. It describes face-highlight enhancement and shadow enhancement around the forehead center, nose bridge and tip, midface and chin. It does not publish an algorithm, an intensity range or numerical equivalence requirements. This implementation's [0,1] controls and conservative thresholds are original product policy.

## Mature method and license review, before authoring

1. Durand and Dorsey, *Fast Bilateral Filtering for the Display of High-Dynamic-Range Images*, SIGGRAPH 2002: https://people.csail.mit.edu/fredo/PUBLI/Siggraph2002/DurandBilateral.pdf. Primary research supports separating broad luminance structure from fine detail rather than flattening the entire image. This implementation does NOT copy the paper's code, reproduce its bilateral algorithm or claim HDR tone mapping.
2. OpenCV image-filtering API: https://docs.opencv.org/4.13.0/d4/d86/group__imgproc__filter.html. Primary implementation documentation provides the mature normalized box-filter building block. Here, independently written f64 integral sums compute support-normalized log-luminance box means on two measured scales.
3. OpenCV's repository license was read at https://github.com/opencv/opencv/blob/4.x/LICENSE and identifies Apache License 2.0. No OpenCV implementation, weights, images or assets are copied or bundled by this family. No dependency is added. Original new Rust/Python/TypeScript code is GPL-3.0-or-later under the existing repository license.

## What the operation actually computes

A frozen original/effective-source RGB window is measured once, before this operation. The source may be a canonical original photograph or a separately verified creative-derived photograph. It is never a previous facial_sculpt result, a transformed display thumbnail, another person's image or an old-source field.

1. Verify exact FaceRef, retained 478-point landmark digest, real MediaPipe evidence and named face_skin producer observation. A merged skin mask cannot substitute.
2. Intersect the measured face oval with independently painted and explicitly reviewed visible skin. Exclude eye, brow, lip and nostril/base neighborhoods, known occluders, face boundaries and ALL other retained face boxes, including disabled/unresolved faces.
3. Restrict the target to smoothly feathered zones at measured forehead-center, nose-bridge/tip, bilateral midface and chin locations. These are 2D editing domains, not recovered 3D shape or a guessed hairline.
4. Decode the frozen encoded-working-sRGB-D65 SDR samples to linear RGB and log luminance. Reject deep-black and clipped-source samples from the estimator. Compute reviewed-support-normalized means at radii r and 4r, with r = ceil(0.025 × measured face width). No replicated boundary samples or resized image is used. Unsupported neighborhoods receive zero field, not invented samples.
5. Take the difference between the two broad means. A smooth deadzone removes tiny residuals; a bounded response separates positive and negative structure. Highlight controls only the positive component; shadow controls only the negative component. The signed source field is bounded by 0.24 log units, multiplied by admitted target coverage.
6. Apply that source field to the ACTUAL current stage by one common linear-RGB gain. A common scalar gamut bound prevents channel clipping. The fine-detail image is never replaced with either low-pass image. At fixed gain, fine linear variations are multiplied rather than erased. This does not promise unchanged microcontrast at spatial gain boundaries or artifact-free photographs.

Flat source produces no intentional structure. Strong occlusions, colored markings, uneven lighting and poor semantic evidence can still confound a single image. Human review is an extra veto, not proof of perfect segmentation. No physical light decomposition, relighting, learned AI sculpting, 3D reconstruction, overexposure recovery, new facial structure or full cosmetic removal is claimed.

## Deliberate difference from neighboring families

- skin_gloss fits an existing bright/reduced-chroma neutral-light residual and adjusts apparent gloss. facial_sculpt measures a low-frequency spatial log-structure band, including an independently controlled negative response, and has no chroma/specular fit.
- skin_finish or smoothing changes texture/detail treatment. facial_sculpt does not replace source detail with a low-pass reconstruction.
- Geometry operations move samples. facial_sculpt preserves source coordinates, source dimensions and anatomical topology.
- Global exposure applies one broad multiplier without anatomical source contrast. facial_sculpt requires a nonzero measured local structure residual plus per-face review and support. It is not a renamed exposure control.

## Resource and ownership boundary

Native windows are at most 4,000,000 pixels, at most 8192 per dimension, and measured radius 2–128. Host source validation and geometry budgets are admitted before large image fields, and the native wrapper admits independent snapshots. Original source planes stay immutable. Native calculation stages its complete field privately; errors/cancellation do not publish partial output. The final successful copy is deliberately non-cancellable. Allocation estimates are conservative source policy, not a measured peak-memory or latency result.

The field is one immutable contiguous float32 HW array in a source-coordinate LocalEffect window. CPU and tensor composition use deterministic lexical FaceRef partitioning for overlap, with no repeated gain accumulation. Every export tile intersects and crops that same field at its exact (y,x) origin; it does not refit a small neighborhood. Unsupported HDR/nonfinite active composition is refused, alpha shape is refused and neither is clipped. Generic recovery is unsupported and rejected.

Only two scalar strengths are portable. Review strokes, source PNGs, FaceRefs, analysis evidence and the calculated field are not preset/batch payloads. Cross-photo person/group propagation, preset and batch publication are not enabled by this slice. require_transition rejects operation-local changes outside the exact current/effective row source. Current-photo changes that would affect unseen source-identical document owners also fail closed; this slice provides no alias-review authorization workflow.

## Acceptance gate

The interfaces and authored fixtures are source deliverables. Shared registry, protocol, original/derived preparation, CPU/device composition, source-owned support persistence, history, receipt replay and UI wiring must all be present before describing the family as integrated. Even then, runtime/native/photo/UI/export acceptance remains UNRUN until separately authorized and actually performed. See INTEGRATION.md and ACCEPTANCE_UNRUN.md.
