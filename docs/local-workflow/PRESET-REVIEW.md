# Exact scalar preset image review

Status: source implementation and authored fixtures only. All product execution,
numerical, image-quality, native bridge, UI, test and end-to-end acceptance is
UNRUN. This document describes the isolated review owner, not a claim that a
workflow has applied a preset successfully.

## Bounded genuine recipe support

`workflow_preset_review.WorkflowPresetReviews` accepts only a nonempty saved
preset consisting entirely of `lnx.exposure.v1` and/or
`lnx.white_balance.v1`. This includes the genuine packaged `color-warm` preset.
It resolves the current validated preset through
`workflow_preset_catalogue.resolve(preset_id, preset_sha256)`. It does not accept
caller-authored modules, a copied donor state or a catalogue row as authority.
An unsupported module, including an inactive one, rejects the entire preset.
There is no partial-module omission or substitution.

XMP adaptations remain outside this generic owner. The owner neither creates
XMP provenance nor removes it to evade the existing XMP acknowledgment contract.
A target with retained active face decoration also remains under its existing
dedicated complete portrait review, even when the selected preset is colour-only.
No generic acknowledgment impersonates that owner. Other existing target edits
must survive and render through the complete export snapshot or the review fails.

The actual candidate comes from `face_decoration_preset_admission.candidate`,
the same candidate path used by `PresetController`. It is checked against
`scope.apply_modules` without modifying unrelated target data. Exposure's seven
tuple members, omitted white-balance option semantics and the target reference
white are owned by their existing implementations, not reimplemented here.

## Explicit loaded target

Every target is exactly:

```json
{"document_id":"stable-document-id","load_id":"current-load-id","revision":"0"}
```

These are three different identities. A load ID is not a document UUID or a
document revision. The current row must be that exact retained object, its
existing document-version owner must already have initialized its fence, the
loaded path must match, and its active portrait ownership must already exist.
The review does not select a photo, initialize an identity, activate a people
context, remember the current photo, alter a recipe, save a project or touch
unrelated history stacks. Those lifecycle operations belong to the parent host.

The owner rechecks the saved preset, stable document ID, load, revision,
workspace, row ownership fields, active people owner object and fence, complete
current/candidate state fingerprints, original/effective source proof, ordered
active/redo repair proof and complete export-snapshot fingerprints. Source,
repair and people data remain the target's own. A change in any of these fields
invalidates the review; matching pixels at a replacement row do not restore it.

## Complete rendering and immutable image pages

Both sides use `portrait_review_render.image`, backed by
`full_candidate_render.render`. The full original or immutable creative source
and all existing target edits must render successfully. There is no filmstrip,
proxy, old display buffer, reduced RAW decode or skipped-effect fallback.
Only the final review display is reduced to a maximum edge of 1024 pixels and
encoded as RGB8 PNG. Full source/render data is not replaced by these PNGs.
A target without retained portrait content does not invent a portrait graph.

Each PNG has an immutable whole-image SHA-256, dimensions, byte length and page
count. Retained blobs are private immutable in-memory bytes, never project
assets or filesystem paths. A fixed 65,536-byte page protocol transports them:

```python
owner = WorkflowPresetReviews(engine)
review = owner.prepare(preset_id, preset_sha256, target, cancelled=cancelled)
page = owner.retrieve(review_id, review_sha256, target, side, image_sha256, page_index)
```

`review` has schema `lrt.workflow-preset-review.v1`, `review_id`,
`review_sha256`, `target`, `preset_id`, `preset_sha256`, `module_ids`, `before`,
`after`, source/state/people/repair/render proofs, `page_bytes: 65536`,
`ttl_seconds: 900`, `approval_only: true`, and `runtime_verified: false`.
Each `before`/`after` object has `mime`, `width`, `height`, `sha256`,
`byte_length`, and `page_count`.

The page response echoes the exact review, target, side and image metadata. It
adds `page`, `page_bytes`, `offset`, `page_byte_length`, `page_sha256` and
`base64`. The base64 encodes raw PNG byte segments, not independently decodable
image fragments. The client must concatenate every page in order, verify page
and whole-image hashes plus byte length, then display the complete images.
The owner records successful retrieval of every page of each side. Image reads
and acknowledgments revalidate the current target; they never rerender or apply.
Retrieval is evidence of delivery only, not an inference that the user looked.

## Explicit approval, never application

The UI must wait until both exact complete images have been verified and shown,
then obtain an explicit user confirmation. It must not automatically acknowledge
because a review opened, image bytes arrived or a previous target was approved.
The acknowledgment has precisely these keys:

```json
{
  "review_id": "retained-review-id",
  "review_sha256": "exact-review-sha256",
  "target": {"document_id":"stable-document-id","load_id":"current-load-id","revision":"0"},
  "preset_id": "color-warm",
  "preset_sha256": "exact-current-saved-preset-sha256",
  "before_sha256": "exact-before-png-sha256",
  "after_sha256": "exact-after-png-sha256",
  "accepted": true
}
```

`owner.acknowledge(ack)` returns an internally retained receipt with schema
`lrt.workflow-preset-approval.v1`, a random `approval_id`, the complete exact
acknowledgment, `approval_sha256`, `approval_only: true`, and
`runtime_verified: false`. An identical repeated acknowledgment reads that same
receipt; it never mints another approval. The receipt contains no replayed state,
history delta, fake preflight token, XMP token or successful-apply assertion.

## Application boundary owned by the parent

Only after the native core has journaled its actual `ApplyPreset` operation may
the parent call:

```python
authority = owner.consume(approval_receipt, target, preset_id, preset_sha256)
```

The entire target, saved recipe and retained image evidence is revalidated.
The receipt must exactly match the one retained in this engine session, and it
can be consumed once. The authority's `preset_command` is only:

```json
{"cmd":"preset","action":"apply","id":"color-warm","document_id":"current-load-id"}
```

The parent adds the correlated request identity and uses the existing normal
serialized dispatcher and `PresetController`. It must not replay the review's
candidate itself, call a shadow mutation path, skip normal guards, invent a
success receipt, rewrite history or treat the review receipt as completion.
The parent owns journal correlation, mutation observation and uncertain-outcome
handling. If dispatch is uncertain, query the original operation; do not obtain
another authority and resend the same effect.

The parent must hold the existing preset catalogue transaction lock across
`consume` and normal synchronous dispatch. Otherwise the controller's genuine
store read could observe a different preset after review consumption. The
read-only catalogue recognizes that same-thread lock. Do not upgrade its
temporary shared read lock, and do not dispatch from a rendering/background
thread. The serialized command lane must preserve the loaded-target fence from
consumption to ordinary dispatch. Normal dispatcher revision advancement stays
owned by that dispatcher, not by this review module.

## Retention and failure

Reviews expire after fifteen minutes using the monotonic clock. The session is
bounded to 64 retained review/tombstone records, eight live image pairs, 32 MiB
of cached bytes and 4 MiB per image. A full cache fails explicitly rather than
evicting a pending approval or decreasing image detail. Consuming an approval
releases the image bytes and retains its consumed tombstone until expiry.
`discard(review_id, review_sha256)` cancels only that exact private review.

Lost images, missing/expired receipts, source changes and process restart fail
closed. A serialized receipt cannot reconstruct approval authority. No alternate
source, cloned document, donor masks, donor graph or inferred user approval is
admitted. Tests in `engine/tests/test_workflow_preset_review_unrun.py` are
authored transport/ownership fixtures and remain UNRUN.
