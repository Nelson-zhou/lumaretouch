# Light glow current-photo UI

Status: **AUTHORED / UNRUN**. No product process, test, build, typecheck, module import, model inference, download, or installation was performed for this UI work. Static source inspection is not runtime verification or proof that an entry is visible in the app.

## Requirement and primary reference

- Exact local requirement: `ui/src/spec/creative.json`, tool `211524`, “光影——发光”. This is independent of lens blur `165438`.
- Primary source inspected on 2026-10-25: [PixCake's light-glow guide](https://www.pixcakeai.com/guide/211524), dated 2026-09-17.
- The guide identifies black mist, white mist, and glow. Mist presets are 1/8, 1/4 (default), and 1/2; glow presets are weak (default), medium, and strong. It names strength, radius, threshold, exposure, scattering, and tint hue/saturation/lightness, plus a green affected-range display and application. The guide supports multiple selected photos.
- Neither the guide nor the local requirement establishes slider domains, numeric preset values, implementation equations, or equivalence to physical filters. The UI presents the controls and named levels but identifies all numeric calibration as local. It does not claim AI illuminated-surface detection or proprietary implementation parity.

## Owned source family

- `ui/src/lightGlow/model.ts`: exact versioned wire types, strict validators, scalar presets, capability and immutable-source identities.
- `imagery.ts`: canonical Base64, PNG signature/chunk structure/CRC, hash, size checks; affected-range images must use RGBA.
- `controller.ts`: App-lifetime source/review/write state, explicit human approval, local parameter undo/redo, per-mode drafts, uncertainty and refresh recovery.
- `useLightGlow.ts`: current-photo acquisition owner and read-only observation across panel visibility changes.
- `LightGlowWorkspace.tsx`, `LightGlowWorkspaceHost.tsx`, `lightGlow.css`: controls, complete comparison, actual native coverage overlay and explicit limitations.
- `workflow.unrun.test.ts`: synthetic contract fixtures, authored but not run. They are not a production fallback and are not exported by `index.ts`.

This family imports no lens-blur or expression-replacement implementation and claims no existing route. Native transport and App navigation are separately integrated. Do not register a capability as available merely because these files exist.

## Integration API

Create one stable, genuine `LightGlowPort` for the App lifetime. Call `useLightGlow(context, port, onChanged)` unconditionally, above the transient modal. Render `LightGlowWorkspaceHost` with the returned owner and explicit `open`, `onOpen`, and `onClose` callbacks. Opening or mounting never initiates capture, preview, model download, inference, or writes.

`LightGlowWorkspaceContext` consumes existing App facts:

- `sourceUid`, `loadId`, `engineKey`, `hostRevision` identify the host scope.
- `hostRevision` only invalidates UI work. It is never substituted for the native canonical document revision.
- `active`, `available`, `externalBusy`, and `queueBusy` gate explicit acquisition. `externalBusy` must exclude this module's own in-flight work.
- The native port must independently settle pending editor changes and validate current source/revision before read or apply admission. UI-only checks are not an authorization boundary.

`onChanged(receipt, command)` is a read-only authoritative refresh. For an applied receipt it must refresh the actual `result_document_id`, not assume the old `owner.document_id` was modified. A failed refresh leaves the confirmed result intact and exposes a refresh-only retry. Do not replay the application to repair a failed refresh.

The real port implements `refreshCapability`, `acquireCurrent`, `currentStatus`, `cancelCurrent`, `preview`, `submit`, `receipt`, `cancelReads`, `checkReads`, `pendingReads`, and `subscribe`. Optional `requestReconciliation` enables an explicit status read. It retains original transport requests outside the mounted panel. Preview resolves an inner `GlowReview`; submit/receipt resolve an inner `GlowReceipt`; current reads return the exact `light_glow_result` envelope. The parent transport uses distinct `light_glow` routes, never lens-blur routes.

## Source and review contract

- Protocol 1, operation `lnx.light_glow.v1`, ABI 1, math identity 65537.
- A source is an immutable full current edited capture, not the cropped viewport, an analysis thumbnail, original-file shortcut, or a guessed path.
- `GlowOwner` binds document ID, document epoch, canonical revision string and complete-source hash/dimensions/orientation.
- `source_evidence` retains capture version 3, original/people-graph/repair-stack hashes, canonical revision, native load ID, and capture token. These are native facts, never UI-generated proof.
- Current acquisition additionally fences the App engine/source/load/revision scope. A late result from a changed scope is discarded without starting another capture.
- The preview response must echo the exact request/session/owner/recipe and source evidence. The `before` hash must equal the retained context image. Before, after and coverage must have identical complete-frame display dimensions.
- Display PNGs are bounded to 1280 pixels per edge and 4 MiB each. Their hashes are distinct from canonical float-source and coverage-raster hashes. The latter identities alone identify the actual retained output and numeric coverage.
- PNG verification does not imply that a user has seen the images. Browser decode and natural-size checks are separate, followed by an explicit user checkbox. Missing or failed before/after/coverage images disable apply.

## Modes, presets, and history

Recipes contain only the version/operation/math discriminator, mode and numeric controls; there is no ambiguous stored preset name. Preset selection expands into these scalars. “Custom” is derived from exact equality. Switching modes restores that mode's session draft; first use selects 1/4 for either mist mode and weak for glow. The initial black-mist mode is a local UX choice, not a documented vendor initial-mode claim.

Local numeric domains: strength, threshold and scattering 0–1; integral source-pixel radius 0–512; exposure −4 to +4 EV; hue −180° to +180°; saturation and lightness −1 to +1. Domain violations are rejected rather than silently clamped. The scalar tables in `model.ts` match this module's core calibration, not vendor values.

Parameter changes invalidate prior review and human approval. The session retains up to 128 parameter undo/redo steps, independent from source-document history. Rendering and editing controls do not mutate the existing document. Strength zero must be exactly neutral even when other controls are nonzero. A neutral result is identified by the unchanged canonical source hash and still requires review before creating a distinct new image.

## Actual affected-range display

The native renderer computes coverage from the maximum absolute change in premultiplied RGB output versus input, normalized to 0–1. The adapter supplies a green RGBA diagnostic PNG with transparent unchanged pixels, sampled identically to the complete before/after images. The UI displays these actual bytes over the after image, without generating its own threshold selection, rectangle, silhouette, or bloom approximation.

This coverage is a result-change diagnostic, not an AI detected lighting surface, a source-selection mask, an editable paint mask, or confidence. The overlay never enters the returned image. RGB-only opaque illustrations are rejected as coverage overlays. The UI does not prove the relationship between the numeric coverage hash and PNG by recomputing the native renderer; that relationship is an adapter responsibility.

## Returns, cancellation, and uncertainty

Only `return_mode: 'new_image'` is accepted. Apply binds the native preview token, recipe hash, complete immutable result-source hash, numeric coverage hash, and all three display-image hashes. An applied receipt must belong to the same exact original command, identify a distinct new document, echo the correct original document and canonical result hash, and carry a valid canonical result revision.

Updating the original source is explicitly unsupported in this UI. No fake source-update button, reversed-grade operation, display-PNG writeback or fallback source ID exists. New-image creation must preserve the original file, source document, edit state, people graph, repair stack and history. Project persistence and exporting an image remain separate operations.

The controller retains the immutable original apply/cancel command before dispatch. Timeouts, transport errors, malformed receipts and pending receipts remain unknown or pending. They never enable resubmission, a different return mode, or cancellation of an already-entered uncertain apply. Only read-only reconciliation of that original command can resolve the outcome. Duplicate clicks cannot produce a second in-flight write.

Hiding/Escape only hides the panel. It revokes presentation approval but does not discard the source recipe, original request or receipt. Reopening requires image decode and explicit approval again. Source changes invalidate previews while retaining pending writes. Cancellation acceptance is not cancellation completion; only the matching terminal receipt authorizes the cancelled state.

## Explicit remaining limitations

- Current photo only. Multi-selection and batch propagation from the official guide are not claimed.
- The native core currently supports bounded SDR only. HDR, negative or unsupported values must be rejected without clipping or substituting the display PNG. This UI has no HDR conversion path.
- No claim of vendor numerical, optical, physical-refraction or AI-model equivalence.
- No original-source-update return, layer-stack return, mask painting, or project/export automation is implied.
- No production native result, screenshot, end-to-end rendering, packaging, typecheck, test or visual-visibility result was produced here.

## Authored verification scenarios

The UNRUN fixture file covers exact schemas/presets, source evidence and revision rejection, image integrity, RGBA coverage, separate decode/approval gates, per-mode drafts and local undo/redo, late/stale preview rejection, unknown-write preservation, wrong result identity rejection, single-flight cancellation, unsupported return modes, neutral-source identity and refresh-only retries.

Additional integration checks remain unrun: actual current capture including repairs/people/edit state, HDR rejection without source changes, each real mode at each preset, green coverage registration, both complete frames at portrait/landscape aspect ratios, keyboard focus and resizing, hidden-panel status observation, engine restart, load/revision change while capturing, cancel before/after native admission, and original history invariance after new-image creation. These are acceptance requirements, not passed checks.
