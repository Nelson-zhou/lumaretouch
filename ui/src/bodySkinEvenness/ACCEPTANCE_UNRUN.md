# Reviewed body skin chroma evenness: partial source implementation, acceptance UNRUN

## Exact scope and evidence

- Reference `LNX-REF-PC-32465-C-d5ac2d4606`; exact leaf `PC-32465|AI肤色统一（身体）`.
- Official guide https://www.pixcakeai.com/guide/32465, lines 211–213 supplied by the coordinating task, describes uneven colour across body regions. It does not establish a public algorithm, numeric calibration or equivalence. The visible local label is **身体色度均匀（手绘审核、自身参考）**.
- This is a manual-assisted, own-body chroma-evenness slice, not a learned AI model, automatic body-skin instance segmentation, body/face colour matching (`d8b09012a9`), shared cross-person colour matching or complete skin-family acceptance.
- Independent operation `lnx.body_skin_evenness.v1`, exactly `{version: 1, amount: 0..1}`. Display 0..100 is local product policy. Zero is neutral for this operation only.
- Current effective RGB source may be the original or an already returned composite. Reference chroma comes only from the same person's independently reviewed body support. The guarantee preserves input linear luminance at this operation's stage, not after subsequent effects. Makeup, coloured lighting, tan lines and natural pigment variation may be affected; no automatic intent, makeup or physical-lighting decomposition is claimed. RGB SDR only; nonzero amount does not prove visible change or accepted quality.

## Authority and first-use flow

- `body_skin_evenness_available` / `body_skin_evenness_reason` indicate dedicated core readiness, not proof that a target body is usable. `people.body_skin_evenness` reports only this operation's attached support and review validity.
- Face/person/group/all-people amount edits retain current source/document/state/association ownership and authoritative provenance checks. Selected effective value, its provenance and explicit shared intent are separate. Shared scopes without explicit values get a blank deliberate choice; no inherited selected-person value is copied into a shared target.
- Direct active scalar edits require the selected person's exact tagged attachment with `needs_review === false`, real enabled verified analysis, current owned target membership and valid readback. Engine admission must independently check every actual active target; the selected-person report cannot authorize others. Missing active support has no face-only, colour, finish or guessed-mask fallback.
- The review family is `body_skin_evenness`, operation `lnx.body_skin_evenness.v1`; engine support kind is `body_skin_evenness_visibility`. Actions use `body_skin_evenness_reference`, `body_skin_evenness_preview`, `body_skin_evenness_confirm`, and `body_skin_evenness_detach` through the existing people request owner.
- Review is face-owned and uses an explicitly chosen, already associated real `BodyRef`, points digest, newly painted source-normalized add/subtract strokes and separate visible/unoccluded/ownership confirmations. Neither the prior colour/finish masks nor their consent is reused.
- To avoid first-use deadlock, an explicit positive local candidate amount accompanies preview as `{review, amount}`. Blank/zero cannot create a candidate. No scalar command is sent before review. A tagged preview must echo the exact positive amount, source, face, body and vectors. Amount edits invalidate the preview, loaded-image approvals and acceptance.
- All three actual before/after/overlay images must load at their declared dimensions; unchanged draft and separate explicit review acceptance are required. Confirm sends only `{preview_id, reviewed: true}` and atomically commits the staged face-specific amount plus independent support. UI discloses that this writes a current-person override, never group/person/all defaults. Closing a draft does not cancel an already sent request; unknown outcomes query the original request, not resend.
- Existing colour and finish flows retain their old payload `{review}`, reference source, independent consent and displayed meanings. Legacy untagged colour DTOs remain accepted only as colour; tagged body or finish replies cannot authorize another family.

## Neutral recovery and interruption boundaries

- Standalone reset writes exactly this target's `/amount = 0` through the canonical people patch owner. It does not unset inheritance, remove the body review, reset the separate face-evenness/colour/finish effects, touch old smoothing, modify other scopes or erase history.
- Neutral recovery needs current ownership and idle/known request state, not body support, anatomy, valid readback or an available core. Other nonzero targets may still be refused by the engine and are not silently cleared.
- Detach requires a current owned face and authoritative effective amount zero. It removes only body-evenness support; inherited active values cannot be silently reset or restored. The host independently rejects nonneutral detach, while neutral stale-support removal remains possible.
- Pending, uncertain, export/engine ownership, hair, white balance, portrait competitors and closed/pending/in-flight edit queue fences remain active. Owner callback generation, mounted state, full source/target/member/authority/review bindings, local draft snapshots and a synchronous scalar submission latch prevent obsolete or repeated writes. Source-image readiness is fenced by current canvas context. Confirmed fast failure releases scalar latch through refreshed owner state.
- The existing people workflow remains the sole submission, receipt, refresh, history, replay, preview and export owner. No alternate renderer, transport, optimistic people graph or source evidence is created.

## Batch disclosure

- Frozen review field `body_skin_evenness_coverage` has `version: 1`, `support_transfer: 'none'` and one exact `face_ref` per target. A positive amount requires `reviewed-body-only` plus the target's retained review digest. Exact zero requires `neutral-no-effect` plus null digest; it does not claim reviewed support.
- UI validation rejects missing, duplicate, foreign or extra targets, copied geometry, face-only fallback, invalid digest, extra fields, unexpected body coverage on unrelated transfers, wrong scalar paths/domains, and borrowing colour/finish coverage. Mixed operations keep independent disclosures.
- Coverage is expanded visibly beside existing colour/finish coverage and states no mask, reference colour or identity transfer. Target refusal reasons remain owned and displayed by the existing preflight flow; one reviewed target does not make rejected targets admissible.

## Authored fixtures and verification status

- `model.unrun.test.ts`: exact recipe/leaf/capability; owned provenance and shared intent; membership, confirmed links, conflict/staleness; review-family independence; first-use review vs direct-active separation; neutral recovery; full invalidation and mutation-free helpers.
- `bodyReview.unrun.test.ts`: operation tags/actions, positive explicit amount, source/face/BodyRef/vector matching, loaded-render schema, distinct families and correlated receipts.
- `wiring.unrun.test.ts`: exact leaf, preserved neighbours/legacy, core/ownership/queue fences, atomic candidate flow, local amount invalidation, neutral-only detach, canonical owner and honest limitations.
- `../people/bodySkinEvennessCoverage.unrun.test.ts`: active/zero coverage domains, exact target set, rejected cross-family/fallback/copy attempts, mixed independent disclosures and visible rejection notice. Existing colour/finish source assertions were adjusted only for the additional expanded disclosure.

Only source reads, source edits and manual static inspection were performed for this UI slice. No application/test imports, test execution, build, typecheck, inference, download, image/numerical/photo evaluation, or Git writes were performed. The fixtures are **AUTHORED / UNRUN**, not passing-test evidence. Backend source authored by other slices is not UI runtime acceptance.

## Required later local acceptance

1. Typecheck/build and run these UNRUN fixtures with existing skinColour, skinFinish, skinEvenness, people transaction/batch/history, legacy smoothing, preview/export and source-editor regressions.
2. Exercise first review from zero, invalid/blank amount, amount changes before/after preview, positive independent atomic confirm, edits after confirmation, neutral reset, detach while inherited active, stale-body neutral detach, family switching, missing/incorrect tags, released payload and source/body/face changes.
3. Exercise face/person/group/all targets and shared members with missing, stale or foreign support. Verify refusal, no mask/reference copy, no face fallback, and independent own-source evidence for each actual active target.
4. Test fast failures, repeated pointer/keyboard events, rapid Apply/confirm/detach, unknown outcomes/query, Close/reopen, owner replacement, view unmount, queued competing edits, image-load failure and stale image callbacks. Confirm no stale draft can authorize a new person, operation or amount.
5. Validate actual RGB SDR body photos across skin tones, clothing, hair, occlusion, crops, touching/overlapping people, tan lines, makeup, coloured light, clipping, low-resolution and no-evidence cases. Measure own-stage luminance, boundaries, identity, unchanged outside support and tile/full-frame equivalence. A manual review is not segmentation or photograph-quality acceptance.
6. Verify ordinary preview/export/save/load/undo/redo and frozen batch digest revalidation across original and returned-composite sources. Check body and face-evenness stay independent and adjacent body/face matching remains unsupported by this slice.

No item above is marked passed; the leaf and skin family remain partial and unaccepted pending authorized local validation.
