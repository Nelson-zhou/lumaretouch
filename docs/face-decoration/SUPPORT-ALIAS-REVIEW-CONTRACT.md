# Visible-support alias review adapter

Status: source-authored / UNRUN. This document covers the engine review and host
subset, not a passing runtime, native, export, numerical or image-acceptance run.

## Bounded authority

The separate `face_decoration_support_alias_preview`,
`face_decoration_support_alias_image` and
`face_decoration_support_alias_confirm` people actions change only the selected
retained face's `face_decoration_visibility` pointer. They do not grant scalar
recipe, effect-recovery, association, donor support or mixed-preset authority.
The scalar-alias protocol and original support-record/numerical implementations
remain unchanged.

Preview checks the existing successful original/derived source-reference proof
and explicit region consent. It retains a candidate graph and immutable bank
off-live. An absent initial support is valid only when the real before is
neutral; a stale/missing active before is rejected rather than rendered with
the new support. An identical pointer or numerically equal region is a no-op,
not a new transaction, even if integer/float JSON spelling would change a hash.

All two to sixteen live shared-source documents must be present. Each keeps and
verifies its own full original/derived provenance, crop, repair, colour, effects
and support context. Equal effective assets can retain distinct original
provenance; only the initiating member must match the initiating owner proof.
Dormant/source-switchable/unavailable member refusal remains in the existing
closure checker. Complete selected plus active before/candidate face coverage
is limited to 64 faces; larger sets are refused, never truncated.

## Wire contract

- Preview payload: exact `region`, `reference_proof`.
- Image payload: exact `token`, `document_id`, `side`, `sha256`,
  `review_sha256`. Both image sides of every member must actually be served
  before complete ACK is accepted.
- Confirm payload: exact `token`, `ack`. ACK uses the existing complete ordered
  document/revision/before/after image digest shape, but a distinct review token.
- Review version 1 includes target, owner, face reference, prior nullable and
  candidate support hashes, exact original region and reference proof, opaque
  before/candidate bank hashes, candidate graph revision and complete member
  coverage/visuals. The exact region is compared by field values across language
  boundaries; clients must not regenerate Python float-containing bank/review
  hashes by serializing parsed JSON.
- Confirm proof includes the frozen support and bank hashes, graph revision,
  exact ACK and every expected/result document revision. `review_sha256` binds
  the full review. `history_review_sha256` is the canonical string-only ACK
  digest and matches the distinct compact history marker.

Preview receipts include unchanged document binding and graph revision with
`people.face_decoration.support_alias_review` equal to the full returned review.
Image receipts contain only the requested immutable image page, not doc-state.
Report metadata also includes `support_alias_reason`. Existing source-reference
PNG receipt pruning remains unchanged.

## Publication, uncertainty and bounds

The dedicated transaction re-renders the complete candidate through the existing
ledger with the staged bank. It checks exact review, bank, closure and available
pages immediately before a one-way claim. The host marks the request started
at that boundary, retains a returned batch ID before any late verification,
and never turns a known ledger identity into a success assertion.

Prewrite failures report `no_write=true`. Verified compensation reports
`no_write=false`, `rolled_back=true`; uncertain publication reports
`outcome_unknown=true`, `no_write=false`. Failed receipts omit attempted
candidate payload and doc-state. Only independently verified late ledger
diagnostics may include the compact marker and exact member transitions.
Support history uses the established ledger and retains immutable bytes on undo;
undo restores the prior pointer rather than deleting retained records.

Display rendering uses existing full-source rendering and display reduction,
with additive optional staged-context arguments only. The default rendering
arguments and all numeric display logic remain unchanged. Limits remain 1024
display edge, 4 MiB per PNG, 128 MiB/256 cached images, four reviews, 1800-second
review TTL, 192 MiB transient encoded-image ceiling, 16 MiB/4096 bank records,
128 people receipts and two retained support-alias image receipt payloads.

## Authored checks, not executed

The owned UNRUN fixture covers strict source paint/image addressing, neutral
initial support, active invalid-before refusal, append-only revised support,
semantic no-op, scalar-authority rejection, complete other-face coverage,
64-face refusal, detached context, actual served image-pair ACK, ordered ACK,
failure receipt classification, known-ID retention and untouched render defaults.
Full native compilation, UI behavior, actual original/derived full-render review,
save/reopen, undo/redo, memory pressure and photographic acceptance remain UNRUN.
