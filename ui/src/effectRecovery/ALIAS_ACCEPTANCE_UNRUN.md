# Eye-bag effect-recovery alias UI

AUTHORED / UNRUN. Source contract work only. No tests, build, typecheck,
product imports, product execution, inference, downloads or installation ran.

## Authored contract

- Only `eye_bag_preserve` admits the separate version-2 alias review. Other
  targets and single-photo version-1 review retain their existing route.
- Runtime load identity is distinct from canonical recipe document identity.
  Preview, image and apply receipts bind the original capture, ticket,
  generation, recipe document/revision and full source dimensions.
- Every review is canonical-hash verified. Each member retains its own source
  proof, crop/output geometry, repair/current-recipe identity and full-render
  before/after pair. Metadata is not a substitute for actual image bytes.
- One member's PNG pair is loaded at a time. Each side has a separate immutable
  request identity and SHA-256/PNG verification. Actual browser decode, natural
  dimensions and two display frames precede explicit per-member confirmation.
- A view-only baseline can enable drawing after the current member is reviewed.
  It never sends a native presentation ACK or creates commit authority. The
  first stroke invalidates that baseline. Every committable mutation requires
  all members plus a final explicit save.
- Late fetch, decode and display callbacks cannot authorize another review or
  another member. Page navigation may retain already-viewed exact member ACKs;
  rereading revokes that member's ACK, and a new review invalidates all ACKs.
- Successful shared publication requires the distinct
  `eye_bag_recovery_alias_review` marker, exact ordered member transitions and
  people-graph-only scope. It creates no second UI undo owner.
- Existing people-owned batch history handles complete-member undo/redo and
  reopened ledger entries. Mixed/malformed markers remain blocked. Unknown
  results retain the original request and write fence; a diagnostic batch ID
  alone does not authorize history. Only verified workspace replacement may
  retire an unresolved old-workspace fence without calling it successful.
- Explicit preclaim failures and verified compensated rollbacks are distinct;
  compensation can advance member versions and requires refreshed review. The
  people-owned history operation retains the existing global recovery fence
  until its own status refresh succeeds; a stale refresh cannot clear a newer
  history request's fence.

## Required acceptance, all UNRUN

Browser interaction and accessibility; first/middle/last page review;
decode/hash/size mismatch; reread and stale-callback races; baseline-only
drawing with zero write authority; all-member final confirmation; capture,
source, repair, graph and workspace invalidation; same-source aliases with
different crops/current recipes; cancellation and lost transport; sparse
unknown receipts; compensated failure; whole-member undo/redo after reopen;
photo/export quality; legacy-target and singleton regression.

The authored `aliasWorkflow.unrun.test.ts` and `aliasHistory.unrun.test.ts`
fixtures are synthetic contract coverage, not photographic evidence and not
executed acceptance.
