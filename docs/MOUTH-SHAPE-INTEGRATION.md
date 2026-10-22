# PC-32466 mouth2D: source implementation and open acceptance gates

Status: source written, not runtime or photographic acceptance. No product,
compiler, test runner, inference, installation or download was executed here.
All acceptance cases below remain unrun for the local verification owner.

## Requirements and source

Checked the immutable AI package `功能需求验收映射.json` and live official guide
https://wiki.pixcakeai.com/guide/9405.html, lines 301–351, on 2026-10-22.
Family `PC-32466-C-cbb4c198e8`. Leaf IDs all prefix `PC-32466-C-`:

| Recipe | Suffix | Meaning |
| --- | --- | --- |
| size | c6608e6df0 | Left smaller, right larger |
| width | 25a12375ad | Left narrower, right wider |
| vertical | d9f05e02e0 | Left UP, right DOWN, opposite eye/nose position |
| horizontal | 76ebd0c9bb | Left/right head-local translation |
| gummy | eb54b58b96 | Observed upper lip moves down; bilateral unlock |
| m_lip | 64e1410070 | Left stronger cupid peaks/bead and subtle corner lift, right flatter |
| tilt | 120b651906 | Signed rotation; guide repeats same direction for both signs |
| upper | 71447c0f00 | Outer upper lip thinner/thicker, inner border retained |
| lower | 5fd3068bc8 | Outer lower lip thinner/thicker, inner border retained |

Only gummy explicitly promises split-side unlock in the guide. The other eight
are scalars. Gummy sides refer to the person, not viewer. Linking preserves unequal
values until the next explicit linked edit. Its range is nonnegative [0,1]; no
reverse exposure of unseen gums/teeth. Other values [-1,1], UI ×100. Bounds and
coefficients are local policy, not commercial numeric specifications. Positive
local tilt is clockwise in the unrolled image right/down plane, negative is
counterclockwise. This is OUR choice because the source sign text is ambiguous.

## Geometry and source evidence

Original GPL Rust control math uses full observed MediaPipe 1.1.1 outer AND inner
lip rings, reusing repository Apache-licensed topology and notices. Existing
`lip_makeup_geometry` supplies RGB/known-occluder evidence, never cosmetic state.
Eight signed operations and bilateral gummy have distinct role-specific math:
whole-ring size, horizontal scale, vertical/horizontal translation, rigid tilt,
outer-only upper/lower thickness, cupid peaks and inner bead shaping plus corner
lift, and downward upper-ring movement. This is not nine whole-mouth scales.

Gummy translation is bounded by the observed aperture and tapers at corners.
Closed or unobservable apertures refuse gummy; observed closed lips can still
support non-opening operations if contour and texture checks admit them.
Unsupported upper/lower regions, inadequate RGB contrast, known occluders,
foreshortening, clipped/degenerate contours, contradictory near-coincident
controls, target contour crossing, protection conflict and fold risk refuse.
Photometric evidence is conservative, not a complete occlusion/lip segmentation
model. Unknown skin-coloured occluders remain a limitation. Jacobian probing is
an admission heuristic, not proof between probes.

The source lip texture is moved, not regenerated. No teeth/gums/interior model,
inpainting, invented vermilion or new downloadable model is introduced. New
M-lip is not legacy `deform.smile`: it shapes cupid contour and bead as well as
corners. Legacy smile remains bit-for-bit untouched in state and old neutral
render paths; UI reports its amount and intentional stacking. PC-32471 lip makeup
remains independent. Reset mouth does not reset either feature.

## Composition, transport and lifecycle

Mouth pullback M composes after eye E, nose N, brow B and automatic A:
`M(E(N(B(A(x)))))`. Evaluate each at actual off-grid coordinates, then sample image
and source-bound masks once using the resulting final grid. Mouth protection does
not inherit eye/nose lip anchors that would pin the target mouth. Final combined
displacement, not sum of independent maxima or mouth-only displacement, determines
original-size export halo. RGB8/RGB16 use original dimensions and explicit memory
refusals rather than silent proxy export.

Teeth support, lip makeup contribution/recovery, mouth wrinkle effects, local
masks and RGB must share that final map. In particular transported teeth support
must be zero wherever gummy moves observed upper lip over the original cavity;
never enhance a pre-warp mouth box or reuse a stale teeth support after warping.

Versioned parameter-only presets/batches recompute target selected-face anatomy,
source support and full-original fields. Face/source/model identity, history,
parking, reload, project redo records and export snapshots retain owner identity.
No derived field or source mask travels in portable intent.

UI reuses `latestIntent.ts`; native host reuses `ReceiptHost`. One in-flight and
one latest whole intent, source/face/engine epoch identity, explicit gesture
history, post-history authoritative recipe/revision, strict CAS and status-only
reconciliation after uncertainty are required. Admission is not completion.
Missing or wrong native ABI is visibly unavailable; there is no runtime compiler
or Python numerical fallback. Packaging explicitly builds and stages native
library, source, integration doc and existing license notices.

## Required local verification (none passed here)

1. Rust ABI, engine contracts, host integration, UI parsing/type checks/build and
   package contents including missing/wrong ABI. Static source parsing is not
   runtime verification.
2. Nine controls independently at both signs (gummy zero/positive only), real
   open/closed/occluded mouths, asymmetric lips, teeth/gums visible, lipstick,
   small source, head roll/yaw and illumination. Confirm distinct deformation,
   honest refusals and no invented tissue.
3. Gummy left/right unlock, re-link retaining unequal values, no mouth cavity
   flipping, and no teeth enhancement leaking onto lowered upper lip. Test with
   teeth enhancement, lip makeup/recovery and mouth wrinkles all active.
4. Neutral old-project exact output; legacy smile unchanged; M-lip and smile
   stacked then undo/redo; mouth reset leaves smile and lip makeup unchanged.
5. Slow/rapid drag, numeric edit, reset/link while pending, panel collapse, face
   change, source replacement, stale CAS, engine restart, lost receipt, status-only
   reconciliation and rollback failure. A continuous gesture is one history step.
6. Full-original RGB8/16, different tile sizes/seams, final-grid halo, local masks,
   recovery, picker, proof and optics parity. No source-size downsampling fallback.
7. Target-recomputed preset/batch admission, unsupported target rejection,
   selected multi-face ownership, parked photos, redo records and budget refusal.
