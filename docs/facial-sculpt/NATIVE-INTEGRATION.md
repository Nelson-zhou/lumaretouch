# Facial structure native transport boundary

Status: **AUTHORED / UNRUN**. These Rust source files and their fixtures have not
been compiled, executed or tested. Static source inspection and file hashing are
not runtime, visual, PNG decode, inference or release acceptance. This document
describes the integration contract; it does not assert that shared hooks are
already installed.

## Ownership and exact protocol

`ui/src-tauri/src/facial_sculpt_protocol.rs` belongs under the existing
`people_api` module and uses the existing registered `people` command and
`ReceiptHost<PeopleKind>`. It adds no Tauri command, transaction ledger, graph,
support bank, compositor, renderer, export solver, alias workflow or recovery
authority.

- Operation: `lnx.facial_sculpt.v1`.
- Portable recipe: exactly `{version: 1, highlight: 0..1, shadow: 0..1}`.
- Actions: exactly `facial_sculpt_reference` and `facial_sculpt_review`.
- Reference payload: exactly `{}`.
- Review payload: exactly `{region, reference_proof}`.
- Native receipt binding: exactly `facial_sculpt_request`, containing the action,
  payload, document ID/epoch/revision, state revision, association revision and
  target captured from the original command. The outer request ID and engine
  epoch remain owned by the existing ledger.
- Reference proof: exactly `source`, `face_ref`, `landmark_digest`,
  `preview_sha256`, `reference_request_id`. Source has exactly SHA-256, width and
  height; dimensions are integral and in `[2, 1,000,000]`.
- The target must be one exact face. Its source hash and retained face reference
  must match the proof. No inferred ownership or source substitution is admitted.

Public native hooks are `action`, `command`, `binding`, `read_only`, `receipt`,
`released_reference` and `reference_matches`. The parent module can also use the
restricted `recipe`, `region` and `reference` helpers. There is no separate
`record` API or second receipt owner. Unknown actions are not classified as this
family; the existing `PeopleKind::ACTIONS` allowlist remains mandatory.

## Region and image bounds

The region contains exactly a canonical source-normalized local-mask brush
recipe and the affirmative booleans `visible`, `unoccluded` and
`ownership_confirmed`. Only add/subtract brushes are accepted; at least one
enabled positive-opacity add is required. All IDs are unique. The native limits
match the canonical mask contract: at most 64 objects, 1,024 points per object
and 8,192 points total, finite normalized point pairs, finite nonsingular axes,
bounded opacity and feather. The UI is deliberately more conservative at 32
strokes and 4,096 points. The full command additionally stays within 256 KiB.

The source page is one RGB8 PNG in the document report, not repeated in the
receipt payload. Admission checks canonical base64, at most 5 MiB of PNG bytes,
CRC/framing through the existing `torso_transfer_protocol::png` helper, exact
SHA-256, dimensions no larger than 1,280 pixels on either edge, full-frame
normalized mapping, one EXIF normalization and the existing decoded-source
aspect/scale contract. This is framing validation, not PNG deflate decompression
or proof of image content, skin visibility, actual inference or numeric quality.
No existing private helper needs to be exposed or copied into a shared module.

## Exact report and terminal semantics

The document report is exactly:

`recipe`, `facts`, `source`, `face_ref`, `landmark_digest`, `reviewed`,
`source_preview`, `reference_proof`, `support_sha256`, `native_available`,
`support_available`, `support_reason`, `suspended`, `alias_required`,
`alias_reason`.

The last two fields are refusal-only diagnostics. They explain why the existing
current-photo source-owner guard will not edit shared-source rows. They grant no
permission and have no member counts, alias review objects, acknowledgments,
support aliases or decoration metadata. A successful review must report
`alias_required: false`. The engine still checks actual affected source owners.

`facts` is either empty or the bounded current facial-structure diagnostic
schema: measured zone counts and face width/radius, protected face count, exact
recipe/face/landmark, semantic-model digest and named face-skin observation,
source/render dimensions, positive and negative structure pixel counts, their
sum, reason, solver/policy/composition names and explicit limitations. No
decoration catalogue, pigment pattern, material identifier or rasterizer name
is admitted. Facts cannot themselves authorize pixels or prove that a solver
ran. The exact active schema is coordinated with `facial_sculpt_layer.py` and
`facial_sculpt_geometry.py`; new diagnostics require a coordinated change.

A reference success preserves all six context fences and both revisions. It
contains the reference proof in both payload and report, and its one verified
source PNG in the report. It emits no frame. A review success echoes the exact
submitted proof and the retained support digest, advances document and people
state revisions by exactly one, preserves association revision, target and
selected face, and matches resolved highlight/shadow leaves to the reported
recipe. It does not retain a reusable source page after the write. Renderer
availability and support diagnostics remain independent of successful consent
retention; a transport success is not a rendered-pixel acceptance claim.

Only a retained, successful, non-unknown, unreleased reference in the same
native ledger can be redeemed for review. Epoch reset, any context change,
different proof, pending read, unknown read or released page removes that
authority. A released cached reference is admitted only in its exact compact
successful-read shape, with no payload or document state. It can never release
a review mutation. Native unknown writes retain their original binding and
remain fenced; later success does not overwrite the first unknown terminal.

## Shared integration checklist for the parent owner

The native worker owns only its two new Rust files and this document. Shared
files must be integrated by their assigned owner:

1. In `people_api.rs`, declare the module with its file path, add only the two
   exact actions to `PEOPLE_ACTIONS`, call `command` on admission and `receipt`
   from `PeopleKind::valid`, and admit `released_reference` before generic
   document-state checks. Require `facial_sculpt_protocol == 1` for either
   action. Before enqueueing a review, redeem its original reference ID through
   `reference_matches` against this mailbox's retained status.
2. In that same API, use `begin_command` for this family, not unbound `begin`,
   and guard its incoming events until the exact native ledger has accepted
   them. Do not let an unvalidated sculpt event update document state or settle
   recovery fences. Preserve existing action/request/epoch and first-terminal
   behavior; no new late-reconciliation exception is needed.
3. In `receipt_host.rs`, capture `binding` in `ReviewBinding::from_command` with
   a 256 KiB maximum, `read_only` from the original command and
   `strict_failure_identity: true`. Add only `facial_sculpt_reference` to the
   existing read-only eviction allowlist. Do not add the review mutation, new
   alias marker or replay/late-terminal exemption.
4. Add `read_only` alongside existing exact people source-read families in
   `engine.rs`, `native_dispatch.rs`, `project_recovery_fence.rs` and
   `preset_alias_recovery_fence.rs`. The existing duplicate/pending-ID checks
   must run before a read-only bypass. A read receipt with a reused mutation ID
   must not clear a write fence.
5. Engine receipts must echo `facial_sculpt_request` on success and failure,
   preserve the exact source/reference/review payload contracts and compact
   released-read shape, and continue publishing through existing people graph,
   support/history and source-ownership mechanisms. UI receipts must compare
   this family-specific echo rather than accepting a decoration echo.

## Authored fixture coverage

`facial_sculpt_protocol_unrun.rs` specifies accepted read/review requests,
independent brush consent, field/foreign-authority rejection, numeric recipe
bounds, exact PNG/source echo, CRC and trailing-byte refusal, all context fences,
strict one-step revisions and overflow, refusal-only alias diagnostics,
substituted binding becoming immutable unknown, strict failure identity,
released read limitations, duplicate-ID mutation fencing, bounded eviction of
unknown reads but not unknown writes, and bounded sculpt-only renderer facts.

These fixtures depend on the shared integration above. Every fixture remains
**AUTHORED / UNRUN**. Compile, test, runtime UI, inference, real portraits,
full-resolution export, history and packaging acceptance require their own
authorized environment and have not been established by this work.
