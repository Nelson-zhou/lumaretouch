# Face-decoration mixed-preset native boundary

Status: SOURCE-ONLY, AUTHORED / UNRUN. Static review is not Rust compilation,
runtime, renderer, numerical, image-quality, UI, packaging or release acceptance.
Baseline: `279b7f28d2ba281e1f514dccba89ced06f59282a`.

## Versioned boundary

- Existing single-document `face_decoration_preset` v1 and its scalar ACK remain
  unchanged. Existing support/direct/batch/cohort and eye-bag protocols remain
  separate authorities.
- `face_decoration_preset` v2 adds exactly `before_bank_sha256`, `members` and
  `review_sha256` to the v1 keys. The complete wrapper, excluding its review
  digest, determines the review digest. The support-bank digest is therefore
  included in the frozen identity, not a client-supplied replacement mask.
- The first member is the active document. All 2–16 unique members have exact
  `{path, role, visual}` fields. Each visual independently validates its original
  and effective source proof. Shared effective bytes do not replace original
  provenance. All share effective source, source dimensions, coverage and shared
  graph hashes. Siblings retain their own nonportrait state hash and output
  dimensions; only the current document receives the full selected recipe.
- The v2 ACK has exactly `review_sha256`, `preset_sha256`, `applies_sha256` and
  ordered `members`. Each member binds document, canonical revision, both image
  digests and coverage. Revisions are bounded to advance safely once.
- Immutable `face_decoration_visual` reads can include both
  `member_document_id` and `member_revision`. Those coordinates remain bound to
  the original preset, current load, token, active revision, side and hash.
  Partial or write-bearing image coordinates are rejected.
- The native API requires `face_decoration_preset_alias_protocol: 1` for member
  reads and composite apply. It does not gate legacy single-document requests
  on the new capability.

## Publication and unknown results

Successful apply requires a real batch ID, the complete ordered `alias_members`
revision publication, current document binding, and the distinct compact
`face_decoration_preset_alias_review` marker. Its selected module list is unique,
nonempty, at most 32 entries, and cannot contain the graph-ledger pseudo-module.
It need not select decoration: retained decoration can require whole-render
review for a selected exposure/color/crop recipe.

The marker binds review/preset/applies digests, current logical document, member
count and exact selected modules. It cannot be combined with direct decoration,
support, batch, cohort, face-style or eye-bag alias markers. ACKs from another
review family cannot substitute for the frozen complete decoration ACK.

Known no-write apply refusals retain exact request/ACK identity and a nonempty
error, without batch, publication, before/after or document-write evidence.
Unknown results may retain a batch ID alone, or a fully verified marker and
complete member publication. Compaction never invents revisions. Contradictory
no-write, rollback, success or recovery claims do not settle the request.

The shared recovery fence covers composite apply and history, including direct
native dispatch. An uncertain write blocks edits, history, save and export;
request queries and safe reads do not replay it. An engine-issued or invalid
publication unknown remains immutable. Only a native transport-generated
unknown for the new decoration composite apply/history can reconcile an exact
late engine terminal in the same engine-observed workspace. Apply retains the
original ACK; history also retains the exact observed marker. Unknown engine
events close that reconciliation window. Missing/malformed/changed workspace
or marker ownership cannot settle it. No new write or request is dispatched.
A verified project reopen/new engine epoch is the recovery escape when the
outcome remains unknown; a bare or failed open event cannot clear the fence.

## Saved history

Engine-observed session summaries classify the new marker independently of
legacy/direct/support histories. Missing, malformed, changed, mixed or oversized
markers cannot launder a known protected batch into ordinary undo/redo. Restored
history accepts only the original batch ID with correlated request identity;
clients cannot supply markers or new replay authority.

Successful undo/redo requires exact marker echo, graph-ledger scope, complete
unique restored indexes and no conflicts. Known no-write/compensated failure
requires empty restoration proof and consistent no-write/rollback identity.
Unknown history remains fenced and retains original batch/marker identity.

## Source-only verification

- Static inspection of schema, native command routing, receipt binding,
  compaction, history classification and recovery-fence call paths completed.
- `git diff --check -- ui/src-tauri/src` completed without whitespace findings.
- Protocol fixtures cover original plus supported derived members, independent
  sibling crops, immutable bank digest, canonical revisions, all-member caps,
  stale/member image identity, exact publication, foreign markers, retained
  decoration without selected decoration, no-write/unknown retention, reopened
  history, marker laundering, late receipt fencing and bounded transport-first
  late-terminal settlement without changing old scalar/eye-bag semantics.
- All authored fixtures remain UNRUN. No tests, build, typecheck, product imports,
  product execution, inference or downloads were performed.
