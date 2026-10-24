# Named face-style batches: target-owned visual review

Baseline `f8f8e462813612d107db8b0a61dad7a98b8d601f`. Source authored, runtime
and numerical/photographic acceptance **UNRUN**. This is completion of the same
nine PC-32466 recipe family/style/degree requirements, not a new algorithm count.
The prior [research and single-photo contract](REVIEW-CONTRACT.md) and
[original recipe bindings](../development/face-style-recipes.md) remain applicable.
No additional third-party implementation, weights or assets are copied.

## Explicit intent, not donor geometry

The user selects named-style mode, one of seven binding-v1 styles and a shared
0–100 display amount, then explicitly identifies verified faces in each selected
target photograph. The source face anchors the existing inventory/owner context;
its resolved slider values, geometry, masks and analysis are not recipe inputs.
There is no automatic identity association or new persistent relationship.

The request carries exactly `{version:1, style, amount}` plus the fixed thirty
managed leaves of ten existing operations, all target proofs and exact FaceRefs.
Caller-supplied geometry, coefficients, partial recipes and mixed modules are not
accepted. The engine regenerates the original local coefficients independently
and merges those leaves into each target's own canonical graph. Other parameters,
original files, support masks and accepted ownership remain unchanged. The same
whole-candidate compatibility checks as single-photo styles still apply.

Degree zero neutralizes the thirty leaves; it does not restore prior manual
values or inherited intent. Switching styles replaces those leaves rather than
accumulating edits. Historic recipes are not converted or automatically cleared.
Existing per-person solvers use target-local evidence and the existing canonical
joint sampler; this is not copying a donor's landmark offsets.

## Whole aggregate, then actual images

Targets sharing an original project owner are staged into one aggregate graph
before any target image is rendered. Independent copies remain separate owners
regardless of identical bytes. Every affected logical document must be in the
reviewed target set. A target that would also modify an unseen alias, including
the context/source photograph, refuses and needs independent copies or a revised
complete target set. This does not relax the prior single-photo alias refusal.

Each eligible target uses the complete original or supported opaque-SDR derived
source, repair stack, retained nonportrait state and final aggregate people graph.
The existing full-source renderer supplies actual before/after images. Complete
export snapshots, support/context hashes and source provenance are frozen and
rechecked after all target renders and after final canonical preparation. Removing
one member under skip/report cannot silently authorize a changed aggregate.

Immutable PNG pages live in a separate session namespace on the existing frozen
batch store. A user must load and inspect both verified image pages and acknowledge
each eligible target. The exact ordered ACK binds logical document/revision,
both PNG hashes and the named recipe digest. It cannot authorize another token,
recipe family, selected face set or changed full graph.

Recipe digest uses SHA-256 of the UTF-8 domain `lumaretouch.face-style.v1` followed
by NUL, ASCII style, NUL and the shared amount encoded as big-endian IEEE754 binary64.
Both zero signs normalize to positive zero. This avoids cross-language JSON float
serialization. Existing graph/snapshot hashes remain frozen Python facts and are
not independently recreated from a different float serializer.

## Existing transaction and history owner

The existing frozen batch controller claims the exact reviewed plan only after
all target proofs, snapshots and images are available. The existing scoped people
ledger publishes canonical graphs and owns rollback, dormant document snapshots,
undo and redo. Source-owned FaceRefs remain in the history record. Monotonic
fences/revisions can advance during rollback; a post-claim failure is not claimed
as a proven no-write outcome. Uncertain requests are queried, never blindly retried
or silently dismissed by a generic acknowledgment control.

Named-style ACKs are exact, separate from collarbone/body/spill ACKs, and survive
terminal response limits and replay. Image reads and exact named-style preflights are read-only after the normal
pending/recovery/import guards and do not create another edit/history owner.
Preflight requires the existing active owner and already reviewed target scopes,
never a fresh-import scope migration. Remembering the current already-committed
recipe/history into its owning row and filling runtime caches are synchronization,
not a new edit; byte-for-byte immutable runtime caches are not claimed.

## Explicit limits

- Explicit face mapping only, up to sixteen target documents, existing inventory
  face-count limits. No automatic same-person inference or named persistent cohort.
- Each recipe is an original local composition, not a vendor-equivalent effect,
  learned face classifier, anatomical reconstruction or seven new algorithms.
- Manual and automatic target support capabilities are not broadened. Unsupported
  anatomy, stale analyses, conflicting legacy intent, unavailable existing solvers
  or broader alpha/HDR sources refuse rather than invent or flatten pixels.
- Review images are presentation-only RGB8, maximum 1024-pixel edge, 4 MiB each.
  Existing immutable store has 128 MiB/256-image bounds; large images fail explicitly,
  never truncate a target set or silently lower review detail. Full rendering and
  ordinary 16-target memory/performance have not been measured here.
- All fixture execution, product imports, build/typecheck, native interactions,
  full-resolution numerical/export parity, undo/redo and photographic quality
  acceptance remain UNRUN. Static source checks establish none of these outcomes.
