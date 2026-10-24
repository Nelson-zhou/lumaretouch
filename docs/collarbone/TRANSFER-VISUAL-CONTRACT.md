# Collarbone target visual transfer: source-only contract

Baseline: `ef20ce9394fa986c7379544cb88a12b6956bd2e3`.
Requirement `LNX-REF-PC-32465-C-abf0a5c8c9` remains **PARTIAL**. This closes
source wiring for the existing manual operation's confirmed/one-time people
batch image review, not another algorithm or official AI 3D detection.
All tests, native execution, builds, numerical and photographic acceptance are
**UNRUN**. Source inspection is not functional acceptance.

## Actual target image evidence

The existing people transfer controller remains the transaction/history owner.
Selected scalar leaves, including mixed portrait operations, form the complete
candidate per actual portrait owner before either image is rendered. Original
photos can share that owner, so independent per-row candidate graphs would not
be sufficient. Each eligible logical document gets its complete current and
candidate rendering through `full_candidate_render`, with actual original or
immutable derived-source pixels and the canonical full editing chain.

Every nonzero target needs its own independently reviewed body ownership,
visible clavicle traces, category attestations, semantic/manual coverage and
measured source support. Nothing except selected scalar parameters transfers.
Zero strength still requires image review because it can remove an existing
operation. Unselected retained documents sharing an affected source are refused,
not silently changed without their own review. Final actual ledger targets must
be a subset of reviewed eligible documents; neutral no-op rows need not write.

Frozen proofs bind document/revision, original/effective-source proof, before
and candidate state digests, complete people/context digests, source/output
sizes, target coverage digest and both PNG digests. Full RGB rendering precedes
display reduction. PNGs are display-only RGB8 reductions with longest edge at
most 1024; they do not replace float source, edit state or final export pixels.
The exact integer ties-even aspect-size contract is shared across Python,
TypeScript and Rust. No smaller proxy is substituted to fit transport.

## Paged transport and limits

Preflight returns only compact image metadata. The temporary display store is
owned by the active frozen-batch controller session, not the project, preset,
asset package or history. It writes raw PNG bytes into a private temporary
directory under random names. No caller-supplied path is used. It admits at
most 128 MiB raw bytes and 256 image entries across its retained plans; each
image is at most 4 MiB. Expired, consumed or evicted plans release their images.
A failed cleanup retains its byte reservation and is retried, not undercounted.
The operating system can leave temporary files after an ungraceful process
termination; restart does not restore review authority from those files.

At most 16 targets are admitted, without truncation. Preparation has a separate
192 MiB aggregate base64 ceiling; images are subsequently kept as raw files,
not inline frozen history. This is a bound, not a performance or 16-photo runtime
guarantee. Other source-render/memory/support limits remain operative. Multiple
unconsumed plans can exhaust the shared session storage and require finishing
or expiring older reviews. Global mailbox caps have not been raised.

The read-only `batch/collarbone_visual` action requests one side with exact
preflight token, document, revision, side, digest and request identity. It reads
only the frozen bytes, checks their digest again, and never regenerates a newer
preview. An expired read cleans up even when obtaining the plan raises. One
image's base64 response fits the existing 8 MiB native result limit. The native
protocol verifies PNG framing/content hash and exact request echoes. A narrow
validated read-only exemption covers this acquisition and its preflight, not
mutation. Missing or corrupt data requires a fresh review.

## User review, commit, history and uncertainty

Each target has an explicit read button and independently loaded before/after
pair. The UI verifies content, dimensions, target coverage and exact frozen
identity, permits native display-size scrolling and requires its own checkbox.
It labels the images as the frozen complete editing chain, including any other
selected operations, not an isolated sample of the donor's effect. Changing
request/token/target/coverage invalidates old asynchronous results and approval.
This records an explicit user acknowledgment, not proof of attention or quality.

Commit carries ordered per-target PNG and coverage acknowledgments under the
frozen token. Invalid or incomplete acknowledgment does not consume the token.
Before claim the actual final aggregate, target source/context/coverage and
cached images must still match; no new image or support can replace the reviewed
one. A skipped row that changes a shared aggregate may require fresh review
instead of continuing `skip_and_report` with the wrong images.

The existing atomic scoped ledger owns publish, rollback and grouped undo/redo.
Image files are not needed for replaying already accepted history. Claim consumes
the plan and cleans display files; terminal receipts retain compact exact
acknowledgments, including unknown/oversized-result fallback. Cached replay
cannot substitute a different acknowledgment. Unknown mutation outcome remains
query-only, not a reason to blindly retry or discard recovery ownership.

## Explicit remaining paths and limitations

- Persistent association create/patch cannot newly select collarbone until all
  source and target cohort members have a corresponding actual-image review.
  This is an explicit UI/backend refusal. Saved projections and complete unlink
  remain available; old recipes are not reinterpreted.
- Generic legacy batch cannot bypass the confirmed/explicit people image route.
  The separately existing current-photo preset path retains its own review;
  this change does not claim a new visual preset-application workflow. Generic
  derived preset installation remains guarded as before.
- Manual annotation/eligibility errors, low contrast, accessories, skin markings,
  coloured illumination and segmentation ambiguity remain. No AI 3D clavicle
  detection, automatic category inference, physical relighting or naturalness
  acceptance is supplied. Broad alpha/HDR remains unsupported, never clipped
  into acceptance.
- Display pixels are not full-resolution inspection or proof of RGB16 export
  precision. Response timing, 16-target usability, disk cleanup, interruption,
  history replay and all photographic quality need real execution acceptance.

## Primary workflow practice and license

[GIMP filter common features](https://docs.gimp.org/3.0/en/gimp-filters-common.html)
and [GIMP 2.10 release notes](https://www.gimp.org/release-notes/gimp-2.10.html)
were checked on 2026-10-24 for mature original-versus-processed preview practice.
They support showing actual before/after output; they do not validate this
application's ownership, transport, numerical method or visual quality. No
GIMP code, assets or models were copied. New source is repository-original
GPL-3.0-or-later; numerical core and prior recipe versions are unchanged.
