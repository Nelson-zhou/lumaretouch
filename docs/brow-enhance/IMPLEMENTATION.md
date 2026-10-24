# Original-brow enhancement: source-connected, acceptance UNRUN

## Exact requirement and boundaries

- `LNX-REF-PC-32471-C-18765fa8ea`, PC-32471 `眉毛增强`, traceability `control:PC-32471:3`.
- Official [desktop makeup guide](https://www.pixcakeai.com/guide/32471): left reduces the original brow effect, right strengthens it; unlocking enables separate sides. The guide does not specify a numerical range or an algorithm.
- New `lnx.brow_enhance.v1` implements bounded observed original-brow contrast, not the existing seven geometric brow controls or fourteen added brow patterns. Its `[-1,1]` bounds and gain are original conservative policy, not proprietary-equivalence claims.
- Broad facial symmetry includes ears and other anatomy; this feature does not close that different family. No new completed requirement is invented for an internal adapter.

## Technique and provenance

Original GPL-3.0-or-later Rust computes a local weighted linear-light forehead reference from independently admitted source pixels, and modulates the observed dark log-luminance residual with one common linear RGB gain. Negative strength reduces but does not remove that residual. Positive strength cannot create hair where no observed residual exists. Exact black and protected pixels are preserved. Every requested native pixel requires sufficient real local reference mass and uniformity; failure aborts the side and the complete staged transaction.

Primary practice consulted: He, Sun and Tang's [Guided Image Filtering author page](https://people.csail.mit.edu/kaiming/eccv10/index.html) and [paper](https://people.csail.mit.edu/kaiming/publications/eccv10guidedfilter.pdf), sections 3.4 and 5, explain separating base/detail and controlling detail while considering halos. This implementation is **not** their guided filter: it uses independently measured forehead support and a bounded weighted box reference rather than fitting a guided local linear model. [OpenCV's official filter API](https://docs.opencv.org/4.13.0/da/d17/group__ximgproc__filters.html) was inspected for mature practice. The [specific guided-filter source](https://raw.githubusercontent.com/opencv/opencv_contrib/4.x/modules/ximgproc/src/guided_filter.cpp) carries BSD-3-Clause; [OpenCV's broader license](https://opencv.org/license/) is not a substitute for that file header. No external code or weights were copied, downloaded, installed or executed. No new learned model or model-compatibility claim is introduced.

## Source ownership and measured support

The existing verified MediaPipe 478-point digest supplies measured brow chains, face oval and exclusion anatomy, not a hairline or semantic hair mask. Actual current-source RGB, independently retained face-skin observation and known excluded coverage admit adjacent forehead references and dark original-brow pixels. Per-third visibility, reference chroma/uniformity and strip-half tests refuse ambiguous evidence; all other same-source retained face boxes are protected, including disabled faces. No copied makeup consent, masks, pixels or cross-owner analysis are accepted.

Only requested nonzero sides undergo photometric admission. The opposite measured brow and eye/lip/nose boundaries remain protections. Normalized retained anatomy is evaluated on the actual render grid; original producer dimensions are provenance, not incorrectly required to equal a proxy grid. Full-source export prepares its own full-resolution evidence and correction, not an upscaled preview bitmap. Native radius and memory bounds can refuse an excessive case; there is no silent downsampling.

## Integration

- Nested active/undo/redo project graph validation checks exact new scalar leaves and fully resolved linked recipes before live mutation; unresolved inheritance conflicts remain explicit recoverable intent.
- Strict state/native loader, native capability handshake, packaged source/header/license and an authored build script. Runtime does not compile or substitute a Python effect when the binary is unavailable.
- Canonical people registry, atomic edits and complete linked-value validation. Valid zero-strength linked-state choices are interaction-only neutral; malformed/nonzero requests still need source admission.
- Derived sources resolve their actual immutable owner, RGB and analysis. Original pixels and old operation semantics remain untouched.
- One prepared `brow_enhance` local effect is composed before added brow makeup, then passes through the existing common geometry sampler. No new independent resampling path.
- CPU and device composition use one feasible scalar for the prepared encoded-RGB delta against actual upstream SDR headroom. Output channels are not individually clipped. This feasibility policy is not a claim of linear-RGB chromaticity after other colour operations.
- Dedicated native UI route, subject-side controls, atomic relinking and reset, effective-source/shared-intent ownership and pending/uncertain fences.
- Presets transfer scalar intent only. Target-owned anatomy, source and forehead observations are remeasured; a failing target must not silently skip a requested side or publish partial changes. General unsupported derived transfer routes remain fenced.

## Honest limits and review

Existing canonical preview is the before/after review surface. Strength selection is explicit, but this slice does not add manual painted brow support, a new persistent review receipt, or semantic brow/hair segmentation. It does not distinguish all tattoos, pigment, makeup, shadows and hair. Pale/white/low-contrast brows, occlusion, unusual projection, unreliable forehead skin, insufficient resolution and extreme export scales may refuse. Negative strength is not complete brow removal or hidden-skin reconstruction. No hair growth, gap filling, physical component separation, symmetry, 3D correction or proprietary matching is claimed.

Monotonic residual and chromaticity statements apply only to the native source calculation with fixed admitted coverage/reference and feasible gamut. Binary support admission, spatially varying references, later makeup/colour edits and joint geometry prevent a global perceptual-order or final-colour guarantee. Broad HDR/alpha retouch support remains unfinished; active unsupported values are refused, never clipped to manufacture support.

All numerical, native ABI, UI, photographic, performance, memory-peak and end-to-end acceptance remains **AUTHORED / UNRUN**. Static source review and fixtures are not functional acceptance. This bounded source-connected implementation does not mark the complete official photographic experience accepted.
