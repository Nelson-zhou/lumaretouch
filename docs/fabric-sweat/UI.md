# Reference-assisted garment sweat correction UI

Status: **AUTHORED / UNRUN**. Shared integration is owned by the app integrator. No build, type check, tests,
product execution or photographs were run. These files alone do not enable the
feature. Current-photo source and mutation authority remain with the app owner.

## Requirement and boundary

The retained original `ui/src/spec/refine.json` PC-32477 describes sweat-mask
add/subtract, original/mask display and explicit update. This UI covers the
manual current-photo interaction for `control:PC-32477:5`, `:6`, `:14`–`:17`.
It is not automatic stain recognition, five-person grouping, multi-garment,
batch, preset, or complete PixCake parity. Existing `fabric/FabricPanel.tsx`
continues to mean fine wrinkles; it is not renamed or reused as a sweat effect.

## Integration

Import `FabricSweatPanel` and `FabricSweatPort` from `ui/src/fabricSweat`.
Render `<FabricSweatPanel port={port} disabled={conflictingEditOrExport} />`.
The controlled port has `snapshot`, `reference()`, `preview(payload)`,
`confirm(payload)`, and `clear()`. They return `Promise<void>` and must update
canonical snapshot state rather than return ad hoc optimistic results.

- `snapshot.bindingKey` must include document ID, epoch and revision/source
  identity and change for navigation, history, source replacement and writes.
- `snapshot.reference` is the validated host reference response.
- `snapshot.preview` contains `{request, value}`. `request` is the exact preview
  payload the canonical owner sent; `value` is its authenticated matching host
  result. An echo from an untrusted or unrelated result is insufficient.
- Set `pending` before send, keep `uncertain` on ambiguous mutation failure, and
  reconcile the original request through existing receipt machinery. Never
  automatically resend `confirm` or `clear` after a timeout.
- `refreshRequired` blocks further edits until canonical state is refreshed.
  A successful write is not inferred from refreshing. Existing outer `doc_state`
  and receipt validation prove the write. No independent history bank is added.
- A `fence` is a lowercase 64-hex digest. Reference/preview IDs are opaque
  32-hex strings. `model.ts` matches the host's confirmed payload contract.
- Hook `reference`, `preview`, `confirm`, `clear` to the respective
  `fabric_sweat_*` actions with the standard outer document/request envelope.
- Missing capability disables nonzero algorithm preview. Clear is retained for
  a stored effect even when native capability is absent, subject to owner fences.

## Interaction and coordinates

Four independently composited brush stacks mark same-garment scope, stain target,
clean reference and hard protection. All use existing source-normalized brush
vectors with `version:1`, `domain:'source-normalized'`, existing `MaskObject`
brush fields, opaque strokes and no feather. Protect is add-only; undo-last and
clear-current remove erroneous protection strokes explicitly. The other roles
support add/subtract. Brush radius is a source-short-edge percentage, mapped to
separate normalized x/y axes so source-pixel circles stay circular.

The displayed transport image is the complete source, not a crop or numerically
sampled proxy. Canvas pixels are only a draft visualization. The host rasterizes
submitted source vectors and validates disjoint clean reference/target inside
same-garment support; UI strokes do not establish automatic garment ownership.

All four roles have separate overlays. Subtract affects only its own role, not
another role's overlay. Original/mask toggle changes presentation only. Cancelled
pointer strokes are discarded; source changes remount and clear drafts. A stroke
or parameter change invalidates review. 64 strokes per role, 1,024 points per
stroke and 4,096 total submitted points bound UI drafts.

Explicit Update generates matching full-composite before/after and source-domain mask
images. The mask retains original source aspect and is explicitly labelled as
not crop/rotation transformed; only before/after must have matching dimensions. Confirm requires all three to load with their declared dimensions and
an explicit human review checkbox. Loaded images are not proof of human visual
inspection; the checkbox records the user's assertion. A changed payload cannot
reuse a previous preview. Host remains responsible for image byte checks,
source/authenticity checks, canonical mask/radius bounds and final publication.

The radius 2–128 source pixels and amount 0–1 are local implementation contracts,
not claimed official PixCake parameter ranges. No new model, remote image upload,
installation or runtime library fallback is performed by this UI.

## Verification still required

Type/build checks; malformed/stale receipt tests at the canonical adapter; pointer
cancel and navigation while reading/writing; reference/target overlap rejection;
source aspect mapping; unknown-write recovery; clear with missing runtime; actual
colour/texture quality and large-image responsiveness all remain UNRUN.

## App-lifetime hook

`useFabricSweatPort(context, refresh)` is exported. Context is
`{bindingKey, documentId, revision, enabled, blocked}` with string revision. Mount
it once alongside the app's other request owners, not within a conditional
panel. It uses `fabricSweatRequest` and `fabricSweatStatus` from native.ts.

The hook sends a mutation once, keeps the original immutable request, and polls
only that ID until terminal. Exact outer echo, source fence, PNG header/dimensions
and SHA-256 are checked before exposing read results. Successful writes require
`doc_state.document_id` plus `doc_state.fabric_sweat.revision`, amount and
`recipe_sha256` matching the returned candidate. Refresh does not turn unknown
outcomes into success. The hook retains pending/unknown state across panel
unmount and document changes; no optimistic image or project-history bank is
created. A malformed terminal reply remains unresolved rather than being
reported successful. All paths remain source-reviewed only, execution UNRUN.
