# Explicit group save boundary (source only; acceptance UNRUN)

`portrait_preset_group_save.save(engine, rows, recheck)` is called only by the
serialized group owner, after the original group commit is fully proven. The
caller retains the original receipt, batch ledger, document revisions, exact
after recipes/history/source evidence and any Unknown outcome. The callback
must reject drift both before staging and at the existing CAS write boundary.

The adapter reads the bound existing project with its recorded disk SHA, uses
the existing lossless per-row recipe/history codec, detached canonical portrait
serializer, and `workflow_preset_save.persist`. It does not call ordinary global
project save, switch the editor, analyze a photograph, or submit export work.
Other saved document rows are retained; unrelated dirty recipes remain dirty.
Global dirty is deliberately not cleared, even if only these targets were dirty.
The displayed project dirty badge therefore is not a per-group save receipt.

Shared portrait changes outside the exact selected source assets are refused,
as are changed shared associations, immutable support banks, source provenance,
duplicate sources, missing saved target rows, migrations and external disk CAS
changes. Existing private portrait contexts are independently checked. A dirty
unrelated private recipe is not copied into this save. An unclassified new
import or unrelated shared portrait change may require a separate explicit
ordinary save first; this adapter never silently includes it.

Exceptions before replacement are known no-write failures. After replacement,
readback/publication failures return `status: unknown`; the owner must retain
and reconcile the same request, not issue a new save. A succeeded result updates
the in-memory saved-project baseline and disk SHA, not the live recipes. It says
nothing about exported outputs, actual rendering quality or throughput.

Authored, **UNRUN** acceptance scenarios: unrelated dirty editor recipe preserved;
exact 1–8 successful targets saved; newly prepared group portrait slices saved;
other shared portrait change refused; private context preserved; external edit
CAS refusal; source/revision/history drift during staging refused; disk replace
succeeded followed by readback failure stays Unknown; repeat/late requests do
not save again; cancellation before dispatch does not write; no output files are
created by save. Python fixtures cover only pure evidence-boundary examples and
have not been executed. Build, typecheck, runtime, durability, image and
performance checks remain UNRUN.
