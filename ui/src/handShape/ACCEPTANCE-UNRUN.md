# Hand shape UI/native source integration — AUTHORED, UNRUN

PC-46608:3 is a separate geometry panel, not hand tone or vein correction.
All controls/ranges/transition sizes are original local policy. One independently
reviewed hand per document; no BodyRef, 33-point pose or face prerequisite.

## Source-only checks performed

Read source/contracts; `git diff --check -- ui` (whitespace only). No builds,
typechecks, unit tests, product imports, model execution or image QA performed.
Native fixture functions below `hand_shape_api.rs::tests_unrun` are authored,
not execution evidence.

## Required external acceptance

- Standalone hand photo: capture immutable source; four-point palm/finger/joint
  region; two-point protection box; explicit per-role checks; adjust separate
  signed controls; render complete before/after plus authoritative source overlay;
  load all images; acknowledge and confirm. Undo/redo, virtual copy, save/reopen
  and original-size tiled export must preserve canonical source and geometry.
- Display geometry: normalized `x*(width-1), y*(height-1)` source coordinates,
  true source aspect, ellipse longitudinal half-axis and max measured transverse
  width ×1.8. Negative/positive swaps and numeric point correction work. Cropped,
  tiny, asymmetric, protected or conflicting supports reject rather than clipping.
- In-progress four-click/two-click work prevents confirmation. Cancel/delete/edit,
  slider change, proposal selection, reference change, source/history change all
  invalidate the old proof. A newly selected proposal never silently fills regions.
- Optional model unavailable explicitly displays manual-support mode. Actual
  21-point proposals are untrusted visual hints, including out-of-frame points;
  no fabricated visibility, hidden anatomy, identity or demographic template.
  Empty proposal result is not AI success. Handedness is not ownership.
- PNG signature, dimensions and SHA-256 must match every displayed proof.
  Full before/after and source-coordinate overlay are separate, clear labels.
- Review/preview/propose are native read-only; confirm/clear are existing document
  edits. Exact request, source, document revision, candidate hash and native epoch
  are fenced. Changed candidate or old process receipt must not clear recovery.
- Double-click, timeout, interrupted response and engine restart: query only the
  original request; never automatically replay an uncertain mutation. Receipt
  validation failure leaves the request guarded. Existing global edit gate and
  sibling hand-tone/vein/fabric panels remain blocked during uncertainty.
- All model installation, runtime resource limits, mathematical properties,
  between-grid behavior, real-photo naturalness and performance remain UNRUN.

## Owned integration files

New `ui/src/handShape/{model.ts,index.ts,useHandShapePort.ts,
HandShapePanel.tsx,HandShapeSupportEditor.tsx,ACCEPTANCE-UNRUN.md}` and
`ui/src-tauri/src/hand_shape_api.rs`.
Shared UI: `App.tsx`, `native.ts`, `components/RetouchPanel.tsx`.
Shared native: `main.rs`, `engine.rs`, `native_dispatch.rs`, `receipt_host.rs`,
`project_recovery_fence.rs`.

The Python host supplies `hand_shape_protocol:1`, `doc.hand_shape` with
`protocol:1, revision:string, active:boolean, recipe_sha256`, and successful
publication payload `protocol:1, family:'hand_shape', active, candidate_sha256`.
No new history or image owner exists in the UI.

## Exact late-terminal reconciliation (AUTHORED, UNRUN)

Native transport-generated unknowns carry the full original event/protocol,
document/revision and request echo. Only `hand_shape` may reconcile a later exact
validated engine event in the same native epoch; mutations additionally require
the complete original recovery-fenced command still pending. Changed request,
changed epoch, removed fence, engine-issued unknown and previously known terminal
do not gain new authority. No command is resent. New fixtures specify these
conditions; they have not been executed. The transported `status` action is not
admitted; `hand_shape_status` only reads the existing native mailbox.
