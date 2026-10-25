# Selected-reference body matching runtime

Status: authored, statically inspected, **UNRUN**. No test collection, product
imports, native build, model download, inference, hardware probe or photo-quality
acceptance was performed. The fixtures use explicit protocol doubles, not a
replacement colour algorithm or evidence that a detector found a real person.

## Contract and compatibility

PC-32465:19 has a genuine body path, not a renamed legacy body-to-own-face chroma
operator. `lnx.skin_reference_body_match.v1` supplies a separate portable amount;
`skin_reference_match_body_visibility` is its separately reviewed, nonportable
relation. The source stage is immutable source before repair and portrait edits.
An explicit selected same-photo FaceRef supplies both brightness and chroma. It
may be the body owner's own face, but it need not be. Body-only matching does not
activate the face operation or require a face-only relation as consent.

Old `lnx.skin_reference_match.v1` face amounts, records and solver math remain
unchanged. They never activate body scope. Legacy `lnx.body_face_match.v1` remains
a distinct own-face operation. No saved row silently acquires body consent, and
no new numerical algorithm is counted: this module calls the existing original
Rust `skin_reference_match` fit/apply implementation.

## Public integration points

- `skin_reference_body_runtime.requests(state, asset_sha256)` resolves the complete
  enabled new-operation amount set through the canonical inheritance resolver.
- `prepare_bank(state, asset_sha256, full_source, analyses, *, assets, body_bank,
  application_shape, byte_budget, face_records=(), cancelled=...)` returns a tuple
  of body LocalEffects and facts keyed by owning face-instance ID. Supply the full
  prepared face-reference bank via `face_records` when the face path is active.
- `validate_joint_records(records, *, application_shape, cancelled=...)` checks
  every face/body reference record, source capture, selected reference, duplicate
  owner and BodyRef, and every positive-weight overlap across the full grid.
- `skin_reference_body_composition.apply_records_np` and `apply_records_t` accept
  the complete record bank. They apply only `skin_reference_body_match`, retaining
  face records for joint preflight. NumPy returns `(current_or_owned_result, facts)`;
  tensor composition returns the tensor. `source_shape` denotes the unchanged
  application grid, with exact `(y,x)` crop `origin`.

The host must validate the common selected reference across all resolved active
face/body requests before fitting. Prepare face records first when present, pass
them into body preparation, and keep both phases private until every target and
final cancellation/source-revision fence has succeeded. Do not feed only the
currently selected UI row or only the current crop's targets into either phase.

## Source fit and current-pixel application

The authenticated `portrait_fit_source.FullSource` must come from canonical
original 8/16-bit capture or creative float32 capture, before repair and portrait
edits. Its immutable native float32 working-sRGB bytes, source dimensions, kind,
precision and content digest are checked; a display proxy, writable RGB array or
caller-supplied verification flag cannot replace it. Full native precision means
no extra RGB8 round trip or resized fit source, not inferred precision that was
absent from the original.

For each body, projected *semantic observations* are intersected with that body's
independently reviewed manual scope and protected anatomy. Source body and
selected reference-face windows stay independent, even when they differ in size.
One native fit measures the immutable source populations. It is never repeated
for preview tiles, export crops, zoom or already-retouched pixels. Full-source
and application-grid geometry are rebuilt separately while retaining the original
producer observation; resampling is not new full-resolution inference.

The immutable in-process Parameters bind a distinct BodyRef, owning FaceRef,
selected reference FaceRef, full-source pixel digest, consent digest, source and
application grids, independent source windows, application window and coverage
hash. Parameters retain no source RGB, RGB delta, geometry field or portable fit.
The application coverage has immutable bytes backing rather than just a writable
array with its write flag temporarily cleared.

Application passes *current pixels* and the one measured fit to Rust. Thus repair,
other portrait effects and local current-pixel detail remain inputs, rather than
being replaced with a stale source result. Exact zero amount, outside-coverage
pixels, exact black/white endpoints and neutral transforms retain their bits.
Unexpected native writes to protected pixels cause refusal, not clipping.

## Ownership and one geometry pass

The support module owns real BodyRef/person association verification, manual
review, actual `body_skin` and `face_skin` observations, known-occluder vetoes,
all retained face protection (including disabled/reference/foreign faces), and
foreign-body/manual-scope protection. An operation amount alone grants none of
these. Missing or stale active consent is an error, not neutral fallback or an
invitation to infer the nearest body from a face box.

The runtime additionally claims full-source and application-grid body supports,
then preflights the complete face/body effect bank. Any positive-weight overlap
is rejected, even for the same person; there is no order-dependent blending,
second contribution or alpha-based compromise. The same selected source face
must remain unpainted by the combined matching operation. Ordinary other portrait
families are not treated as ownership conflicts: their edits are the current
pixels this solver preserves as its input.

Run colour stages in the existing source frame before the established one-pass
combined face/body geometry warp. This path neither owns geometry recipes nor
replays/invalidates them. The body support remains attached to the same retained
BodyRef through ordinary body geometry controls; reanalysis or identity/association
changes must require new review instead of silent rebinding.

## Admission, transactions and remaining acceptance

Admission charges retained source/analysis backing storage, body metadata,
prepared face weights, worst-case body weights and freeze copies, support
geometry, native snapshots and private application output before heavy work.
Geometry admission uses the maximum live source/application phase: four projected
semantic planes (16 bytes/pixel), the support module's bounded full-grid work,
and padded measured-face ROI polygon scratch. Native fit is admitted separately
from its actual independent body/reference windows once those windows exist;
there is no blanket native-ROI multiplier across the full source canvas. A
budget failure refuses the operation; it never fits a smaller proxy. Strip-native
apply reuses the single fit with bounded work and keeps output private. A later
body/strip failure or cancellation cannot mutate the input or publish earlier
partial output. Full-grid joint overlap preflight runs even for cropped output.

Authored protocol fixtures cover: body-only/own-or-foreign selected reference;
old face-neutral isolation; native source ROI precision and once-only fitting;
current pixels and crop parity; face/body overlap outside a crop; duplicate body
identity; source/grid/coverage/algorithm/recovery tampering; missing body review
or semantics; preallocation/cancellation; later fit/apply failure; and exact
protected endpoint behaviour. They have **not been run**.

Remaining: runtime verification of host/UI/project integration, optional-native
packaging, Rust numerical tests, source-precision and export-parity
checks, large-image memory/cancellation checks, and explicit multi-person/body
photographic before/after acceptance. Neither this runtime nor its support claims
automatic identity, automatic brightest-face selection, instance segmentation,
new full-resolution inference, universal skin quality or complete AI acceptance.
