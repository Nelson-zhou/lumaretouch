# Face-decoration transfer UI: authored, acceptance UNRUN

The preset and ordinary explicit-face-map batch routes show the complete frozen
mixed render, not a partial decoration overlay. Selected decoration, including
zero, requires review. Engine-declared retained active decoration also requires
review even if the selected operation set does not contain decoration. Presets
send the full selected scope without inserting donor decoration parameters.

Both routes share a decoration-specific image-pair component and coverage
validator. Existing image PNG/hash/metadata primitives are reused. Each actual
image side is fetched lazily from its exact immutable token, document, revision,
side and SHA. Preset reads additionally bind the preset ID and load session.
The component requires both PNG hashes and decoded extents, canonical target
coverage digest and an explicit checkbox before enabling confirmation. It
exposes a 1024-edge RGB8 display, not native-resolution or photographic proof.

The coverage binds sorted target FaceRefs, candidate recipe hashes and independent
visible-skin review hashes. It does not carry donor painted support. The complete
candidate retains other local effects; independent eye-bag or collarbone review
families still require their own confirmations when batch mixing is supported.
Single-photo incompatible dedicated review families remain explicit refusals.
The current single-photo planner still requires one explicit enabled face; it
does not guess a target in a multi-person photo.

Changed target, source, recipe, request, token or coverage invalidates confirmation.
Disposed or navigated image reads cannot publish; this is not a claim that decode
or the engine render was interrupted. Unknown apply/commit and protected batch
undo/redo remain query-only, including after hide/reopen. Persisted decoration
batch markers carry exact review digest and affected member count. Partial
restores or conflicting markers do not settle as success. No-op commits retain
explicit null batch identity and do not fabricate history.

Authored fixtures cover exact source/owner/recipe proofs, neutral review, retained
active decoration, single-photo direct-apply refusal, immutable image transport,
late reads, reopened history, malformed and mixed markers, and source wiring.
All fixtures, TypeScript checks, builds, GUI interaction, actual image quality,
undo/reopen/export and memory/performance acceptance are UNRUN. Same-source
aliases and persistent cohorts are not enabled by this slice. Manual visibility
and opaque-SDR renderer limitations are unchanged.
