# Independent under-eye controls

The existing enhance command accepts dark_circles and eye_bags in [0, 1], both
zero by default. Partial updates retain all other enhancement settings. These
parameters are separate from sclera, iris and teeth, whose algorithms and
three-channel masks are unchanged. The specification's two existing under-eye
rows are connected to independent sliders; the unsupported preserve-aegyo-sal
switch remains disabled rather than claiming a separate capability.

The implementation adapts RapidRetouch at revision
5e9d9c1d2770ff29d11a3879e5a90aad5887e028. Dark circles use surrounding-skin Lab
tone interpolation, not global brightening. Eye bags use frequency-separated
relighting plus a Hessian/closing crease detector, not generic skin smoothing.
See third_party/rapidretouch/UNDER_EYE_NOTICE and its AGPL-3.0-only license.

The selected face and real 478 landmarks use enhance's existing guard, deferred
rebuild and face-switch policies. Too-small and severely foreshortened eyes are
skipped. A complete face ROI is corrected against the source image, then its
RGB delta is composed at the enhance stage, before global colour adjustments.
The source includes committed repair strokes; repair-version changes invalidate
the cached correction before rendering, matching the export repair base.
This intentionally shares the existing enhance source-derived approach; it does
not rerun local lighting analysis on every already-smoothed preview frame.
Slider changes resolve the ROI once, while frame renders reuse its cached delta.
Full-resolution export resolves with full-resolution landmarks and source pixels
before splitting into tiles, so reference rings never acquire tile-edge seams.
No proxy-resolution correction is upscaled for export.

History and project serialization store the expanded enhance amount dictionary.
Old projects fill missing controls with zero. Existing portable colour presets
and generic cross-image batches exclude face-specific enhance settings; this is
kept explicitly, rather than copying one person's coordinates to another photo.
Document export includes both controls through the existing recipe route.

Development-first delivery: only static source review performed. No application
execution, build, typecheck, image-quality validation or regression run was made.
