# Reviewed lower-lid ridge preservation

Status: source development only; every numerical, photographic, native, history,
project-reopen and export acceptance case remains UNRUN.

## Exact requirement and boundary

Original requirement `LNX-REF-PC-32464-C-e5fac5fdcf` is the preservation child of
eye-bag correction (`LNX-REF-PC-32464-C-fafd366f9d`). The supplied handbook,
`manual-text.txt` lines 503–504, says eye-bag correction preserves the lower-lid
ridge by default. The official desktop guide was read on 2026-10-24:
<https://www.pixcakeai.com/guide/32464>, section 祛眼袋 / 保留卧蚕. It describes
complete default preservation, with a decreasing slider attenuating that ridge.
The guide gives no public numerical implementation or anatomical segmentation
contract. This implementation must not be represented as vendor equivalence.

The bounded new path is `lnx.eye_bags.v2`: the user marks and confirms the visible
ridge separately for each treated eye on the actual immutable source. A default
preservation value of one removes this operation's correction from fully covered
source pixels. Fractional coverage has fractional protection. An unreviewed eye
is not treated and is reported as such; missing review never means no ridge.
This is manual-assisted preservation, NOT automatic ridge segmentation, learned
AI, or a guarantee that zero preservation completely removes a ridge. The
original requirement therefore remains PARTIAL, not accepted or newly counted.

The old `lnx.enhance.v1` eye-bag recipe retains its existing numerical behavior.
It is not automatically converted. Explicit replacement stages removal of the
old eye-bag amount together with the new recipe, with actual full-image review.
Other eye and portrait operations are not reset or masked by this protection.

## Existing numerical method and licenses

The existing repository adaptation of RapidRetouch is pinned to revision
`5e9d9c1d2770ff29d11a3879e5a90aad5887e028`. Its eye-bag correction combines
frequency-separated local relighting with a line-sensitive crease correction.
It is not generic Gaussian skin smoothing. Its original source and all constants
remain unchanged in this slice. The new source-owned protection blends only this
correction, not the aggregated dark-circle, sclera, catchlight or vein delta.

Primary upstream license was read at
<https://github.com/crispin81/RapidRetouch/blob/5e9d9c1d2770ff29d11a3879e5a90aad5887e028/LICENSE>.
The pinned source-file web request returned a cache miss; no new upstream source
download or comparison is claimed. The checked-in adaptation, full license and
`third_party/rapidretouch/UNDER_EYE_NOTICE` are the local source evidence.
That adaptation remains AGPL-3.0-only, including its combined-work obligations.
The original new Rust blend/support/host code uses the repository's
GPL-3.0-or-later license. No third-party model, weights or new code were imported.

## Mature workflow comparison

The darktable project's primary manual documents selective frequency retouching
and user-drawn masks:

- <https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/retouch/>
- <https://docs.darktable.org/usermanual/development/en/darkroom/masking-and-blending/masks/drawn/>

These support the architectural choice of source-coordinate vector masks rebuilt
at the render resolution and selective corrections rather than proxy-mask
upscaling. They do NOT establish automatic anatomical recognition or quality of
this implementation. No darktable code, assets, prose or algorithms were copied.

## Honest protection and image limits

Protection means this new operation's pre-geometry correction is zero in the
fully protected region. Other portrait effects, common geometric resampling,
global grading and export color transforms can still change final output pixels.
The UI must show this distinction, actual source support, and actual mixed-graph
before/after images before confirmation. A drawn outline alone is not evidence
that the numeric mask has a fully protected core.

Only the currently supported opaque SDR source path is admitted. PNG16 samples
stay float32 through the existing decoder/renderer; that is not alpha or HDR
support. Uncertain anatomy, occlusion, very small eyes, ambiguous ownership and
unreviewed target images must not be silently supplied with substitute masks.

Transfer of scalar intent never authorizes copying this source's painted ridge,
landmarks, semantic support or FaceRef. Any unsupported preset/batch or alias
workflow remains an explicit refusal until its complete affected-image review
and target-local ownership are actually implemented.
