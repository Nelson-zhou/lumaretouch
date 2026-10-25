# Hair volume: current-photo host contract

Status: AUTHORED / UNRUN. This slice has only received static source/AST review.
No application import, unit test, typecheck, build, native execution, model
inference, installation, download or photographic-quality acceptance was run.

## Ownership and interfaces

The operation is `lnx.hair_volume.v1`. Crown (`control:PC-32472:2`) and sides
(`control:PC-32472:3`) retain their independently versioned family recipe.
Only four scalar override leaves enter the existing people graph:

- `/crown/amount`
- `/sides/linked`
- `/sides/left`
- `/sides/right`

Signed amounts and defaults are local implementation policies, not claimed
reference-product values. A linked side recipe must contain equal explicit
left/right values. No uniform face-oval/head-size shortcut is admitted.

`hair_volume_project.py` reads the canonical live `_people_support` bank, whose
project/context key is `people_support_assets`; frozen export snapshots use the
already established `support_assets` key. Records have kind `hair_volume`.
There is no new support bank, graph owner, history stack or source identifier.

Shared host integration calls:

- `validate_leaf`, `validate_graph`, `validate` and `validate_owned_graph` for
  scalar, current, private-context and history admission;
- `require_transition` for generic live preparation, and
  `require_unreviewed_transition` for generic patch/preset/transfer paths;
- `preview_kwargs` and `shared_preview`, returning `hair_volume_assets` and
  actual shared hair semantic evidence when active;
- `capture` / `capture_derived` and `kwargs` for immutable original/composite
  export inputs; no original-file path is passed as derived image content.

The controller exposes `HairVolumeHostMixin`, `check_request`, `read_only`,
`execute`, `finish`, `capability`, `guard_other`, `dispatch_rejected` and
`invalidate_after_reload`. The last is called only after an authoritative
project reload, never to turn a timeout into a known result.

## Effective source and independent manual permission

Every selected `FaceRef.asset_sha256` must equal the effective source SHA for
both original and immutable derived photos. Original physical-file provenance
remains a separate `source_proof.original_sha256`; it is not rebound into a
composite identity. Source dimensions, source proof, analysis revision, graph
fence, document epoch/revision, owner, row and selection all remain pinned.

Context reads actual existing `hair_colour_evidence` output. It may retain that
output losslessly but does not install or run a model. Missing actual evidence
is a blocker, not a synthesized hair mask. Hair-colour support and its previous
consent are neither required nor accepted as hair-volume permission.

Each nonzero crown/left/right region needs its own measured source contour,
paired interior-hair and clear-background probes, plateau/fade bounds and
explicit region confirmation. Inactive unfinished drafts remain UI-local and
must be submitted as null. Whole-source and visible-anatomy reviews must both
be true. The authored support policy permits at most two ear boxes, one neck
box, and 64 other-person protection boxes. Face detections are never a census:
all retained source faces, including disabled/manual/unresolved records, and
the newly confirmed exposed-anatomy/other-person rectangles are protective.
Hidden anatomy is not inferred. Changes to retained face anatomy invalidate
an active review rather than silently altering ownership.

## Exact protocol and full review

The request envelope contains exactly `cmd: hair_volume`, protocol 1,
`operation_id`, `request_id`, `action`, `people_context` and `payload`.

1. `context`, with empty payload, returns the exact effective source image,
   source PNG digest and dimensions, selected FaceRef, current recipe, actual
   semantic evidence digest, source kind and installed-symbol/ABI availability.
   Availability is not numerical or photographic acceptance.
2. `preview` carries the recipe, independent regions/protection and explicit
   global plus per-region confirmation flags. It creates a private candidate
   graph and append-only candidate support bank. It never swaps the live graph.
3. Both before and after are rendered by `portrait_review_render.image` through
   `full_candidate_render` from the complete current photograph, all mixed
   edits and complete final crop/rotation. No proxy-only or operation-isolated
   stand-in is labeled as the result. The after render receives its exact staged
   graph and shared support bank. Missing/unsafe native fields cause refusal.
4. A third PNG shows actual whole-source pixels with reviewed contours,
   samples and protection rectangles. It is a source diagnostic, not a
   segmentation or rendered after image. When final geometry has a different
   aspect ratio, this diagnostic preserves the entire source with letterboxing
   at the same display extent as before/after. It never stretches the source.
5. `presented` must echo the preview ID, review token and exact before, after
   and diagnostic PNG hashes. Native validation and UI byte/hash/image-load
   acknowledgment must complete for those same images.
6. `commit` additionally requires explicit final confirmation. Before publication
   it rechecks all target/source/graph/recipe/support/evidence fences and the
   complete candidate snapshot. The token covers both full render proofs,
   source diagnostic, independent confirmation flags and support content hash.

Publication uses the existing `_people_prepare_graph`, `_people_publish_graph`
and `_history_record` owners. Its short-lived operation-local admission binds
the exact graph owner, monotonic fence, before/candidate states, shared bank
digest and reviewed token. This does not authorize a generic patch.

`clear` writes the complete neutral family and detaches only the active
hair-volume pointer. Immutable support/evidence bytes remain for undo/reopen.
It does not call this family's native solver or require fresh semantic evidence.
Other still-active mixed effects continue to enforce their own render contracts.

`status` returns the original immutable request's full correlated receipt,
or a known missing result, without repeating the original operation. Exact
request IDs are never silently evicted/re-executed. Reusing an ID with changed
content is refused. Bounded read-image retention replaces old read payloads
with correlated tombstones, preserving request identity; commit/presented
receipts are not weakened. An uncertain mutation blocks further editing until
its original result is settled or an authoritative project is reopened.

## Deliberate boundaries and future acceptance

This slice refuses all-people, person/group inheritance, source-identical alias
activation, cohort/batch transfer and generic active recipe changes. It does not
invent partial alias review. Dormant alias protections remain in force.

The host contains no new numeric solver, mask warp or RGB resampling pipeline.
It relies on the independently authored `hair_volume_runtime` / native family
and the parent's unchanged common sampling owner. All direct quality claims
remain pending real native and mixed-photo evaluation.

Authored regressions in `engine/tests/test_hair_volume_host_unrun.py` cover
strict request/ACK shape, independent consent, effective derived source
binding, staged append-only bank isolation, exact publication identity,
native-independent clear, current-source protection changes, original receipt
idempotency, read-image tombstones and uncertain publication retention. These
fixtures are UNRUN, not proof that the engine or UI starts or renders correctly.
