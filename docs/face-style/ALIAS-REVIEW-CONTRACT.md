# Explicit shared-source face-style review

Baseline `75a627b6f89c7b377b4007398de3dd7206a02092`. Source-only work;
all execution, native interaction, numerical and photographic acceptance UNRUN.
This closes an ownership/review path for the same nine PC-32466 style/degree
requirements. It adds no recipe, anatomical solver or algorithm count. The
original [recipe research](REVIEW-CONTRACT.md) and [cohort contract](COHORT-REVIEW-CONTRACT.md)
remain applicable. New code is repository-original GPL-3.0-or-later; no external
code, model, weights or assets are downloaded or copied.

## Why aliases cannot be treated as one photograph

Established project originals may share one canonical portrait graph. Several
retained documents can therefore expose the same measured face and immutable
effective source, while having different crop, repair and other image state.
A face-level change affects every such document. Private virtual copies already
have legitimate independent graph ownership, but silently converting an existing
shared document would change its association and history semantics. This path
does not perform that conversion or invent new FaceRefs/source digests.

Existing single-document review version 1 remains its own path, with a narrow
additional refusal when another same-owner document retains the edited source
only in dormant history. Its numerical, no-op and local publication semantics
are not otherwise migrated. Version 2 names
the current document first and every affected same-owner document, bounded to
sixteen including the current document. Each member retains its own path,
revision, source proof, complete render/repair/context snapshots and actual
before/after image pair. A matching effective asset is not permission to reuse
another document's crop, repair state, provenance or rendered output.

The exact affected set is derived from the existing ledger's actual graph change,
not from the visible selection or a caller-provided partial list. Hidden or
trashed/unavailable members cannot be silently omitted. Newly appearing or
changed members invalidate review. No geometry, support mask or inferred person
identity is transferred between independent sources.

## Consent, publication and history

Every member's real PNG pair must be retrieved, byte/dimension checked, loaded
and explicitly acknowledged. The v2 ACK contains the frozen review digest and
all member document/revision/before-hash/after-hash coordinates in order. Image
requests name their exact member document; current-document image consent does
not authorize siblings. Review images remain bounded RGB8 display reductions,
not full-resolution or numerical quality acceptance.

Confirmation rechecks full source/render snapshots and exact member closure
after preparation. The existing scoped graph ledger is the sole publication,
rollback and undo/redo owner. A successful alias result carries its real batch
ID and every member's exact one-step document revision advance. It is not
recorded as an additional local document undo. The existing thirty-leaf staging
advances graph revision by thirty; document revisions and the owner commit fence
advance once. These distinct counters are not silently normalized. Unknown outcomes retain the
existing query-only receipt fence; retrying an uncertain mutation is not an
accepted recovery strategy.

An unchanged canonical alias candidate is a known preview refusal, before claim
or publication. It does not fabricate a batch ID or advance bookkeeping just to
satisfy a success validator. Existing version-1 no-op behavior is not migrated.

Alias batches carry an explicit exact-member history marker. Later undo/redo
must not silently expand to new aliases or discard members after source/owner
changes. Marker validation applies to this new history family, not a blanket
reinterpretation of older saved batch recipes. Strictly validated persisted markers
also contribute read-only workspace-scoped classification to the existing batch
status. UI controllers use that classification for query-only uncertainty and
complete-member history result checks, including the global batch toolbar after
reopening. This metadata is not image consent, a second undo stack, or authority
to apply a new recipe.

## Dormant source limits

Current-source images cannot honestly review a sibling whose affected source is
only retained in an earlier source-switch history frame. Such dormant siblings
remain an explicit refusal until the affected source is restored and reviewed,
or a genuinely independent document is used. Malformed/ambiguous source-history
metadata is not ignored. The header inspection is bounded to 64 frames per
undo/redo stack and 10,000 retained frames in aggregate; an exceeded bound refuses
the complete operation rather than dropping members. Unknown pending imports
conservatively block the v2 route; known provisionally isolated imports are not
converted to shared owners. Ordinary overlapping historical edits remain subject
to existing protected history rules; this is not a promise that every arbitrary
past crop/recipe can be restored after a later shared edit.

## Remaining acceptance and capability limits

No automatic person/shape classification, semantic reconstruction, proprietary
numerical equivalence or photograph-quality claim is added. Existing unsupported
anatomy, transparent/HDR retouch and other solver restrictions remain fenced.
All product execution/imports, tests, build/typecheck, inference, native/history,
project reopen, export, performance and photographic acceptance are UNRUN.
