# PC-46608: 手部美型 — source implementation / UNRUN

## Requirement, not invented handbook controls

`ui/src/spec/refine.json` PC-46608 names three separate families: 手部中性灰,
祛青筋 and 手部美型. The last describes hand width, fingers and knuckles.
It does not publish numerical ranges, default strength or demographic rules.
This source provides separate original signed `palm`, `finger`, `joint` controls
(-1..1; UI -100..100, default zero), not whole-body slimming under a new label.

## Ownership and visible review

One explicitly selected visible hand per document is supported in v1. Its
`_hand_shape` recipe is owned by the existing document snapshot/history/project
owner, including virtual copies. No FaceRef, BodyRef, 33-point body-pose result,
new undo framework, identity, medical label, age or gender template is required.
A standalone hand photograph is a supported input shape; execution is untested.

Source review uses the canonical original-frame RGB8 analysis representation.
If prior repairs exist, the actual repaired pre-geometry source is replayed first
and converted to RGB8 only for display/model input; the original-bit-depth render
source remains unchanged. Exact original source SHA-256/dimensions, repair-stack
digest, document revision, workspace and full state fence bind the review.
Current v1 refuses creative-derived source reuse and cross-photo/batch/preset
copying. Changing source or repairs invalidates the review rather than rebinding.

Users independently mark each visible palm/finger/knuckle region: longitudinal
start/end and actual two opposite contours near its midpoint. Explicit contact,
other-hand, nail, jewelry or background protection rectangles are exclusions,
not a claim that an automatic detector found those objects. Every visible-only,
ownership, no-contact, transition and protection confirmation is separate.
Hidden or ambiguous anatomy is never filled. Supports are drawn on the source
image, and the complete before/after plus actual support overlay must be reviewed
before the retained candidate can be confirmed. Each new preview replaces the old
candidate; confirmation cannot submit a different recipe or fabricated proposal.

Optional MediaPipe output is only a visual landmark proposal. Missing or invalid
model/runtime yields an explicit unavailable state; manual support is labeled
manual, never AI. The server retains the actual proposal and source/input/model/
backend hashes; a client supplies only its retained ID. Out-of-frame coordinates
are preserved as evidence and not silently clamped. Actual geometry is always
independently marked/corrected source support, not a hidden demographic template.
See [MODEL-PROVENANCE.md](MODEL-PROVENANCE.md) for reviewed license/hash evidence.

## Original numerical policy

Rust consumes at most 32 compact elliptical primitives, in retained order:
center, longitudinal unit axis, longitudinal radius, transverse radius, signed
strength. The longitudinal radius is half the marked axis length; transverse
support is 1.8 times the larger measured side width. This includes explicitly
reviewed nearby transition pixels, not a promise of unchanged local background.
Length >=8 source pixels, contour width >=2, width asymmetry <=2:1, radius aspect
0.2..5, a one-pixel source-edge inset, and a conservative cumulative displacement
budget min(128px,5% of source short side) are original conservative limits.

Each inverse maps transverse coordinate `v` to
`v + 0.12*amount*v*(1-u²/a²-v²/b²)³` inside its support, identity outside.
The compact map has a globally positive analytic determinant; chained actual
queries also require determinant [0.25,4] and finite in-source coordinates.
The core validates all input before writing either output and rejects aliasing.
It accepts no RGB pixels and contains no image sampler or model.

Original source-pixel state is evaluated at actual off-grid points. Preview
queries/displacements are conjugated through source/render scale, not enlarged
sampled deformation LUTs. Independent document-hand fields join the existing
hand→body→face inverse chain before its ONE source RGB/mask/recovery sampler.
No extra hand image warp is inserted. Existing final manual-liquify remains its
independently established later stage; it is not relabeled as this tool.

Distinct document-hand IDs never occupy face/body identity fields. Ambiguous
support overlap with other hand/body fields, observed faces or protection is
refused. Disjoint edits compose; same-location hand/body overlap is conservatively
unsupported, not silently partially applied. The final composed raster also has
seam/Jacobian checks. No photographic injectivity/quality acceptance is claimed.

## Lifecycle, transport and budgets

`reference → optional propose → preview → confirm` uses the existing full target
candidate renderer. Confirm/clear use existing document history and frame owner;
uncertain writes are queried by their exact original ID rather than replayed.
Mutation receipts are bounded and not evicted to create a replay opportunity.
Source/revision/epoch/candidate/PNG hashes are checked by UI/native and engine.
A failed rollback stays explicitly uncertain if the restored frame cannot be
published. Native transport reconciliation accepts only an exact late terminal.

Original-source maximum is 32 MP. Existing full-render admission applies; model
and primitive/map allocations have explicit conservative budgets. Three display
PNGs are bounded to 768px and the complete comparison payload to 7 MiB below the
native 8 MiB receipt limit. These bounds are not measured performance claims.
Export re-solves source geometry at original resolution, with original decode
stamp/digest fences and existing tile halo/sampler ownership. Source-dependent
passthrough and stale edited-source captures cannot bypass the hand intent.

## Verification status

All source, Rust/engine/native fixtures and acceptance checklists are authored.
Only AST parsing, text inspection and whitespace checks are permitted here.
No tests, builds, typechecks, model imports/inference, installations, photographic
quality, edge/contact reliability, performance, memory peak or device acceptance
have been run. Qoder owns those deferred gates. No push or upload occurred.
