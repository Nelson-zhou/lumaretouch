# Per-target visual spill transfer: source implementation, UNRUN

Baseline: `8c110e464c21224b4bcc95e667ed92b63b1dc66f`.
This extends the existing partial feature, not the requirement count or proof of
photo-quality acceptance. Relevant official IDs remain
`LNX-REF-PC-32475-C-e999ab085a` and `LNX-REF-PC-32475-C-4bc238dfa1`.
The supplied mapping has no dedicated acceptance cases for either ID. The official
[ID background guide](https://www.pixcakeai.com/guide/32475) does not specify our
solver, numeric controls, preview dimensions or transfer-review protocol.

## What is reviewed

The dedicated `lnx.spill_removal.v1` operation transfers only enabled/strength.
Each target retains its own reviewed ID matte, manual coverage, original/derived
source, assets and independently owned analysis. The preflight renders both its
existing full edit stack and the complete proposed stack through
`full_candidate_render`, without switching the active document, applying an edit
or invoking undo as a preview. Target-specific automatic optics and reference
recipes must be installed before final candidate rendering.

The pair includes every selected module, not only the visible spill difference.
Crop transfer may legitimately produce different before/after geometry. Complete
source renders are reduced to display-only PNGs up to 256 pixels on their longest
edge and 150,000 bytes each. A high-entropy PNG may be reduced further solely for
display. These are not 100% edge inspections, exported images or masks.

The initial bounded workflow permits at most eight selected batch targets. Larger
selections are explicitly rejected before preparation; no photo is silently
omitted. A paginated/on-demand large-batch review queue and cancellable long render
preparation remain future work. Existing result/metadata caps are not raised.

## Explicit approval and stale protection

Every eligible target needs its own actual before/after PNG integrity check,
browser image load and explicit viewed acknowledgment. Request evidence identifies
the target, revision and both PNG hashes. The engine compares the exact ordered
eligible list against frozen compact proofs before consuming the one-use plan.
Blocked targets do not acquire fabricated visual evidence. A later conflict is
reported under the existing skip/recheck policy, not approved with new pixels.

Both before and candidate fingerprints, source proof, people context, dimensions
and proposed scalars are verified again before writing. Actual live replay must
match the reviewed candidate; parked writes and group history keep their own
source ownership. Recipe/source/analysis/matte/coverage/people changes invalidate
review, even if the transferred scalar happens to be unchanged. Compact proofs,
not base64 pictures, belong in frozen/history records. Unknown results retain the
existing receipt/query workflow rather than triggering blind retries.

## Whole-ID scope is not a bypass

Whole-ID portable recipes can also carry spill scalars. That wider operation does
not yet have this complete visual-review integration. Its installer now explicitly
refuses a change to spill scalars, or any changed ID recipe while spill is active.
Use the separately reviewed scalar spill route. Ordinary whole-ID changes with
neutral unchanged spill remain available. No blanket claim that every background
transfer is visually reviewed is made, and no guard is removed from derived paths.

Managed-portrait legacy presets have another explicit boundary: some face scalar
changes are converted to people-graph overrides only during replay. This renderer
does not invent that candidate graph. A mixed spill request changing those managed
face leaves is refused before its images are prepared; apply the portrait parameters
separately, then review spill against the actual resulting target. Separate existing
portrait workflows remain available. Full mixed face-graph preview is unfinished. Replay-unstable managed deformation
mirrors that would be promoted to legacy defaults are also refused before display.
A live people binding must already be established: preview never invokes migration
to manufacture eligibility. These explicit compatibility limits require a future
candidate-people and replay-normalization integration, not weaker state hashes.

## Integration and acceptance

- `spill_transfer_review.py`: target-specific two-state full rendering, compact
  schema, geometry/source/people proof and exact acknowledgment validation.
- Batch preflight/store/sync: private proof, public pair, final candidate checks,
  acknowledgment, actual replay and target-owned scoped history.
- Preset review/controller: the same proof contract under its existing one-use
  target preset token and transaction rollback owner.
- Workflow ports and native batch/preset surfaces: exact command transport,
  correlated receipts and bounded public PNG/source validation.
- `ui/src/spillRemoval` transfer model/view, batch and preset workflows: distinct
  target pairs, image integrity/loading, viewed state and no premature apply.

All numerical, codec, Rust, UI, integration, export, history/reopen and photographic
checks are **AUTHORED / UNRUN**. No product imports, execution, tests, compiler,
build, typecheck, inference or downloads occurred. Existing deep opaque reflection,
same-colour foreground ambiguity, coarse F/B guidance and alpha/HDR limits remain.
This does not implement original-shadow extraction or license any external model.

## Native integrity dependencies

The host promotes already locked transitive packages to direct use, without
upgrading their lock entries: base64 0.22.1 and sha2 0.10.9. This avoids writing
another cryptographic digest implementation. Their primary upstream metadata was
read on 2026-10-23: [base64 MIT licence](https://github.com/marshallpierce/rust-base64/blob/v0.22.1/LICENSE-MIT)
(Alice Maz, 2015), and [sha2 package metadata](https://github.com/RustCrypto/hashes/blob/sha2-v0.10.9/sha2/Cargo.toml)
(MIT OR Apache-2.0, RustCrypto Developers). No source was vendored or downloaded;
normal distribution must preserve upstream dependency licence notices. Cargo
resolution, compilation and dependency compatibility remain UNRUN.

Generic spill batch group receipts are session-only: the controller initializes
an empty ledger; the separate people-history persistence accepts only people-graph
operations. New spill group receipts therefore require their compact visual proof,
without fabricating one for older session records. Existing project document undo
snapshots retain their prior restoration path. This slice does not add durable
cross-restart generic batch-group history or promise unsupported hot-reload migration.

Apply/commit failure now verifies photo-state rollback against the frozen prior
source, full state and people identity. If that expectation is not restored, the
view is invalidated and reload is required; no successful rollback is claimed.
It does not overwrite externally changed people data. Group-history undo/redo
retains its existing scoped recipe/source checks, not a new full-state/people
post-replay verification; broader history rollback hardening remains unfinished.
