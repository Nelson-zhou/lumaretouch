# Eight-color HSL preset/batch scope

Status: implementation candidate, not yet executed or accepted. This closes a
transfer gap in the existing color operator; image-action eyedroppers remain
separate unfinished work in `action-eyedropper-plan.md`.

Requirement: product guide / AI package LNX-REF-PC-32455-C-3791959b40, and existing
module-scoped preset/batch requirements. Official reference:
https://www.pixcakeai.com/guide/32455 . Do not claim its proprietary pixel math.

## Contract and ownership

- `lnx.hsl.v1` owns `recipe`, an exact object with integer version 1, algorithm
  `legacy-hsv8-smoothstep-v1`, and 24 finite numeric bands, eight dh/ds/dl triples.
- Existing limits remain dh ±60 degrees and ds/dl ±100. Unknown metadata/keys,
  boolean/string numbers, nonfinite/overflow values and wrong lengths reject.
- This is the existing HSV/smoothstep implementation, despite the familiar HSL
  UI label. Pixel formulas are unchanged; a future true HSL algorithm needs a new
  identity, never silent reinterpretation of saved values.
- `hsl_recipe.py` owns transfer validation. `ops/hsl.py` retains vector pixel math.
  The document still has one `_hsl` tuple, not a second mutable recipe store.
- Legacy state padding/coercion is retained, but invalid HSL fails before live
  fields change. Missing legacy state is neutral. Transfer recipes require all 24.
- Scope/preset/frozen batch/undo use the same generic scope mapping. No independent
  HSL branch in the batch controller. Registry additions do not edit frozen P0.
- UI choices derive from actual engine capabilities, offer individual modules,
  and omit missing HSL on older engines, including from their labels. A remembered
  scope that becomes unavailable requires re-selection; it never broadens to all modules.

## Correctness repairs found while connecting the scope

Scoped preset save now accepts the `module_scope` key that native/UI already send.
Explicit empty scope rejects instead of silently saving every module. Omitted/null
scope retains its existing all-transferable default.

HSL installation errors no longer erase the layer and allow a misleading success.
Preset rendering uses `preset_transaction.py`: restore the previous state/frame
on failure; if rollback also fails, invalidate the pipeline and require reopening
the image. Successful preset receipts are only emitted after rendering succeeds.
Frozen batch also invalidates its live pipeline if both rendering and rollback fail,
without writing parked targets.

## Verification required

Strict envelopes/copies/ranges; old-state handling and pre-mutation rejection;
actual command-level scoped save/load; pixel identity through preset, one-step
undo/redo and project reopen; frozen source and out-of-scope undo preservation;
installation/render failure injection; capability-derived UI options; unchanged
full regression gates. Physical GUI/performance testing remains deferred, not
replaced by pure controller tests. Test outcomes must be recorded after execution.

## UI gap found during final inspection

The existing App preset-save handler has a name state but no reachable input that
sets it. It also does not pass the optional module scope. The new batch scope UI
is reachable; the protocol-level scoped preset save is implemented and tested by
the new candidates, but a usable scoped-preset save UI is still **open**. A dedicated
preset workflow must provide name/scope inputs and actual-result confirmation,
not clear inputs or announce success merely because a command was enqueued.
Do not mark the entire preset user journey complete from backend tests alone.
