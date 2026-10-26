# Automatic ID foreground initialization — source-only handoff

Status: implemented source, **not executed or locally accepted**. No tests,
typecheck, build, inference, product runtime, installs or model downloads ran.
No commits or publication were performed by this task.

## Product route

`id_initialize_foreground` is a normal fenced ID mutation using the existing
terminal receipt and history owner. It creates an **unreviewed** local-mask
operand, not an ID support binding and not a background application. Existing
source capture/overlay and add/subtract brush objects provide correction. The
user then selects the exact objects and independently confirms **subject** review
before the ordinary ID background apply/preview/export path consumes them.
Existing reviewed snapshots remain unchanged when a new proposal is created.

The new `automatic_foreground` operand is distinct from `semantic` and `prompted`.
Client edits cannot create it or alter its selection proof. Generic semantic/full
objects remain forbidden for ID support. Contact/all categories cannot consume
the new operand. Cross-photo transfer/presets reject it. Original-shadow's manual
operand whitelist remains unchanged and excludes it.

## Real producer and proof

The existing full-source decoder/ICC route reads bound RGB8/RGB16 input; a separate
long-edge <=512 RGB8 analysis copy is passed to the existing pinned MediaPipe
six-class inference implementation in a bounded disposable offline worker. The
proposal sums hair, body skin, face skin and clothes probabilities, **not** inverse
background; `others` is excluded. Alpha is quantized to uint8 and its exact bytes
are hashed. Receipt binds automatic origin, contract, actual model SHA, installed
MediaPipe version, actual input SHA, alpha SHA, analysis extent and original source
SHA/extent. Replay recomputes and matches this receipt; no raw client alpha is
trusted. Cached fields remain disposable and source/model guarded; full export
forces replay before resizing the bounded proposal to the actual output grid.

Bundled pin: `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`.
License evidence remains in `docs/model-licenses/models.json`, official model card
and archived MediaPipe Apache-2.0 notice. No new model or modified weights.
Existing PromptedJob process lifecycle is reused, not its SAM producer/schema.
This route does not require SAM and never invents clicked points or SAM provenance.

## Deliberate limits

- Original photos only. Derived/composite sources fail explicitly, never fall back
  to the old original. Existing prompted/manual derived workflow is unchanged.
- Whole-photo categories: count, person-instance selection and occlusion are
  unknown. Several people can contribute. Face detection is not invented.
- Soft bounded semantic proposal, not native-resolution hair matting, accessories,
  complete silhouette or official ID compliance. Enlarging it does not improve
  its model resolution. Independent visual review/correction remains required.
- No generative image changes; source RGB is untouched. Initialization rejects
  active nonzero object-bound grade edits to avoid widening an existing color edit.
- Existing ID full-field 32MP and decode/memory admission limits still apply.
- Missing or changed weights/runtime, source drift, malformed output, timeout or
  proof mismatch fail closed. There is no download or alternate-model fallback.

## Explicit owned manifest

Engine (`engine/src/lumaretouch_engine/`):
`automatic_foreground.py`, `automatic_foreground_worker.py`,
`creative_id_background_host.py`, `id_background_controller.py`,
`id_background_runtime.py`, `id_background_support.py`, `local_grade_layers.py`,
`local_grade_live_dependencies.py`, `local_grade_runtime.py`,
`local_mask_controller.py`, `local_mask_recipe.py`, `local_mask_state.py`,
`prompted_mask_resolver.py`.

UI: `ui/src/idBackground/IdBackgroundPanel.tsx`,
`ui/src/localMasks/LocalMaskPanel.tsx`, `ui/src/localMasks/model.ts`,
`ui/src/localMasks/transferModel.ts`, `ui/src-tauri/src/id_background_api.rs`.
Documentation: this file.

## Local acceptance still required (Qoder)

Exercise a real bundled-model original from initialization through source overlay,
brush add/subtract, independent subject review, background apply, undo/redo,
save/reopen, inspection and full export. Check repeat clicks/replayed request IDs,
document/revision changes, failed-worker rollback, missing/tampered weights,
forged/foreign receipts, malformed alpha, disabled operands, contact/all rejection,
derived rejection, independent old reviewed snapshots, and transfer rejection.
Compare source face pixels and output boundaries across RGB8/RGB16, ICC, hair,
accessories, multiple people and occlusion. Measure actual latency/memory and
quality; source inspection alone establishes none of these results.
