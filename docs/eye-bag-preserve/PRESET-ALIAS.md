# Complete mixed-preset shared-source review

Source implementation and static inspection only. Runtime, numerical,
photographic, persistence, cancellation and rollback acceptance are UNRUN.
The existing `LNX-REF-PC-32464-C-e5fac5fdcf` requirement remains partial:
manual ridge protection is not automatic anatomical detection.

## Two different kinds of ownership

A shared-source portrait graph is not the same thing as a document recipe.
Applying selected portrait parameters can affect multiple documents using the
same effective source and graph owner. Applying a selected crop or colour
recipe belongs only to the active document. A sibling must retain its own
crop, repair stack and nonportrait adjustments.

The mixed-preset review therefore stages one exact portrait plan and separately
renders every affected document. The active document's after image uses the
complete selected preset candidate. Each sibling's after image uses its own
unchanged document state with the proposed shared graph. The review must never
substitute the active image or its colour/crop recipe for a sibling's result.

The existing single-document version-1 route and direct-edit alias history
remain separate. Neither a generic alias guard relaxation nor the graph-only
direct-edit marker authorizes a mixed document-state transaction.

## Required publication and recovery contract

- Review the exact active-first affected set, including each member's own
  immutable effective-source provenance, revision, repair, crop and support
  dependencies. Distinct provenance records may name the same effective pixels.
- Retrieve actual immutable before/after images lazily and acknowledge every
  member. Metadata alone, unread images, expired tokens and an incomplete
  affected set cannot authorize publication.
- Preserve target-owned per-eye ridge support. Preset data transfers scalar
  intent, never donor protection strokes, recovery masks or correction pixels.
- Make the legacy eye-bag replacement choice explicit. Never silently discard
  selected preset modules to produce an easier partial preview.
- Publish the shared graph and only the active document's new recipe through
  one protected composite history entry. Sibling document recipes do not change.
- Preserve complete before/after state through the existing lossless project
  codec and content-addressed assets. Runtime tensors, pointers and lossy
  serialization are not durable undo evidence.
- Portable sky references retain their real relocated locator in the payload.
  Only that structurally validated locator is excluded from the new durable
  content digest; SHA-256, geometry, ICC, bit depth and all recipe fields remain
  pinned. Missing or changed enabled assets still refuse actual render/replay.
- Undo, redo and reopen require the same complete affected membership and
  exact state/source dependencies. An uncertain write remains query-only;
  cancellation or dismissal does not prove that it did not publish.
- A real active-document recipe change remains meaningful even when graph
  scalars are unchanged. A complete graph-and-recipe no-op is rejected as
  unchanged before any write, revision advance or history entry, not reported
  as an uncertain mutation or assigned a fabricated batch identity.

The native composite-write fence rejects subsequent edits, undo/redo, export
and save while the original application is pending or unknown. Safe status and
receipt reads remain available. Receipt queries read the retained original
result; they do not resend the mutation or promise that a retained unknown will
become success. If the original terminal result stays unknown, use the existing
explicit project reopen/recovery path. Only a successfully established new
workspace can discard that obsolete workspace's pending fence. Panel closure,
ordinary photo switching and timeouts cannot do so.

Protected composite undo/redo uses an exact correlated request and the actual
existing ledger marker. Native classification comes from validated publication
receipts or complete engine session summaries, never a client-supplied marker.
A batch ID retained without full publication evidence is diagnostic only.

## Limits and provenance

Unavailable, ambiguous or source-switchable dormant affected documents remain
refused until their complete evidence can be reviewed. Existing bounded image
storage and supported opaque SDR original/derived-source contracts remain in
force. Display reductions are RGB8 review images, not native-pixel photographic
acceptance or broader HDR/alpha support.

This is a workflow and ownership extension of the existing original Rust
protection core and pinned solver, not another algorithm. No new model, weights
or third-party code is introduced. See `REQUIREMENT-AND-RESEARCH.md`,
`NUMERICAL-CONTRACT.md`, `PRESET-TRANSFER.md` and `ALIAS-EDIT.md` for the retained
method, license, support and native-crop boundaries.
