# PC32473 瘦腰: reviewed visible contours

## Exact requirement, not the rest of whole-body shaping

This slice targets only `PC-32473-C-8268ea3e37`, requirement
`LNX-REF-PC-32473-C-8268ea3e37`, original control path `瘦腰`.
The supplied `AI开发资料包/功能需求验收映射.json`, lines 5145–5159,
marks it P1 and associates `PORTRAIT-008`; that module-level association is not
specific implementation or acceptance evidence. The supplied manual's
`全身美型` section (text lines 561–567) is broader than this slice.
The original mapped reference is https://www.pixcakeai.com/guide/32473.

Primary sources inspected 2026-10-23:

- [PixCake official explanation](https://wiki.pixcakeai.com/guide/9412.html),
  瘦腰 section, lines 107–109: “调整腰部线条向内收缩。” The section does
  not publish numeric range, steps, neutral value or bilateral unlocking.
  Separate sections cover waist length and upper-body length. No inference from
  another feature's slider or unlocking is treated as a waist specification.
- [GIMP upstream Warp Transform manual](https://docs.gimp.org/3.2/en/gimp-tool-warp.html)
  describes local image deformation with size/strength, interpolation and
  out-of-buffer handling. It supports a local visible-pixel workflow, not hidden
  anatomy reconstruction or background preservation guarantees.
- [GIMP upstream Cage Transform manual](https://docs.gimp.org/3.2/en_GB/gimp-tool-cage.html)
  describes user-placed transformation anchors and confirmation. This is primary
  open-source practice for explicit spatial control, not evidence of commercial
  algorithm equivalence or this implementation's runtime quality.
- [Davies Media Design creator tutorial](https://www.youtube.com/watch?v=hSTEeQkVFMg),
  published 2018-07-31: its indexed creator description discusses small body
  retouches with Warp and Cage. Only that description was accessible; the video
  itself could not be fetched and was not watched. No visual claim relies on it.

## Original implementation policy

The recipe is one `lnx.waist_shape.v1` operation with `{version:1, amount:0..1}`.
Zero is neutral; positive amount contracts the reviewed visible contours inward.
The range, zero default, numerical falloff, nine stations, support thresholds,
conservative refusal rules and UI are ORIGINAL local engineering choices, not
published PixCake parameters. There is no separately unlocked side control.

Actual BodyRef v2 shoulders 11/12 and hips 23/24 provide orientation only.
They do not locate a waist automatically or measure anatomy under clothing.
The user supplies and reviews upper/lower axial bounds and BOTH visible contour
profiles on the canonical unretouched source. Each side has nine independently
measured distances; missing values cannot be mirrored, interpolated from the
opposite side, filled with a preset, or inferred from body ratios.

Source support kind is `waist-source-visible-contour-v1`. Its payload is:

- `version:1`, `upper`, `lower`: reviewed fractions along the shoulder-midpoint
  to hip-midpoint direction, never height/length adjustment controls.
- `stations:[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9]` within those bounds.
- `negative` and `positive`: independent nine-element contour distances,
  normalized by `min(source_width-1, source_height-1)`.
- `region.selection_box` and `region.exclusions`: reviewed source-normalized
  ownership rectangle and keep-out rectangles.
- Seven explicit true confirmations: `bilateral_visible`, `bounds_reviewed`,
  `not_occluded`, `not_foreshortened`, `ownership_confirmed`,
  `visible_material_only`, `transition_pixels_reviewed`.

Original numeric admission policy currently requires actual anchor visibility and
presence at least 0.8; torso axis at least 64 source pixels and 8% of the shorter
source side; shoulder/hip transverse spans at least 20% of torso length, agreeing
in direction, with ratio at most 2. Axial tilt and depth difference are bounded
relative to the measured span. These are conservative implementation fences,
not a recovered anatomical model. Reviewed bounds are strictly within the axis
and at least 32 source pixels apart; each measured width is at least 2 pixels and
at most 80% of torso length. Transition factor is 1.8, with radius at most three
times the reviewed interval. The native gain is 0.22 and admitted local Jacobian
range 0.77–1.23. None of these numbers is an official PixCake range or a runtime
quality result; source changes to policy require corresponding acceptance review.

The immutable enclosing body support binds operation, source SHA/dimensions/
orientation, BodyRef, actual point digest, analysis revision and support content.
The operation review is independent of shoulder, leg and arm reviews. Explicit
review cannot upgrade unreliable actual anchor confidence or authorize another
source/body/analysis. Model-predicted joints are observations, not a complete
person census. Reviewed support is MANUAL, never relabeled as AI segmentation.

Loose clothing means visible CLOTHING contour adjustment only. Reject obscured
sides, uncertain body ownership, severe foreshortening/perspective, overlapping
people, unclear arm-to-waist contact and missing bilateral support. Do not invent
hidden skin, anatomy, an unseen side or a demographic body template. Known nearby
bodies/faces/exclusions may conservatively reject otherwise plausible scenes.

## Geometry and compatibility obligations

The Rust kernel evaluates an off-grid inverse displacement field, not RGB pixels.
The field must enter the existing single per-BodyRef composition before face
inverse evaluation. The shared pipeline samples source RGB once, not once per
body feature. Active waist uses authoritative body operation order v4; merely
adding/selecting/reviewing a neutral waist operation preserves the existing
v1/v2/v3 geometry identity. Shoulder, leg, arm and hair behavior remains separate.

ALIGN8 preview dimensions can introduce unequal axis ratios. The field must
conjugate exact source coordinates into render coordinates separately in x/y,
not scale both dimensions by width alone. The complete transition support, not
just contour samples, must fit the reviewed ownership window.

Compact support can preserve pixels outside the complete support domain. It does
NOT promise untouched background or garment texture INSIDE the transition area.
Background lines and cloth patterns may move. Inspect them at final resolution;
Jacobian, displacement, memory and ownership fences are safety restrictions, not
proof of pleasing photographs.

Keep one shared body bank and existing project14/history ownership. Source-owned
reviews, contours and stable identities do not travel in generic batch/presets.
Preserve recovery, immutable original-request receipts and uncertain-result
reconciliation. A sent request or saved file is not proof of published pixels.
Retained source/pose/support changes must invalidate preparation. Export rebuilds
geometry at original dimensions, preserves RGB8/RGB16 source gates, and must not
reuse an enlarged preview displacement or silently downgrade source precision.

## Acceptance status and remaining work

Status: SOURCE INTEGRATION AUTHORED; RUNTIME/QUALITY NOT ACCEPTED.
`engine/tests/fixtures/waist_shape/acceptance.json` contains 64 explicit UNRUN cases.
No test, build, compiler/typecheck, product import/execution, inference, install
or model/software download is performed in this source-only turn. No screenshot,
photographic result, quality pass or commercial parity is claimed. The final
integration manifest, owned by the integration lead, freezes exact source bytes;
it is not a runtime acceptance certificate.

Later local acceptance must compile/package the ABI, execute contract and lifecycle
checks, exercise actual native UI and recovery, and inspect authorized real source
photographs and final RGB8/16 exports. Include asymmetric visible contours,
patterned backgrounds, loose clothing, contact/occlusion refusals, multi-person
ownership, rotated frames, stale sources and lost replies. Save actual input/
output hashes, publication receipts, screenshots and reviewer decisions before
changing any case from UNRUN. Synthetic tests are schema/negative evidence only,
never detector outputs or photographic acceptance.

Explicitly NOT completed by this slice: waist length, upper-body/torso length,
whole-body slimming, AI shaping, body smoothing, hidden-anatomy recovery,
automatic waist semantic segmentation or pixel-perfect PixCake reproduction.
