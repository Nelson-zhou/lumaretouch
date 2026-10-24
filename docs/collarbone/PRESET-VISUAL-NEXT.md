# Current-photo preset visual review: design record

Source inspection only, 2026-10-24. The plan below is now source-authored in
[PRESET-VISUAL-CONTRACT.md](PRESET-VISUAL-CONTRACT.md), not runtime-accepted
functionality. The collarbone batch and persistent-cohort visual proofs do not
authorize current-photo preset application through another controller.

## Why the existing image helper is not sufficient alone

`collarbone_transfer_review.prepare` currently renders two explicitly supplied
people graphs with the same non-people row state. A preset can combine collarbone
with exposure, crop, other portrait operations and other supported modules.
`people_scope.replay_preset` derives changed portrait leaves, validates the
actual selected person and coexistence rules, commits a candidate people graph,
and then replays the rest of the state. Merely replacing collarbone in a preview
graph would omit other selected effects; calling replay to obtain a preview
would mutate real ownership/history and is not an acceptable preflight.

## Coherent next implementation

1. Extract a non-mutating plan from the existing `people_scope.replay_preset`
   preparation, sharing its actual target choice, changed-leaf detection,
   coexistence checks and strict-local semantics with actual replay. Return the
   exact before/candidate graph and complete candidate non-people state. Keep
   legacy no-people and unchanged paths explicit. Preserve old recipe appearance,
   existing owner commit/rollback and all validation; do not duplicate a second
   partial portrait planner or simulate application on the live owner.
2. Add exact full-source preset preparation/verification ports through
   `workflow_ports.PresetPorts`. Bind current logical document and load identity,
   source/context/selected FaceRef, target-local coverage, before and final
   candidate state/graph, and preset content. Preview both complete render paths,
   including mixed modules. Original/derived support must follow the genuine
   effective source contract, not silently relax the existing derived refusal.
3. Extend `local_grade_preset_review.PresetReviews` with compact collarbone visual
   records and an independently scoped paged cache lifecycle. Reuse immutable
   byte storage primitives, but do not let a batch token authorize a preset.
   Frozen preset identity, target row object and revision must survive prepare,
   verify, apply and post-render verification. Both zero reset and unchanged
   selected active operations need truthful target review.
4. Extend preset native/UI request, preflight, image retrieval and apply receipt
   validators. Use actual loaded before/after images and a target-specific
   acknowledgment under the preset token, not a generic confirmation. A complete
   read-only preflight cannot acquire a mutation lock; an uncertain apply remains
   query-only and must retain its exact token/ack identity.
5. Preserve `preset_transaction.apply_with_rollback` and dispatcher-owned history.
   Final application and rollback checks must compare the actual resolved graph,
   not temporary `_collarbone_preset_requested` flags alone. Retain old recipes
   and explicitly report unsupported mixed/derived paths rather than discard any
   selected effect. Do not enable UI until backend/native/history paths agree.
6. Author UNRUN fixtures for mixed portrait/non-portrait presets, current source
   changes, source/load-ID mismatch, wrong target FaceRef, active/zero recipes,
   retained support drift, duplicate-source logical owners, missing/corrupt
   paged images, wrong ack/token, failure after graph commit, rollback and exact
   saved recipe parity. Real acceptance needs local execution separately.

No new algorithm, model, demographic inference or AI 3D detector is implied.
The exact handbook requirement remains partial and all new runtime/quality
acceptance remains UNRUN.
