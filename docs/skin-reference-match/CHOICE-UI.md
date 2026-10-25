# Measured reference suggestion UI

Status: **AUTHORED / UNRUN**, 2026-10-25. Source-only implementation and authored
fixtures. No product imports, tests, TypeScript typecheck, build, browser
interaction, inference, download, installation or photographic acceptance ran.
Static inspection is not a passing test or proof of integrated behavior.

## Scope and honest labels

The public requirement remains `control:PC-32465:19`. The official
[skin guide](https://www.pixcakeai.com/guide/32465) and
[wiki](https://wiki.pixcakeai.com/guide/9404.html) were directly reviewed on
2026-10-25. Their same-photo brightest-face requirement also describes face/body
tone and brightness adjustment while excluding the reference face. Neither
source specifies the ranking statistic, confidence model or ambiguity band.

This UI exposes the independently authored full-source robust natural-log
linear-sRGB luminance measurement in [REFERENCE-CHOICE](REFERENCE-CHOICE.md).
It labels the result as the brightest reliably measured **retained face**, not
the globally brightest person in the photograph, a learned-AI selection, a
complexion score, demographic inference or proprietary metric equivalence.
The native fitter and existing skin support are reused, not counted as a new AI
algorithm. This source slice does not certify the complete external feature.

`census_complete: false` means undetected faces cannot be ruled out. It does not
mean a complete set of retained candidate measurements is unusable. A separated
measurement can be displayed as a suggestion, but the user must explicitly
choose it. Missing measurements in the retained enabled set, a detector-limit
hit, too few enabled faces or a near tie block a unique automatic proposal.
The UI shows those reasons and still permits an explicit reliably measured
manual reference. IDs order tied rows deterministically; they cannot choose a
winner. The approximately 2% band is a local engineering rule, not a perceptual
threshold, probability, validated quality result or confidence interval.

## Modules and integration API

- `ui/src/skinReferenceChoice/model.ts`: isolated DTOs, bounded JSON/schema
  admission, exact request/report matching, deterministic ranking consistency,
  read-envelope validation and current-view fencing.
- `reviewGuard.ts`: `createSkinReferenceChoiceGuard()` exposes
  `prepare(command, view)`, `validate(command, result, currentViewGetter)`,
  `complete(command)` and `update(view)`. `isSkinReferenceChoiceRead(command)`
  identifies only this read. It is installed alongside existing family guards
  inside the sole people owner, never a request queue or transport.
- `SkinReferenceChoicePanel.tsx`: embedded below each existing family catalog's
  actual immutable source PNG. Props are `people`, `family`, `catalog`,
  `sourceSeen`, `available`, `blocked`, optional `lockedReference`, and
  `onReferenceChosen(FaceRef)`. There is no second image or regenerated source.
- Both existing face/body panels receive `choiceAvailable: boolean` from the
  `skin_reference_choice_protocol === 1` capability and embed the component.
- `SkinReferenceChoiceReceipt` is `{command: PeopleAction; result: PeopleResult}`
  because the existing owner holds the queue. The new typed `ChoiceCommand`
  narrows only when `commandMatches` succeeds. The owner publishes
  `lastSkinReferenceChoiceResult` only after guard validation and
  `receiptCurrent(command, result, currentView)`.

The guard observes the **existing** face/body catalog read, validates the
catalog and SHA-256 PNG bytes, and retains the exact family/source receipt.
No separate catalog request, graph, scheduler, publication path, history stack,
retry or source conversion is added. Original decoded-dimension and visible
presentation checking remains in each panel's `ReviewedImage` and `sourceSeen`.
Both measurement requests and reference-choice callbacks require that signal,
current visibility, current bindings, available capability and an idle owner.
Image presentation is not consent to edit.

Missing shared routing, missing receipt state or a missing protocol capability
is explicitly unavailable. The selected catalog's independent native solver
availability and reason are also shown: protocol presence is not installed
solver capability. No invented result or other-operation fallback is used.
Existing neutral clear and manual-reference flows remain separate.

## Exact wire and ownership

The only new action is `skin_reference_choice`, with the existing current-photo
people envelope. Its target is exactly
`{scope: 'all_people', target_id: assetSHA, face_ref: null}` regardless of the
editing cursor. Its payload is exactly
`{family: 'face' | 'body', source_review_sha256, manual_reference?: FaceRef | null}`.
Omitted `manual_reference` and explicit `null` remain different wire requests.

The outer result must echo the complete captured command minus `request_id`,
including document epoch/revision, graph revision, association revision, target
and exact payload. The inner report separately echoes the exact payload.
Successful canonical engine receipts include `event: 'people_result'`,
`created_id: null`, `batch_id: null`, `frame_emitted: false` and `error: null`.
Compact native refusals can omit those transport fields but must retain exact
identity, `success: false`, a diagnostic and known no-write outcome. Unknown
outcomes, wrong echoes, non-null created/batch IDs, frames, document updates,
extra authority fields or payload-bearing failures are rejected. A released
read must omit its payload; it invalidates the retained catalog, not authorize
a replacement or automatic retry.

The report preserves `source_pixels_sha256`, `graph_sha256`, `analysis_sha256`,
`body_bank_sha256`, `document_snapshot_sha256`, `source_review_sha256`,
`source_image_sha256`, `proposal_sha256` and `report_sha256`. Each measured
candidate preserves exact `FaceRef`, current evidence, landmark/support hashes,
semantic observation dimensions and original source window. No raster support,
RGB, landmarks, fit, recipe, consent token or apply authority crosses this API.

The host authenticates the actual source, analysis bank, graph, associations,
repair/render/context snapshot and catalog before and after measurement.
The UI checks digest shape and their exact binding to the retained report and
catalog; it does **not** pretend to independently reconstruct the engine's
Python fingerprints from a partial public view or JS JSON serialization.
Current document/graph/association revisions and exact catalog replacement
invalidate the UI proof. The subsequent existing preview/consent transaction
must revalidate its own source and current full render before any mutation.

The outer operation is the selected family operation. Even for body use, the
nested measured proposal operation remains `lnx.skin_reference_match.v1`, because
the measurement is of face skin. Its native measurement encoding is
`encoded-working-srgb-d65-sdr`, not the separate FullSource storage descriptor.
Original sources retain 8/16-bit provenance; creative sources retain float32
provenance. Measurements use the complete immutable source, never the display
PNG or edited canvas. Source windows are row/column/height/width, with a
16-million-pixel self-ROI ceiling reflecting the native combined 32-million
sample ceiling.

Native reliability bounds retain the actual admitted floating-point tolerance:
sample count, weight and effective count are at least 64; upper count roundoff
is `max(1e-7, count * 1e-6)`; retained weight is between 0.5 and `1 + 1e-6`;
initial log-luminance MAD is at most `0.50 + 1e-12`. Diagnostics are never clipped
or rewritten to satisfy an exact-arithmetic presentation assumption.

Memory disclosure has six exact fields: resident input, verification workspace,
total budget, capture budget, measurement budget and estimated peak bytes.
The reserved verification workspace remains charged through measurement and
final source verification. UI admission checks the report's phase budget and
peak relationships without claiming an OOM guarantee or benchmark.
The measurement allowance is the actual historical budget passed to the helper,
not a value retroactively shrunk after final resident/reservation accounting.
Admission requires each historical allowance to be positive and no greater than
total budget, helper-admitted bytes within the measurement allowance, and final
resident plus verification reserve plus helper-admitted work no greater than the
reported peak, itself no greater than total budget. Live headroom can recover
between phases, so measurement allowance may exceed capture allowance. The UI
does not charge the entire historical allowance again against enlarged final
resident buffers or silently rewrite either recorded phase allowance.

## Explicit selection, not application

Receipt arrival only displays measurements. It does not initialize the manual
selector, update the parent reference, choose a target, tick an ownership box,
request a preview, load before/after images, confirm, retain support or render.
There is no selection callback in an effect or receipt handler.

The user can explicitly choose the suggested face, choose another measured
face in the manual selector, or request remeasurement with that exact manual
reference. Even a successful manual-remeasurement receipt does not invoke the
selection callback. Each user selection changes only the parent reference
input and invalidates old ownership, consent, candidate images and ACK.
The face panel also removes the newly selected reference from its target list.
The body panel retains its existing common-reference lock and independently
reviewed body ownership/mask; donor selection cannot grant body permission or
erase that lock. Body targets can be the donor's own body where the independent
body operation permits it; the donor face itself remains protected.

Source changes, document/analysis/association changes, catalog replacement,
capability removal and unmount discard applicable drafts. Hidden tabs clear
manual-selection presentation and the existing panels clear source/ACK signals.
Double-clicks cannot create another command while the captured request or sole
owner is pending. Uncertain requests remain query-only in the existing owner.

## Authored acceptance, all UNRUN

`fixtures.unrun.test.ts` defines a tiny synthetic 16×16 PNG and metadata only.
It is not a face photo, inference output, brightness benchmark or quality claim.
`model.unrun.test.ts` and `reviewGuard.unrun.test.ts` author:

- Actual engine-shaped success, compact native refusal, exact complete echo,
  omitted/null distinction, release semantics and foreign/late request IDs.
- Both family operations, body outer/face inner distinction, source/epoch/
  document/analysis/association changes and complete source-image identity.
- Complete retained candidates, duplicate/omitted/reordered faces, stale refs,
  wrong evidence/support/semantic ownership, source windows and actual native
  floating-point admission tolerances without clipping diagnostics.
- Near ties, missing enabled measurements, explicit override, no fabricated
  winner, no global census claim and no hidden RGB/fit/authority payloads.
- Catalog PNG byte failures, stale catalog completion, wrong-family borrowing,
  retained uncertain captures and released reads requiring a new catalog.
- Verification memory reserve and impossible admitted peak/budget relationships.

Still requiring separately authorized browser/integration execution:

1. Both original family catalog PNGs decode and show actual numbered people;
   hidden, unloaded, broken or offscreen images do not enable measurement.
2. Suggestion receipt never changes a reference, target, consent or image ACK;
   only an explicit click updates the reference and resets old review.
3. Manual override, exact/near ties, missing candidates, disabled veto faces,
   detector limit, global census warning and body common-reference lock behave
   as labeled. All reference faces remain excluded after final mixed rendering.
4. Rapid repeat clicks, unrelated pending requests, uncertain outcomes,
   catalog rereads, document switches, Back/Forward, tab hiding, unmount and
   capability loss never permit stale callbacks or a second queue.
5. Selected reference flows through the already-owned explicit target/body
   review and complete before/after confirmation. No proposal flag substitutes
   for actual rendered image load, user consent or native mutation proof.
6. Missing solver leaves dedicated unavailable messaging, never fake success;
   clear remains the existing neutral operation and no model is downloaded.

No executed result or production readiness follows from these authored cases.
