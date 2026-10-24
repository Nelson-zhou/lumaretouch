# Eye-makeup native receipt boundary

Status: AUTHORED / UNRUN. The two owned Rust files add source-only transport
admission and adversarial fixture specifications. They do not run the renderer,
build the core, infer faces, prove pixel provenance, or establish photographic
acceptance. Shared registrations and release manifests remain parent-owned.

## Exact parent hooks

Declare in `ui/src-tauri/src/people_api.rs`:

```rust
#[path = "eye_makeup_enhance_protocol.rs"]
pub(crate) mod eye_makeup_enhance;
```

The module exposes these `pub(crate)` hooks with the same signatures as the
existing facial-sculpt receipt family:

- `action(&Value) -> bool`: only `eye_makeup_enhance_reference` and
  `eye_makeup_enhance_review`.
- `command(&Value) -> Result<(), String>`: validate the bounded captured command;
  unknown families are left for their own validators, not admitted as this family.
- `binding(&Value) -> Result<Option<Value>, String>`: return only
  `{eye_makeup_enhance_request: <exact action, payload and six context fields>}`
  for a validated `cmd=people` command. Request ID and host epoch remain owned by
  the existing receipt ledger, not duplicated in the binding.
- `read_only(&Value) -> bool`: true only for the original validated reference
  command with request ID and `cmd=people`, never a review or later event label.
- `receipt(&Value) -> bool`: validate family-specific canonical results.
- `released_reference(&Value) -> bool`: accept only the exact successful released
  source-read form, without payload, image, document state or mutation authority.
- `reference_matches(&Value, &Value) -> bool`: redeem the original successful,
  unreleased, terminal source-read status from the same epoch-bound ledger.

Apply every shared registration, not only the action allowlist:

1. Add both actions to `PEOPLE_ACTIONS`. Call `command` before enqueue; require
   `eye_makeup_enhance_protocol == 1` for this family. Before issuing a review,
   query the existing mailbox at
   `payload.reference_proof.reference_request_id` and call `reference_matches`.
   Reject an unavailable, pending, failed, uncertain, released or stale read.
2. In `PeopleKind::valid`, call `receipt`; allow `released_reference` before the
   generic successful-document-state check. Include `action` in guarded receipt
   delivery and in `begin_command` selection. Do not use `begin_bound` for this
   family's source/review requests or bypass first-terminal ownership.
3. In `receipt_host::ReviewBinding::from_command`, dispatch `binding`; preserve
   the 256 KiB binding budget, set `read_only` from the captured command, and set
   `strict_failure_identity: true`. Success, failure and synthesized unknown
   results must all retain the original `eye_makeup_enhance_request`.
4. Add `read_only` to the existing `project_recovery_fence::issued` read
   classification only after its pending-ID collision check. Do not classify
   reads from received event labels or release uncertain review mutations.
5. Advertise protocol capability only after engine routes, native hooks, shared
   UI workflow and supporting source runtime are installed. Native core
   availability is a separate capability, never a review or visual-quality claim.
6. Keep the engine's `bound_receipt_images` in its canonical image-retention path.
   Released reference receipts close only the matching UI draft, never trigger
   automatic replay. The shared UI owns echo, reference/review/released receipt
   dispatch through `ui/src/eyeMakeupEnhance/model.ts`.

The module uses existing dependencies `serde_json`, `base64`, `sha2`,
`original_shadow_transfer_protocol::hex`, `torso_transfer_protocol::png`, and
`people_api::valid_context`. No new crate or second journal is introduced.

## Own support and scalar contracts

Recipe fields are version 1 plus `amount`, `saturation`, `brightness`, and
`structure`. Each control owns its own `{linked,left,right}`; both values are
finite signed `[-1,1]`, and only a linked control requires equal sides. A receipt
cross-checks all twelve resolved leaves against its reported recipe.

Review payload is exactly `{eyes,reference_proof}`. `eyes` contains at least one
of subject-relative `left` or `right`. Every side has its own makeup polygon,
0–12 exclusion polygons, nullable paired `reference_a` / `reference_b`, explicit
`reference_confirmed`, and the four true user-review flags:
`visible_makeup`, `unoccluded`, `ownership_confirmed`, and
`globe_lashes_brows_excluded`. Polygons have 3–96 unique source-normalized points,
nonzero area, and no nonadjacent edge crossing or touching. A present reference
pair requires true confirmation; an absent pair requires false confirmation.
This is not another cosmetic operation's mask, palette, consent or alias review.
Engine support retention preserves an existing opposite side; native transport
does not fabricate that side or recompute source-owned support hashes.

Reference proof is exactly source SHA/dimensions, the exact targeted FaceRef,
landmark digest, preview digest and original reference request ID. Read receipts
preserve document/people revisions; review receipts advance each exactly once,
retain association revision and the selected target, and clear reusable source
proof/image after publication. Successful review support SHA must match report.
Available-side metadata must match submitted reference confirmation. When actual
analysis is unavailable, the producer can omit side availability despite retaining
reviewed support; native transport does not turn this into automatic visibility.

## Source crop, not full frame

The actual producer is
`engine/src/lumaretouch_engine/eye_makeup_enhance_reference.py::acquire`.
Its exact image schema is:

```text
mime, base64, sha256, source, width, height, view_box, mapping, minimum_eye_width
mapping = source_pixel_centre_periocular_crop
source = {sha256,width,height}
```

It returns an unretouched effective-source periocular crop, not the rendered
effect. The native boundary verifies canonical base64, the 5 MiB byte cap, RGB8
PNG framing/CRC/dimensions, SHA-256, exact nested source equality, 2–1280 image
extents, finite crop bounds, and minimum displayed eye width of at least 40.
It rejects sculpt's `normalized_full_frame`, flattened source dimensions,
`decoded_width`, `decoded_height` and `orientation` fields.

The producer maps crop edges as `(x - 0.5) * (source_width-1)/(decoded_width-1)`
and similarly for Y. Therefore an edge can be negative or slightly outside the
source pixel-centre extent. Native bounds permit this half-decoded-pixel border,
using the existing full-source / downward-ALIGN=8 proxy contract; they do not
incorrectly force `[0,source_extent]` or interpret the image as full-frame.
Because decoded dimensions and landmark coordinates are not in this image
payload, this transport cannot independently reconstruct the exact crop or
verify the measured eye width. Those checks remain with the source producer,
retained face analysis, exact proof and engine reference cache. PNG framing is
not decompression or proof of photographic content.

## Diagnostics and verification limits

Nonempty facts must match this operation's own per-side controls, support hash,
source/FaceRef/landmarks, face-skin observation, source/render dimensions, pixel
counts, native solver label and all explicit limitations. Their shape is not
proof the native solver ran or that makeup was automatically detected. Facts
permit only active sides; per-side changed counts sum to the total. Amount
changes require measured paired-reference counts; other controls do not claim
unused reference sampling.

`eye_makeup_enhance_protocol_unrun.rs` contains 18 authored fixtures covering
signed bilateral controls, independent polygon/reference consent, exact fields,
crop-vs-full-frame schema, PNG tampering, revision and twelve-leaf fencing,
unavailable analysis, terminal reference redemption, substituted receipt echoes,
released reads, pending write/read identity collisions and bounded facts.
Receipt-host and `PeopleKind` fixtures require the parent's complete shared
registrations before future authorized execution. No test, build, compiler,
typecheck, product import, inference, download, install or Git/GitHub write was
performed for these owned files. Static source review and hashes do not replace
any of those UNRUN checks.
