# Target-scoped portrait save staging — source only, UNRUN

`workflow_preset_people_save.py` reuses `virtual_copy_people.save_project` on a
detached serialization view. It does not publish a graph, change live contexts,
save files, grant workflow approval, or replace the existing transaction owner.
The detached graph adapter exposes only `snapshot`, never `commit`.

## Integration contract

1. After the exact original imported target has been opened, but **before** its
   explicit preparation, retain `baseline = capture(engine, row, saved_project)`.
   Its target must have no retained faces, analysis run or all-person override.
   The source requires full managed-import SHA identity and must not be a copy.
2. Use the real preparation and normal preset owner. Freeze
   `expected_context = context(engine, row)` only at a point already proved by
   the handoff against its reviewed candidate. Reading a fresh context at save
   and calling that approval is not permitted. The graph must remain the one
   neutral, enabled, verified MediaPipe target face; legacy scalar skin strength
   does not create a retained graph override.
3. Existing `_scoped_project` first produces its usual codec-owned target row.
   Before its final migration check, call:

   ```python
   project = stage(engine, saved_project, project, row, baseline, expected_context)
   ```

4. The existing top-level comparison may exempt **only** the exported
   `PEOPLE_PROJECT_FIELDS` in addition to its current `docs`/`assets` exclusions
   **when** the retained preparation baseline exists and `stage` succeeds.
   Color-only paths retain their old strict comparison. Keep existing original
   assets, other-row, source-registration, lossless codec and migration checks.
5. Actual pinned-directory CAS/write/readback remains `workflow_preset_save`.
   Keep the normal handoff source/revision/owner proof before and after staging
   and throughout persistence. This helper reads source identity metadata only;
   it does not replace managed-file hashing or the lease's source-file proof.

## Scope guarantees

For shared original contexts, only this target asset's local face/analysis slice,
append-only landmark evidence and source cursor can change. All shared
person/group/link associations and every other asset's graph content remain
exact. Canonical revision counters may advance but never rewind. For private
original contexts, only the target row's `people_context` changes; shared
top-level portrait fields remain exact.

Fresh neutral skin preparation may not create or replace authored support or
hair evidence. Existing immutable landmark records cannot change or disappear.
The normal serializer retains all original unrelated documents and source
registrations, including private contexts. An unrelated unclassified import is
refused rather than silently classified while saving the selected target.

The helper does not widen support to edited targets, multiple faces, manual
faces, virtual copies, derived sources or portrait-effect graph writes. Its
baseline/context objects are internal session evidence, never a wire receipt.

## Status

The helper is not by itself an enabled skin workflow. Preparation, cancellation,
review/planner proof and application/save handoff wiring must all be coherent
as wired by the retained handoff; source integration is not runtime acceptance. Authored contracts in
`engine/tests/test_workflow_preset_people_save_unrun.py` are **UNRUN**. Source
inspection, Python AST parsing and whitespace checks do not demonstrate build,
runtime serialization, durability, rendering, device quality or performance.
