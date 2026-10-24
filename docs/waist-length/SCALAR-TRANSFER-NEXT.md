# Remaining bounded waist transfer route

Requirement remains LNX-REF-PC-32473-C-5d33f285bb, PARTIAL / UNRUN. This is a
remaining implementation map, not a declaration that preset/batch is connected.

## Allowed transferable data

Only `{version:1, amount}`. Reject additional points, support assets, BodyRefs,
FaceRefs, model outputs, source provenance, region masks and ownership flags.
Target evidence must already exist and belong to the target's current source.
A future frozen receipt may carry target proof for review; that proof is not a
portable preset and must never authorize a different target.

## Suggested bounded first route

Use the existing torso frozen-ledger pattern, not a second batch history owner:

1. Select exactly one enabled target body, initially refusing ambiguous multi-body
   targets. Validate its explicit four waist markers and waist-specific support
   review against the current target source, actual pose and own-face association.
2. Apply the scalar to a frozen copy only. Run full canonical candidate rendering
   for both target before and candidate after, including all current unrelated
   effects and body operations. Do not render just a synthetic waist diagram.
3. Freeze exact document/row identity, source proof, revision, complete body bank,
   support/review, current face dependency and complete people-context hash.
4. Verify and decode bounded before/after images in the UI. Require explicit
   target-local acknowledgment, retain ordered acknowledgments with token and
   request identity through claim/replay/unknown outcomes, and compare terminal
   echoes to the submitted proof.
5. Use existing target replay and undo ledger. Guard both forward and rollback
   before any write with exact active row, document, path, revision and source.
   Never install old state into a switched target. Unknown results are query-only.
6. Scoped undo changes only the target waist scalar while retaining immutable
   support, own-face linkage, observations and unrelated operations. Changed
   dependencies conflict; monotonic bank revision alone must not break undo.
7. Keep waist exclusive from mixed scopes until a composed review truly covers
   them. Whole-bank or people inheritance must not bypass manual waist review.

## Existing ports to adapt, not silently enable

`scope.py` / dedicated waist scope, `optics_auto_scope.before_params`, frozen
`batch_preflight` and `batch_sync`, `batch_group_history`, dedicated candidate
review, `local_grade_preset_review` / `preset_controller` / `workflow_ports`, native
preset/batch protocol and receipt validation, UI scope selection and explicit
visual acknowledgment. The new source operation remains absent from these
portable scope registrations until all these paths are coherent.

Source-only fixtures should cover original and derived targets, different source
sizes, absent/stale markers, unrelated body edits, missing current own-face
association, invalid image hashes/decode, changed row/revision, unknown receipt,
rollback refusal and exact scoped group undo/redo. All actual behavior and quality
remain UNRUN until an authorized test environment executes them.
