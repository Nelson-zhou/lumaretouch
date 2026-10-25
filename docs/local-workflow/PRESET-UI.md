# Explicit workflow preset handoff

Status: source implementation and authored acceptance fixtures only. All runtime, image-render, numerical, compilation, typecheck, integration and UI/browser acceptance is **UNRUN**. No photo was imported, edited, rendered, saved or exported in this implementation pass.

## Ownership and supported scope

The native serialized workflow host owns durable renderer request IDs and exact engine envelopes. The engine owns the current lease, target, review evidence and normal preset dispatch. The renderer cannot call an ordinary preset application from this workflow panel and does not substitute catalogue selection for authorization.

The real engine profile supplies `preset_catalogue`. The picker preserves content fingerprints, distinguishes supported recipes and disables unsupported complete presets. Initial support is the complete exposure/white-balance module subset only. Unsupported modules refuse the whole preset, not a reduced preset. Catalogue errors can have a null source filename. Initial native preset error policy is `stop` only.

## Handoff shape

Every preset execute/query receipt includes `handoff`, either null after definitive safe settlement or this exact bounded object:

- `version: 1`
- `operation_id`: current core pending operation ID, never an arbitrary UI ID
- `document_id`: stable retained document identity
- `preset_id`, `preset_sha256`
- `phase`: `awaiting_open`, `reviewing`, `authorized`, `awaiting_save`, `awaiting_return` or `unknown`
- `review`: null or exact `lrt.workflow-preset-review.v1` report
- `message`: bounded explanatory text

Native handoff validation binds it to the original PreflightPreset/ApplyPreset command and the exact preset/document identity. The run persists and exposes the validated handoff. The UI checks it again and clears all image/display/checkbox state whenever its exact review key changes. A restored old engine epoch remains readback-only and cannot authorize a new handoff.

## Explicit steps and journal ordering

Renderer writes use the existing `local_workflow_submit` command with `kind: review_step`, `run_id`, `operation_id`, `step` and `payload`. The original UI request and exact session-bound engine envelope are persisted before dispatch. Review steps are not read-only and participate in the original-request uncertainty fence.

1. `open_target`, empty payload: user chooses to load the exact retained target and prepare real before/after evidence. No preset application occurs.
2. `approve`, exact ACK payload: user must fetch, verify and actually display both images, then explicitly check the per-target box. This only retains review authorization. The core reads that authorization, journals its ApplyPreset intent, and only then dispatches the actual preset operation through the existing owner/history path.
3. `save_project`, empty payload: offered only after a verified actual application. It explicitly saves the exact project.
4. `return_target`, empty payload: explicitly restores the original target after verified save, permitting final PresetApplied settlement. Before approval, the same explicit button cancels the preset and returns safely; the workflow then follows its stop-only policy.

The legacy `open_review` action remains a read-only view. It never loads a target or grants authority. No timer, mount, image-load callback or bulk action sends an ACK. There is no “approve all” control.

## Image proof

`local_workflow_review_image` accepts `input` containing port version, run, current operation, review ID/hash, side, image SHA-256 and page. The host supplies the existing exact lease and calls read-only `workflow_owner.review_image`.

The outer engine response is `status: readback`, echoed `operation_id`, and `image`. Its image payload contains exact review/target/side identity, compact PNG metadata, page number, page size 65536, offset, page byte length, page SHA-256 and canonical base64 bytes. Each image is bounded to 4 MiB / 64 pages. Native validates every returned page against the current report and verifies page bytes. Renderer repeats the page checks, verifies the complete PNG SHA-256 and PNG dimensions, then requires both DOM images to report `complete` with matching natural dimensions before enabling the checkbox.

The ACK exact keys are `review_id`, `review_sha256`, `target` (`document_id`, `load_id`, decimal `revision`), `preset_id`, `preset_sha256`, `before_sha256`, `after_sha256`, and `accepted: true`. It cannot authorize another target, document load, revision, preset version or image pair. Display state and approval are not persisted across panel dismissal.

## Pause, uncertainty and settlement

Directory-source polling pauses while a preset command or handoff is retained. Original core-operation and original explicit-step readback continue. Stop is refused while a handoff is active; it must not drop a loaded, approved or half-saved target. A pre-approval cancel/return remains available only in safe phases. Unknown permits readback only. Release requires no retained handoff, no unresolved core operation and verified owner release.

Success/failure is not inferred from a timeout. Step success must echo its operation/step/session. A failure is definite only with `dispatch_rejected: true`; partial outcomes remain unknown. Querying a step uses its original request ID. The engine republishes the retained original step envelope and includes `step_result` in the readback; it never re-executes that step. A review-required preflight remains nonterminal until the real owner approval receipt arrives.

## Authored acceptance coverage (UNRUN)

- Exact handoff command/document/preset identity and unknown-phase refusal.
- Review-step writes distinct from read-only image and review reads.
- Review-required preflight is not terminal without approval.
- Unsupported whole presets, nullable catalogue filenames and stale catalogue identity.
- Wrong side/target/page/offset/hash/base64 and missing complete image metadata.
- Both images must be displayed with correct dimensions; one failed image or an unchecked box blocks approval.
- Stop cannot release a retained handoff; unknown cannot dispatch any new step.
- Stale target/report keys and panel dismissal revoke image/checkbox proof.

Final Tauri invocation registration for `local_workflow_review_image` is performed by the integration owner outside this module.
