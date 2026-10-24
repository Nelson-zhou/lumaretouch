# Shared integration contract

All checks below describe required shared wiring, not claimed executed acceptance. The family author owns only new family files; the shared integration owner performs shared-file changes.

## Portable state and registry

Register `lnx.facial_sculpt.v1` from facial_sculpt_state. Neutral is exactly `{version:1, highlight:0.0, shadow:0.0}`; only `/highlight` and `/shadow` accept finite native scalar numbers in [0,1]. Booleans, unknown fields and old recipe migration aliases are rejected. Defaults/leaves/recipes, parameter registry, project override validation and canonical transfer inventories must retain this exact independent meaning. Existing skin_gloss, skin_finish, geometry and historical recipes are unchanged.

Use facial_sculpt_project.validate_leaf(path,value) and validate_graph(state) at persistence and dormant all_people admission points. Call require_transition(engine,before,candidate,*,row=None) before every canonical publication that may alter this operation, support or its resolved target membership. It finds only operation-local changes, including dormant photograph-wide intent, rejects changed assets outside the exact current/effective row source and refuses unsupported source-identical aliases. Thus cross-photo person/group/preset/batch publication is unavailable in this slice; helper scope files do not grant that authority. Never borrow face-decoration/eye-bag alias authority. Reset remains possible without native availability, except when ownership/alias fences cannot safely authorize it.

Optional facial_sculpt_scope contains check_params, params_of, install, capture, require_target and owner_identity adapters. It transfers only strengths, requires each target's own support, and refuses generic creative-derived preset installation. Do not expose this adapter until the complete existing transfer preflight/target-map owner is wired. It is not a second transaction engine.

## Independent source-owned review

Support KIND is `facial_sculpt_visibility`. Register it in the canonical people_support_assets validator and the dedicated-support skip list for generic recovery. Dispatch records to facial_sculpt_support.check_record. Include this family's source-specific bank in creative-derived support validation, load/save and project validation. No original support should be rebound to a derived source.

Canonical immutable record shape:

- version: 1.
- face_ref: asset_sha256, face_instance_id, analysis_revision.
- source: sha256, width, height (2–1,000,000).
- row: target=`facial_sculpt_visibility`, landmark_digest, region.
- region: recipe plus visible=true, unoccluded=true, ownership_confirmed=true.
- recipe: canonical source-normalized local-mask stack, brush add/subtract only, effective add required.

retain(state,assets,face_ref,region) returns candidate graph and append-only bank; it does not publish. resolve validates digest, owner, source size, true backend and retained landmark digest. raster rebuilds review vectors at the actual grid; source masks are not enlarged from old preview rasters. validate_project recursively validates face pointers against project people_support_assets, including historical graphs.

Host actions:

- facial_sculpt_reference, payload `{}`.
- facial_sculpt_review, payload `{region, reference_proof}`.
- Both require the current explicitly selected face target, not a group/person/all_people target.
- Proof exact keys: source, face_ref, landmark_digest, preview_sha256, reference_request_id. IDs use canonical People.token. No helper authority outside the canonical receipt owner.
- reference(engine,state,target,payload,*,request_id) stores one runtime proof and verified whole-effective-source PNG, returning `{kind:'facial_sculpt_reference',reference_proof}`.
- stage_review(engine,state,target,payload) rechecks the exact display proof/binding, stages the canonical support bank and returns `(candidate,{kind:'facial_sculpt_review',reference_proof,support_sha256})`.
- Review bank append is private/append-only; canonical graph publication/history owns the visible pointer. On failure, do not publish candidate pointers; unrelated stages and owner history must remain intact.
- bound_receipt_images(records) retains only the newest reference image; old terminal identity/outcome remains queryable but released display bytes cannot authorize review.

Wire actions in protocol allowlists, people commands, command binding checks, exact request echo `facial_sculpt_request`, cached terminal receipts, native request/report/receipt validation and UI workflow terminal classifiers. Reference is read-only. Review uses the existing complete prepare/publish transaction and canonical one-step history. Epoch/source/face/revision changes expire proof. An uncertain outcome is queried by original ID, never resent.

Report = report(engine,state,source,selected_id). Exact keys: recipe, facts, source, face_ref, landmark_digest, reviewed, support_sha256, source_preview, reference_proof, native_available, support_available, support_reason, suspended, alias_required, alias_reason. The last two are refusal diagnostics ONLY, not alias review capability. facts is empty when no prepared effect. Native availability means ABI loading only; support_available is admission only, not numeric/photo success.

## Original and derived numerical prepare

facial_sculpt_layer.prepare(face_ref,analysis,source,recipe,*,byte_budget,reviewed,protected_boxes=(),cancelled=None) returns ONE LocalEffect or None when neutral. It does not return a list.

- Source is frozen unsculpted working-sRGB-D65 float32 SDR RGB on the actual preparation grid, not RGB8 preview bytes. Use the same authenticated effective-source path for original and creative-derived photos; the latter never reads the original file behind its derived source.
- Analysis is the corresponding original/derived canonical face record with real 478-point landmarks and explicit face_skin observation. Verify canonical graph/source identity before entry.
- reviewed is facial_sculpt_support.raster(state,actual_support_bank,face_ref,source.shape[:2]). Pass the actual source's bank, not an assumed global/original bank.
- protected_boxes is every OTHER same-source retained face box, including disabled, unresolved or unsupported neighbors. Never only the enabled render list.
- Include all fields/analysis/records in aggregate memory admission and resident accounting.
- Preserve the immutable HW log_gain through prepared records, original preview, derived preview, full candidate prepare and export. The field's window is in full-source coordinates.

Add stage `facial_sculpt` to the ordered shared source pipeline after skin colour/finish/gloss and before cosmetic overlays (one consistent explicit position on CPU and tensor paths). Never send its field through generic RGB-delta aggregation or default channel clipping.

- CPU: facial_sculpt_composition.apply_records_np(current,records,recovery=None) returns `(output,facts)`.
- Tensor: apply_records_t(pixels,records,recovery=None,*,source_shape,origin=(0,0)) returns NCHW pixels. source_shape is full `(height,width)`; origin is exact `(y,x)` for the current tile.
- Pointwise helpers apply_np(current,HW_gain), apply_t(current,N1HW_gain) do not estimate structure.
- Generic recovery records for this stage are rejected. Do not register facial_sculpt as an interchangeable makeup/facial-recovery target.

## Native ABI and packaging

Original zero-dependency crate core/facial_sculpt, library lrt_facial_sculpt. Native filename engine/src/lumaretouch_engine/bin/liblrt_facial_sculpt.so. Dedicated packaging/build-facial-sculpt.sh is AUTHORED, NOT RUN. Shared packaging must explicitly stage it only after an authorized build. capability returns protocol=1 and available only after the exact ABI/symbol is loaded.

ABI: uint32 lrt_facial_sculpt_abi() == 1.

field_v1 arguments in order: source RGB pointer and float count, support HW pointer/count, target HW pointer/count, width, height, highlight, shadow, radius, output HW pointer/count, cancellation function/context. Counts are floats, not bytes. Output aliases no input. Source/support/target are validated finite [0,1], target<=support; source is RGB only. Status 0 success; 1 ABI; 2 settings; 3 pixels; 4 cancellation; 5 resources; 6 contained Rust panic. Foreign invalid pointers cannot be made safe by bounds checks.

## UI integration

FacialSculptPanel({people,capability,blocked,faceOk,faceWhy,note?,control?}). control='highlight' maps only exact 高光立体 leaf; control='shadow' maps only exact 阴影立体 leaf; omitted displays both. It reuses PeopleOwner patch/submitCaptured/check, not a private mutation or undo store.

PeopleView gains optional facial_sculpt:FacialSculptView. Ready caps gain facial_sculpt_protocol/available/reason. PeopleAction gains two names, PeopleResult gains exact facial_sculpt_request echo. model.ts exports check, patch, access, command, referenceCurrent, echoMatches, referenceReceiptValid, reviewReceiptValid, releasedReferenceReceiptValid and verifiedImage. Incorporate all terminal predicates in the current receipt workflow; do not accept a generic success without the family proof.

Numeric input never treats blank as zero. Individual-face sliders may use that face's resolved scalar; shared scopes use only an explicit override or fresh manual input, never the selected face's inherited value. A reset sends only that scalar zero, not borrowed parameters. Source review uses a genuinely decoded, digest-checked full-frame reference, normalized painting and three independent confirmations. Pending/uncertain actions, source or owner replacement, closing/reopening and stale callbacks fail closed. Closed review does not cancel a request already submitted.
