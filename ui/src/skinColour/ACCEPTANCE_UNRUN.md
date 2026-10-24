# Face-skin temperature and tint: authored, acceptance UNRUN

This bounded slice adds exactly two canonical scalar UI controls. It does not complete the skin family, body skin, AI whitening, skin unification, or segmentation/photographic acceptance.

The source-only fixtures in `model.unrun.test.ts` and `wiring.unrun.test.ts` have not been imported or executed. No application, build, type check, inference, model download, or numerical/photo test has been run for this slice.

## Manual verification still required

- With a real measured face and matching source-owned semantic skin, verify cool/warm and green/magenta directions independently and combined, including neutral pixel identity and unchanged protected anatomy/non-skin regions.
- Compare bright/dark skin, gradients, high saturation, glasses, occlusion, multiple faces and boundary detail. Confirm that missing semantic evidence and synthetic/unmeasured anatomy refuse rather than using global colour keys.
- Confirm displayed values follow the selected face's resolved operation while the write target may be face, group, person or all people. Verify inherited values and explicit zero overrides stay distinct.
- During drag or numeric typing, change photograph, editing scope, selected face, analysis revision, history and resolved revision. Confirm stale drafts do not retarget writes.
- Exercise pending, uncertain receipts, export, other portrait owners, white balance, hair, and closed/in-flight/pending edit queue fences. Confirm retry queries the original request without resubmitting edits.
- Remove core support with non-neutral saved values. Confirm individual zero and atomic two-leaf zero controls remain reachable for a valid target, but never bypass pending/edit ownership. Verify retained non-neutral overrides in other scopes may still refuse rendering rather than being silently erased.
- Verify undo/redo and project replay use existing people history, do not create parallel history, and preserve all older skin labels and specification paths.

Engine readiness is only the loaded native-core fact. The UI does not certify source-specific anatomy or segmentation; the canonical engine preparation enforces those facts and its selected-face refusal is surfaced.

## Interaction limitation retained explicitly

The existing people owner supports same-context scalar coalescing, but the generic edit-queue DTO does not expose a matching ownership token. This slice conservatively blocks both controls while any people request or generic edit queue is pending. Consequently, continuous dragging may pause on its first submitted change until the authoritative receipt arrives; there is no claim of uninterrupted image preview. No new gesture/release owner or bypass of another owner's queue was introduced. Existing numeric-field commits and explicit zero controls remain available when the fences clear. Smooth cross-owner gesture behavior still requires review and runtime verification.
