# Neck fine-line correction: current-photo integration

Status: single-photo source integration authored, all numerical, runtime, photographic and
performance acceptance UNRUN. Exact requirement `control:PC-32464:19`, official
[PC-32464](https://www.pixcakeai.com/guide/32464), remains partial. This is not an
automatic neck detector or learned blemish-removal implementation.

## Actual operation and licence

`lnx.neck_wrinkle.v1` owns version 1 and one amount in [0,1]. Its dependency-free
Rust ABI 1 is an explicitly AGPL-3.0-only derivative of Chris Cork's pinned
RapidRetouch neck-line method. NUMERICS.md and core/neck_wrinkle/NOTICE identify
exact upstream sources and adaptations. The complete unchanged AGPL licence,
notices, header and derivative source are staged with the library. Existing
facial wrinkle and neck geometry algorithms and saved values are unchanged.
There is no runtime compilation, automatic installation or numerical fallback.
Missing native capability refuses activation; neutral reset/detach remains.

The algorithm measures three-scale line structure, morphological depth and
pore-scale detail, rejects dark strands and attenuates broad folds. Its positive
bounded log-gain is applied as common linear-RGB gain to the current stage,
retaining current chroma and headroom. It does not invent skin, reconstruct an
occluded neck, remove jewellery or claim to distinguish anatomical tendons.

## Source, support and rendering

The existing FaceRef and explicitly associated BodyRef identify the reviewed
person. Independent source-normalized neck/context brushes and hard protection
are retained in the one people support bank. Existing measured body-skin
coverage is not instance/neck/jewellery segmentation. Users must exclude hair,
beard, clothing, jewellery, tattoos, hands, other people, tendons and structural
shadows; unclear ownership or insufficient complete context refuses correction.
The observed line half-width is explicitly 1.4..12 canonical source pixels.

Trusted transient factories decode the original genuine bit depth and existing
ICC path, or the immutable opaque-SDR creative source. Original producer-grid
analysis is resampled once. Existing ordered repair math and original repair
weights are materialized at canonical size before numerical fitting. Delivery
RGB8 pixels and analysis/display proxies cannot become the fit source. Source
and active/redo repair proofs travel separately; original provenance remains.
No source pixels, measured fields or decoded buffers are persisted per history.

The canonical common people pipeline carries the new stage before shared
geometry. Ordinary reduced display uses an explicitly labelled conservative
projection of the full-source measured gain, not a proxy-grid solver. Such
records deny review/export authority. Full candidate review and export require
unprojected canonical fields. Current working pixels receive the effect, so
other skin/portrait/colour edits are not replaced by a source bitmap.

## User workflow and transaction

The PC-32464 panel uses the existing application-lifetime people request owner.
It reads a genuine source image and a native source crop, paints source-edge
coordinates, previews the complete before/after mixed render plus actual
eligible/protected/context-rejected overlay, and requires three image hashes
plus a matched native-output crop pair. Source crops are painted in source
coordinates; output crops are never treated as source after geometry.
RGB8 PNGs are display transport, not precision-preserving image masters.

Confirmation binds exact source, repair, analysis, support, people graph,
document revision and canonical measurement key. A typed single-use publication
permit is rechecked after preparation and before the existing graph commit.
The existing graph/support/document history, receipts and query-only uncertain
outcome protection remain the owners. Native validation and the app-lifetime
review guard reject uncorrelated successes even when the panel unmounts.
Direct parameter patches permit only one exact zero leaf. Atomic detach also
removes this family's pointer, not unrelated support or recipes.

The existing native recovery fence retains confirmation, detach and exact reset
until an original-request-matching terminal receipt or a verified workspace
reopen. A same-ID event, altered request marker or bare project-open event cannot
release it. This remains the existing single-photo owner, not composite history.
The app blocks review while another image tool, candidate panel, sampler or
editor queue is active. Read-only progress is labelled as non-publishing.

## Source review on 2026-10-25

Shared people registration, request binding, graph publication, native receipt
guards, canonical source/repair replay, preview/export stage and package staging
were inspected as source. Two independent source reviews found no confirmed
source/render or ABI/core disconnect. The recovery fence gap was corrected and
an unrun native regression fixture added. Root NOTICE now links the new AGPL
derivative and its complete staged source/notices. The official PC-32464 neck
description was reopened; the pinned upstream licence URL failed web retrieval,
so earlier recorded connector evidence and retained exact notices remain the
licence basis, not a claimed new web verification.

These are source observations only. No compiler, typechecker, product import,
numerical test, browser test, real photo or performance run was performed here.

## Explicit residuals

- Manual-assisted visible-neck support, not automatic anatomy or model parity.
- Current-photo current-face only. Preset/batch/cohort/shared-source aliases and
  dedicated effect-recovery painting are not implemented. Parked target changes
  are refused; unchanged unrelated intent can render.
- Opaque SDR only; no alpha/HDR clipping, no silent resolution fallback.
- Full-grid method with conservative memory admission. Neither 24 MP operation
  nor measured peak memory/latency is established. Insufficient budget refuses.
- Native crop inspection is only the acknowledged rectangle, not proof that a
  user inspected every source pixel. Display projection is approximate.
- Cancellation checks occur at supported boundaries; individual decoder/repair
  calls are not forcibly interrupted. No new cancellation UI is claimed.
- No numerical parity, quality, compiler, typechecker, product execution, test,
  performance, hardware or model acceptance has run. Historical undo/reopen
  fixture coverage is authored, not functional acceptance.
