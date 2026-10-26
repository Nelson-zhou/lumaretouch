# S3 / FORMAT-001 — JPEG quality version persistence

Status: source implementation only; fixtures AUTHORED / UNRUN.

## Narrow change

- `export_destination_runtime.decorate`: when synthesizing the single ordinary
  Original output receipt, copy `quality_mapping_version` if and only if reported
  in the writer result. Explicit null remains null; absent remains absent. No
  codec, quality value, or mapping version is inferred from the frozen plan.
- `server.Engine._task_item_locked`: add the field to the existing conditional
  receipt selection shared by success, skip, and failure outcomes. This one-line
  integration was applied by the concurrent server owner.
- Existing variant receipts and retry retention remain unchanged. Existing
  quality scale `lrt.quality.v1` and writer behavior remain unchanged.

## Source chain inspected

1. Ordinary writer returns the actual `encoder_quality` and mapping version;
   target-size writer similarly records its selected encoder quality.
2. Server worker copies those reported facts to the per-image export result
   emitted in `export_done`. Existing direct-copy receipt behavior is unchanged.
3. Original destination decoration now retains the version alongside quality in
   the synthesized ordinary output; existing output lists are not relabelled.
4. `_task_item_locked` passes the optional version to `tasks.item_result`, which
   retains detail fields on the task item for each outcome.
5. Project assembly stores `tasks.for_json`; project save/load serialize and
   retain the task records, and `_tasks_restore` calls `tasks.from_json`, which
   preserves item fields. No project schema migration or current-version default
   is needed, and no prior export is retrospectively labelled.

## Authored regression scope

`engine/tests/test_quality_mapping_persistence.py` covers three outcomes crossed
with reported/null/missing versions through the isolated real task-detail method
and actual project save/load calls, including nested output receipt retention.
Original adapter fixtures cover reported/missing codecs and versions and keeping
variant-specific quality facts. Plan doubles test propagation, not encoding.

Only static AST syntax inspection and source reading were performed. No runtime,
test execution, build, typecheck, project import, inference, install, download,
commit, or push was performed by this package owner. Source closure is scoped to
the known field-loss boundaries, not runtime FORMAT-001 acceptance or product
approval of the quality scale. Real export/event/save/reopen comparison remains
unrun, including ordinary and target-size JPEG and Original multi-output retry.
