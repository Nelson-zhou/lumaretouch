# Target-local multi-person group presets — SOURCE ONLY / UNRUN

The existing group path now distinguishes two contracts. `lnx.skin.v1` remains
legacy scalar smoothing and still requires one face. It is never renamed or
translated into another algorithm. Retained mode admits complete presets made from
`lnx.skin_finish.v1` (whitening/rosiness) and/or `lnx.skin_texture.v1`
(medium-frequency texture/fine clarity), with optional **global**
`lnx.exposure.v1` and `lnx.white_balance.v1`. At least one retained effect must
be active. Legacy smoothing or other unsupported modules mixed into retained
presets are refused whole. Genuine store builtins expose small starting values,
including `portrait-group-wedding-start`; these are review starting points, not
photographic recommendations, automatic per-image correction or validated quality
levels. Exposure/WB affect the whole photograph, not just faces.

## Owner chain

1. Select 1–8 fresh, distinct physical original photos, excluding the editor.
2. Explicit preparation performs each photo's own canonical load/MediaPipe
   analysis and retained bind. Each target must have 1–8 verified, enabled,
   non-manual, unambiguous detected FaceRefs, genuine own skin semantics and no
   detection-limit hit, existing edits or person associations. Failure stops
   subsequent preparations; receipts distinguish prepared/failed/not started.
3. Stage checked retained leaves against *each target's own detected FaceRefs* in
   the existing graph; stage global exposure/WB in each target's ordinary recipe. No source-face recipe observation, mask, identity,
   guessed correspondence or recognition is copied between photos.
4. Freeze the aggregate candidate graph and each complete target recipe per existing owner. Render every full
   original through the shared full-source/export owner. Display reductions are
   only transport previews. Complete before/after PNG hashes, graph/recipe,
   source/revision/history and exact face sets bind one explicit group approval.
5. `people_batch_ledger.commit_scoped` owns the combined graph/recipe publication
   boundary and protected history, including compensation on publication failure.
   It advances document versions; undo/redo restores the combined accepted intent. Frozen batch
   store owns claim/expiry/unknown outcomes; no second undo store is introduced.
6. Explicit group save uses canonical people/project/history serializers and CAS;
   existing destination-planned, no-clobber per-photo export remains unchanged.

All graph changes are limited to selected documents. Shared-source aliases,
current editor inclusion, stale context, unsupported face, missing image page or
native dependency refuse the entire application. Unknown claimed commits cannot
be resubmitted under a fresh request. Neutral analysis may remain after review
cancellation; it is not applied retouching.

## Honest constraints

“Non-limit-hit” does not mean every person in a scene was detected. Review every
photo for missed faces; this is *all verified detected faces*, not identity
recognition or a complete scene census. Tiny, obscured, indistinguishable or
unsupported faces can refuse a whole group. Skin texture requires its actual
Rust ABI, measured face scale, confident semantic support and full-render memory
budget; no legacy smoothing, global exposure, CPU/Python imitation or proxy
fallback is substituted. Native finish likewise remains required. Zero-active
retained presets are refused rather than creating a fake completed transaction.
Every selected target must acquire an effective retained graph change. Already
edited/same-intent targets and scalar-only no-graph-change members are not silently
accepted or reduced to a smaller group; this release path still requires fresh
prepared originals.

8 photos / 8 faces are bounds, not speed claims. Build, inference, GUI behavior,
undo/reload durability, real wedding-photo quality and performance are UNRUN.

## Acceptance cases to run separately

- Bride/groom/group portraits with reordered detection outputs retain own exact
  refs, exclusions and output; missing/duplicate/limit-hit detections refuse.
- Finish-only, texture-only and combined full images; old smoothing unchanged;
  global exposure/WB + finish/texture is reviewed as one whole; legacy smoothing
  or unsupported mixed modules refuse without dropping any module. A graph or
  scalar publication failure must never produce a success receipt for half a preset.
- One face lacks semantic support/native kernel or is too small: no group apply.
- Replaced source, preset, graph, history or face ref after preview: no claim.
- Entire image/page verification and DOM display precede one approval; no partial
  image acknowledgement or selected-face omission.
- Successful graph batch undo/redo, selected-only save/reload and independent
  export preserve face ownership and unrelated saved/unsaved changes.
- Lost commit/save/export response reconciles original receipt only; no overwrite,
  background continuation or duplicate mutation from an unknown outcome.

## Selective-preset reference and additional acceptance — UNRUN

The [darktable history-stack documentation](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/lighttable/history-stack/)
distinguishes selective copy/paste from copying complete history. This informs
explicit module selection here; it does not establish equivalence of rendering,
face ownership, transaction implementation or photographic results.

- UI lists actual full global/face module scope before approval; omitting WB or
  exposure from a mixed frozen response refuses review rather than truncating it.
- Mixed recipe/graph undo, redo and selected-only project save/reload retain both
  sides and exact target ownership; unrelated crop/repair/history stays unchanged.
- Lost response or failed compensation remains unknown and never auto-retries;
  group success requires the canonical combined receipt, not two receipts.

### Source research and owner boundaries

`portrait_group_mixed_history` is a marker inside the existing people batch entry,
not another ledger. It retains only exposure/WB recipe fields and complete own
source/support/recipe dependency hashes. `portrait_group_mixed_transaction`
stages all target states, then owns graph/state publication and compensation as
one boundary. Canonical project history encode/decode carries the marker through
selected-only save/reload. Undo/redo uses that same transaction; any changed target
recipe/support refuses protected restore rather than overwriting later edits.
Monotonic revisions are not rewound after compensation. Unrecognized partial
writes stay unknown and require reload; a claimed group cannot be reissued.

Additional failure acceptance (AUTHORED / UNRUN): fail after first graph, first
parked state, active-target replay, last target fence, and history dirty marking;
verify either the entire old content with advanced fences or explicit unknown,
never a successful half recipe/half graph. Add a source alias between render and
publication; deny the entire group. Save/reload mixed history, undo with one target
active, redo, then export exact own-face outputs; unrelated edits must survive or
cause explicit protected conflict, never be silently replaced.
