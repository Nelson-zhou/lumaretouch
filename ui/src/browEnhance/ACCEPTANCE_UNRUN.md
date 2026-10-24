# 眉毛增强 UI: authored, not runtime accepted

Status: AUTHORED / UNRUN. Source reading and editing only. No product imports, application execution, tests, builds, type checks, inference, downloads or real-photo acceptance were performed. Authored fixtures do not prove passing tests or visual quality.

## Exact requirement and reference

- Requirement: `LNX-REF-PC-32471-C-18765fa8ea`, exact handbook leaf `PC-32471|眉毛增强`.
- Official reference supplied for this task: https://www.pixcakeai.com/guide/32471 . Its required semantics are negative values reducing existing brows, positive values strengthening them, and unlocking to adjust left/right independently. No official numeric range, photometric gain, support geometry or acceptance threshold is inferred.
- One UI leaf routes to `brow_enhance.v1` and renders the complete bilateral `BrowEnhanceControl`. The distinct operation is `lnx.brow_enhance.v1`, not a material, geometry or exposure alias.
- Strict recipe: `{version: 1, linked: boolean, left: number, right: number}`. Side values are finite in `[-1, 1]`; linked values must be equal. Default is linked with both zero. Display `[-100, 100]` is product-local, not official calibration.
- Dedicated native capability: `brow_enhance_available` / `brow_enhance_reason`. Availability does not establish support, visibility, source validity or successful render for any side or target.
- Existing `PC-32466|眉毛` geometry and `PC-32471|局部妆容/眉毛` material/color routes remain unchanged. Unmanaged documents explicitly refuse this leaf, with no direct-native or other-effect fallback.

## Effect and evidence boundary

The intended effect changes source-measured existing dark-brow contrast relative to a reliable adjacent source forehead reference. Negative reduces existing contrast and positive strengthens it. It does not add brow materials, generate hairs, change brow shape, completely remove hairs or makeup, recover occluded detail, or apply generic exposure.

The current effective source may be the original photograph or an already returned composite. Every target owns its own geometry and photometric admission. The UI never fabricates support measurements, contrast statistics, anatomy facts or a photograph-quality result. It displays raw engine refusals, including refusals that may belong to another active operation, rather than inventing an inferred per-side capability.

Subject-left and subject-right are explicit; they are not viewer-left and viewer-right. Equality under linkage is numeric, not a guarantee of visual symmetry. Occlusion, clipping, yaw, sparse/light brows, forehead texture and strong highlights/shadows may prevent admission. Compatibility with earlier geometry and other effects remains engine-owned; no bypass is supplied.

## Ownership and intended interactions

- Existing `PeopleOwner` remains the only command, queue, receipt, history and replay owner. New writes contain only `/linked`, `/left` and `/right` of `lnx.brow_enhance.v1`.
- Selected-face actual values and their provenance are displayed independently from explicit target values. A matching independent face may edit its actual values. Shared all-people/group/person targets start blank unless the exact target already owns the relevant explicit mode or amount. The selected preview's inherited values never seed shared writes.
- Nonzero editing requires matching source, document epoch/revision, face/analysis identity, state and association revisions, current target, enabled real analysis, and native availability. Group previews must belong to the group; person previews must have a confirmed nonfuture association. These are UI fences, not substitutes for engine target admission.
- Raw blank, malformed, nonfinite and out-of-range text is rejected. No write occurs on mount, blur or mode display. Relink requires a deliberately entered common number, applied atomically with `/linked=true` and both equal amounts; neither side is copied or averaged.
- Normal unlock writes only `/linked=false`, preserving both amounts. Linked adjustments write both sides equally; independent adjustments write only the selected side.
- Explicit unsupported-side recovery has two clearly labeled actions. Each atomically writes `/linked=false` and zero to the deliberately chosen subject-side, leaving the other amount unchanged. It is never automatic, does not infer the unsupported side, and in shared scope applies to the selected scope, not merely the preview face. The remaining nonzero side still requires engine admission.
- Both-side reset atomically writes only two zero amounts, preserving linked mode. It does not restore inheritance, mutate another effect, remove shared defaults at other scopes or migrate old brow recipes. It remains accessible without native, effective reads or anatomical support, while ownership, source binding, pending/uncertain and competing-editor fences remain mandatory.
- Draft/callback keys include source binding, state and association revisions, full face/group/person/link membership, selected face, target, read provenance/conflicts, explicit amounts and refusals. Replaced owner command/check identities also invalidate drafts. Mounted/current-binding/current-owner checks reject late callbacks, and a submission latch fences repeated clicks before the owner responds.
- Pending and uncertain requests prohibit mutation. Uncertainty queries the existing original request without resending. Raw refusals and owner errors remain visible. No silent side skipping, guessed coexistence rule or inferred successful visual outcome is introduced.

## Authored fixtures, all UNRUN

`model.unrun.test.ts` covers exact identity and schema; signed bounds and invalid inputs; equal linked values; atomic relink, flag-only unlock, explicit one-sided neutral recovery and both-side reset; dedicated capability; actual provenance versus explicit target intent; blank shared choices; group and confirmed-person membership; stale sources/revisions and conflict refusal; neutral recovery without native/anatomy; ownership/request fences; source/membership keyed invalidation; strict numeric input; nonmutation and preservation of other operations.

`wiring.unrun.test.ts` covers one exact route with complete bilateral controls; preservation of existing material/geometry routes; unmanaged refusal; dedicated DTO fields; sole people owner; competing-editor fences; provenance separation; explicit relink and unsupported-side recovery; mounted/owner/membership/duplicate-click fences; query-only uncertainty recovery; anatomy-independent neutral buttons; raw engine refusals and truthful photometric/semantic limitations.

Still UNRUN: all authored assertions, TypeScript compatibility, compilation, mounted React interactions, native capability delivery, actual per-target geometry/photometric checks, negative/positive visual behavior, subject-left versus viewer-left, atomic history and replay, rapid source/target/membership/owner switching, pending and uncertain recovery, unsupported-side recovery, shared-target effects, sparse/light/occluded/clipped brows, contaminated forehead references, earlier geometry/material coexistence, source-composite replacement, preview/export parity, packaging and full-resolution real-photograph acceptance. No complete 妆容调整 family or development-pack acceptance is claimed.
