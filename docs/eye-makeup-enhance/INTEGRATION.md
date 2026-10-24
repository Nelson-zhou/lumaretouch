# Parent-only shared integration map

These new modules are complete source deliverables, but the parent owns all shared
registry, renderer, routing, native package, history and UI edits. Do not claim an
end-to-end feature until those integrations and authorized execution are verified.

## Registry and project

1. Import `eye_makeup_enhance_state` as `EYE_MAKEUP_ENHANCE` in people_algorithms;
   include OP, neutral/check, flattened defaults and materialization like existing
   dedicated source operations. Leaves are `/amount/linked`, `/amount/left`,
   `/amount/right` and similarly for `saturation`, `brightness`, `structure`.
2. Run `eye_makeup_enhance_project.validate_leaf` for every sparse operation leaf,
   including dormant photograph-wide rows; `validate_graph` verifies complete
   materialized nonconflicting recipes. Unknown source/mask/palette fields fail.
3. Register unique support kind `eye_makeup_enhance_visibility` in people_state
   local-asset descriptor validation and all support-kind enumerations. Add
   people_support_assets.check_store dispatch to `support.check_record`, and skip
   it in generic facial recovery rasterization. Call `support.validate_project`
   (or `project.validate_project`) for current and historical persisted records.
   Include it in creative-derived same-source support validation and invalidation.
4. `project.require_transition(engine,before,candidate,row=None)` is required on
   all affected graph changes, scalar edits, ownership transfers and history paths
   not already guarded by an exact-source owner. It rejects multiple same-source
   documents; no private alias authority exists for this family. Generic portable
   presets may transport scalar intent only and must independently require target
   support. Do not copy reviews or piggyback existing cosmetic consent.

## Renderer, memory and native

5. Pass canonical support bank as a distinct `eye_makeup_enhance_assets` port into
   common source runtime, including original/derived, parked/reopened targets and
   full-source export. Resolve through `support.resolve(state,bank,face_ref)`.
6. Call `layer.prepare(face_ref,analysis,source,recipe,reviewed=record,
   byte_budget=remaining_budget,protected_boxes=every_other_same_source_retained_box,
   cancelled=callback)`. `source` is ORIGINAL effective-source float32 working-sRGB
   opaque SDR RGB, not repaired pixels or another stage's result. The caller owns
   exact original/derived source proof and alpha/HDR admission. Every other box
   includes disabled and unresolved retained faces. Genuine analysis includes
   face_ref, retained evidence, normalized 478x3 landmarks, face_skin observation,
   float32 face_skin and excluded on this render grid.
7. Prepare all active faces atomically; errors reject the requested render, never
   silently omit a requested side. Results are list[LocalEffect] with distinct
   stage `eye_makeup_enhance`, readonly float32 delta, exact source-coordinate ROI
   and facts. Add stage to ordered source effect and local-geometry support paths.
8. Both CPU and device composition must explicitly use
   `eye_makeup_enhance_composition.apply_np/apply_t`, which wrap
   people_source_vector's common scalar feasibility gain. Do NOT fall through to
   generic independent component clipping. Tile export only crops prepared delta.
   Add stage accounting/residency/recovery integration without re-solving per tile.
9. Package `liblrt_eye_makeup_enhance.so` from dedicated core build script when
   execution is authorized. No runtime build/download. `state.capability()` only
   tests symbols/ABI through `native.available`; it is not photographic readiness.
   Advertise `eye_makeup_enhance_protocol:1` only when all routes are installed.

## Current-photo reference, review, receipts and history

10. `host.ACTIONS` has `eye_makeup_enhance_reference` (read-only) and
    `eye_makeup_enhance_review` (graph mutation). `host.check_action` validates
    action/payload/target before dispatch. Existing canonical envelope, exact
    document/source/graph revisions, duplicate request keys, receipts and uncertain
    outcomes remain the sole owners. No second journal or request queue is added.
11. Read route: `host.reference(engine,state,target,payload,request_id=id)` returns
    `{kind,reference_proof}`. Store payload in canonical receipt. It caches only
    `engine._eye_makeup_enhance_reference={proof,preview,binding}`. Source crop is
    produced by `reference.acquire`, and must use actual effective-source model
    preview without running inference. Reference display is NOT effect acceptance.
12. Mutation route: `candidate,payload=host.stage_review(engine,state,target,payload)`.
    Payload input `{eyes,reference_proof}`. Each supplied side: makeup polygon,
    exclusions[], paired optional reference_a/reference_b polygons, plus four
    true flags (`visible_makeup`,`unoccluded`,`ownership_confirmed`,
    `globe_lashes_brows_excluded`) and explicit reference_confirmed. Existing
    opposite-side record is preserved. Host stages immutable bank bytes only;
    caller performs candidate preparation/publication and history atomically.
13. `host.report(engine,state,source,selected_id)` is installed as
    `people.eye_makeup_enhance` in doc_state. It includes full recipe, actual support
    status per side, reference proof/PNG only when binding still matches, native
    availability, facts and suspension. `support_available` is admission only,
    not a photographic result. Clear cached reference on document/owner teardown;
    stale cached entries cannot be reused because every report/review checks binding.
14. Echo exact envelope excluding request_id as `eye_makeup_enhance_request` on
    both success/failure/unknown canonical results. Parent UI workflow dispatches
    `model.echoMatches`, `referenceReceiptValid`, `reviewReceiptValid` and
    `releasedReferenceReceiptValid`. `host.bound_receipt_images(records)` retains
    one recent source PNG and expires old read display payloads without changing
    mutation outcomes. Released read must close its matching UI draft via absence
    of matching report/proof; never treat release as failed or replay automatically.

## UI

15. Add two PeopleAction literals, `PeopleResult.eye_makeup_enhance_request`, and
    `PeopleView.eye_makeup_enhance?:EyeMakeupEnhanceView|null` from this model.
    Install the reference/review validators in the existing workflow/reducer.
16. Mount `EyeMakeupEnhanceControl` with `{people,capability,blocked,faceOk,faceWhy,
    note,Slider}` in the original-eye-makeup section, not iris/eyeliner/eye-light.
    It already contains `EyeMakeupEnhanceSupportEditor`, source proof validation,
    actual PNG canvas, keyboard point entry, explicit exclusions, side selection,
    optional paired clean references, explicit consent and guarded submit callbacks.
    Do not recreate a separate support editor or copy an existing tool's consent.
17. Current UI requires an exact selected face target. Each control's linked flag
    and sides are independent. Numeric text starts blank; relink submits an
    explicit common chosen value. Neutral recovery can bypass absent core/support
    but never stale document or uncertain request fences. Show engine refusals.

## Verification handoff

All runtime/build/numerical/interaction checks remain UNRUN. Authored source
fixtures: core/tests.rs, ui/model.unrun.test.ts,
fixtures/eye_makeup_enhance_contract_unrun.py and fixtures/acceptance-unrun.json.
Run only when execution is separately authorized. Neither helper syntax checks
nor inherited feature tests establish this operation's photographic acceptance.
