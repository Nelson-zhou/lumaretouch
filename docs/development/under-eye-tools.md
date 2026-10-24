# Independent under-eye controls

The existing enhance command accepts dark_circles and eye_bags in [0, 1], both
zero by default. Partial updates retain all other enhancement settings. These
parameters are separate from sclera, iris and teeth, whose algorithms and
three-channel masks are unchanged. The specification's two existing under-eye
rows are connected to independent sliders; the unsupported preserve-aegyo-sal
switch remains disabled rather than claiming a separate capability.

Later source-only extension: `lnx.eye_bags.v2` now has a separate manually
reviewed lower-lid preservation path, documented in
`docs/eye-bag-preserve/REQUIREMENT-AND-RESEARCH.md`. It does not enable an
automatic preservation switch on this legacy algorithm or reinterpret old
recipes. Only independently reviewed eyes are treated; automatic anatomical
ridge detection and photographic acceptance remain unfinished.

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
Old projects fill missing controls with zero. The later canonical
`enhance_scope` and people-transfer routes carry scalar intent and resolve
target-owned analysis; the earlier statement that all presets exclude enhance
settings is obsolete. They must not copy one person's coordinates or masks to
another photograph. The separate reviewed eye-bag v2 operation currently fences
active generic preset/batch changes until its required target-local image review
exists. Document export includes legacy controls through their existing route.

Development-first delivery: only static source review performed. No application
execution, build, typecheck, image-quality validation or regression run was made.
