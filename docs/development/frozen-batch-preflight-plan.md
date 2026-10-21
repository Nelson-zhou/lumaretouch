# Frozen batch preflight: design, not implemented

Original AI acceptance BATCH-001 preserves source-version snapshot; BATCH-002
protects targets edited after preflight. Current preflight is stateless and commit
recaptures current source/targets. The narrow scoped-undo correction does not close
this gap.

## Ownership

A separate document-version owner assigns runtime UUID row identities plus a
monotonic mutation fence outside recipes/undo snapshots. Retained/reordered rows
keep identity; removed/re-added paths do not. Successful project create/open rotates
workspace generation. _load_id is a render/import identity, not a stable document ID.
Undo never rewinds a fence. State hashes or stack length cannot detect edit→undo.

Preflight owns bounded immutable records: random token, workspace generation,
source identity/version/path, canonical serialized transferable module parameters,
selected modules/policy, target identities/expected versions/eligibility and rejected
inputs. Do not retain image/precompute arrays or mutable row references.

Commit consumes a token, not another editable source/selection definition. Reject
unknown, expired, consumed, foreign-generation tokens and conflicting extra fields.
Keep bounded terminal results for idempotent repeated commit requests.

## Commit

Resolve targets by stable identity, not stale index/path. Changed versions or missing
identities are explicit conflicts. Recheck eligibility; a preflight-blocked target
must not silently become authorized. skip_and_report applies unchanged eligible
ones; recheck writes nothing until a fresh preflight/reconfirmation. No overwrite.
Use frozen source modules even if current source is edited, switched or removed;
report those diagnostics without substituting the current photograph.

Revision fencing must cover admitted live mutation boundaries, effective history
undo/redo, parked batch writes, recipe-changing proxy recovery and eligibility
changes outside EDIT_CMDS. A conservative attempted-mutation fence may produce
false conflicts but must not be advertised as an exact changed-recipe counter.
Read-only status, compare, thumbnails and pure selection must not bump it.
Finalize result revisions before publishing success; outer history recording must
not double-increment or publish old metadata.

## History and UI

Keep one undo step per affected document. Batch undo retains scoped-value conflict
checking, but restores only recorded modules into current state so unrelated later
edits survive. Stable identities must also replace index/path-only ledger lookup.

Use dedicated request IDs and an epoch-bound native batch result owner/API. Enqueue
acceptance and command_done are not success. UI: preflighting→review→committing→
terminal, with actual source/version and target/conflict details. Selection/scope/
policy changes invalidate the plan; dismissed/late replies cannot revive it.

Required tests: frozen source after source edits/removal; target edit→undo/redo and
same-gesture return; reorder/remove/re-add; project create/open/restart; skip/recheck
zero-write behavior; identity/eligibility/proxy changes; duplicate token/click; live
and parked undo retaining unrelated edits; no conflicts from pure reads/selection.
