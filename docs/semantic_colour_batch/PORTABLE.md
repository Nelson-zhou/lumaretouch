# Semantic-colour portable intent and owned reference resources

Status: source implementation and source-only acceptance fixtures. All runtime,
native, inference, UI, integration, photographic-quality and end-to-end export
acceptance are **UNRUN**. A small colour residual is not evidence of natural skin,
lighting fidelity or photographic quality. No photographs or model binaries are
added to the repository by this work.

These modules are connected through the dedicated semantic-colour native/UI
workflow described in INTEGRATION.md. The generic text-preset transport explicitly
refuses them because it cannot omit the owned photograph or copy target gains.
The owner uses `semantic_colour_portable`, not the single-photo preliminary
`S.portable` helper. Source wiring is not runtime or photographic acceptance.

## Portable intent ABI

`semantic_colour_portable` provides:

- `extract(recipe) -> intent`: require an already committed, reviewed full-image
  source recipe; subtract each retained fitted baseline from the actual editable
  parameters. Does not run a model or fit, install state, or export pixels.
- `check(value) -> intent`: strict finite, bounded, detached intent validation.
  Groups are returned in canonical order.
- `apply_offsets(fresh_recipe, intent) -> recipe`: add the offsets to this
  target's newly fitted baseline and return a detached recipe. The caller owns
  fresh full-float capture, genuine target analysis/fit, proposal-proof renewal,
  target review, resource retention and atomic transaction/history installation.

The exact intent keys are:

```json
{
  "version": 1,
  "algorithm": "semantic-oklab-log-ot-pchip-hsv8-v1",
  "reference": {"source": {}, "render_sha256": "…", "asset_id": "…"},
  "mode": "harmonious",
  "strengths": [100, 100, 100],
  "enabled": true,
  "offset_policy": "recompute-then-user-offset-v1",
  "class_policy": "require-requested-support-v1",
  "groups": [{"id": "global", "enabled": true, "offsets": ["50 finite values"]}]
}
```

This is an explanatory example, not a valid data fixture: source needs the
existing exact `{sha256, width, height}` identity; both digests require 64
lowercase hexadecimal characters; offsets must be 50 numbers. The allowed modes
are `extreme` and `harmonious`, and each strength is independently in `[0, 200]`.
Booleans are not numbers or version integers. Extra fields are refused.

Canonical group order is `global`, `background`, `hair`, `body_skin`,
`face_skin`, `clothes`, `others`. Global is required, even when disabled. The
groups list is the complete requested group set, not a partial update:

- A deleted or omitted class stays absent, even if a fresh target fit supports
  it. Its newly generated target group and target mask are removed together.
- A disabled requested group stays present and disabled. It still needs actual
  class support and a legal baseline-plus-offset result on each target.
- If a requested class has no fresh supported group, the entire target is
  refused with the missing class identities. There is no global-only fallback,
  implicit class re-creation or silent omission.
- Fresh class groups must use `semantic_CLASS` masks with a real retained base
  and no user objects. All masks are inspected, including those belonging to
  disabled groups. Local-only recipes, orphan masks, source-domain bindings,
  brush/linear/radial objects and other user/source-bound mask intent are refused.
  Source masks are never transported or geometrically reinterpreted.

Extraction requires a structurally valid retained saved review, target binding,
real model-analysis receipt, matching owned reference identity and initial-fit
support for every requested group. The existing saved-review record is a
committed-state guard, not a separately reconstructible cryptographic signature
or an independent photographic acceptance. The owner must retain real commit
provenance. Disabled state does not waive any guard.

The intent does not contain the source target binding, masks, fitted parameters,
baselines, diagnostic pixel identities or user-selected regions. Only the owned
reference's existing identity is carried. Names are not portable overrides.

## Offsets, bounds and the exact curve policy

For each of 50 parameters, `offset = source.parameters - source.baseline`.
The finite difference limits are the full differences between legal native
parameter endpoints:

| Indices | Native parameter | Allowed offset |
| --- | --- | --- |
| 0–3 | EV and RGB log2 gains, each `[-2, 2]` | `[-4, 4]` |
| 4–5 | Saturation and contrast `[-100, 100]` | `[-200, 200]` |
| 6–25 | Four five-knot curve ordinates `[0, 1]` | `[-1, 1]` |
| 26–49, every first of three | HSV hue `[-60, 60]` | `[-120, 120]` |
| Remaining HSV values | Saturation/value `[-100, 100]` | `[-200, 200]` |

For every target, `parameters = fresh.baseline + offsets`, checked against the
actual native parameter bounds through `S.parameters`. The fresh baseline is
not rewritten. Any impossible result refuses the whole return value without
clamping, dropping a parameter, scaling offsets or mutating the input. Fresh
parameters must equal their baseline before this operation so that edits cannot
silently accumulate. The mode and owned reference must already match the fit;
the requested strengths and enabled flags are applied to the returned recipe.

The portable monotonicity policy is **native-editable PCHIP compatibility**, not
mandatory monotonicity. This is intentional and follows the real evaluator:

- `core/semantic_colour/colour.rs::validate` requires finite curve ordinates in
  `[0, 1]`, not increasing ordinates.
- `core/curves/curve.rs::compile` explicitly supports intentional non-monotone
  y values. Fixed x knots remain `0, .25, .5, .75, 1`, so their required ascending
  spacing is preserved. PCHIP preserves each interval's endpoint range.
- The automatic fitter has a stricter increasing master-knot constraint and
  penalizes roughness/reversals. That optimizer constraint must not be falsely
  imposed on the user's already permitted manual edits.
- Therefore legal non-monotone manual offsets are retained; impossible ordinate
  bounds are refused. There is no invented `.01` gap constraint on edited curves
  and no claim of overall monotonicity, especially at strengths above 100%.
- Native strength-time curve clamping and non-neutral SDR HSV-band clamping are
  unchanged evaluator semantics. This module does not clamp offset application
  or relabel those native semantics as HDR HSL.

The returned recipe retains target-owned analysis and review fields. The caller
must renew the complete proposal proof after adding offsets. Initial-fit
diagnostics describe the initial fit, not the manually offset output, and must
not be displayed as a re-measured residual or quality guarantee for that output.

## Exact owned-reference transport

`semantic_colour_preset` provides private engine APIs:

- `build(recipe, *, include_reference) -> envelope`
- `check(envelope) -> envelope`
- `hydrate(envelope) -> intent`
- `prepare_export(recipe, *, include_reference) -> PreparedExport`
- `load_file(path) -> envelope`
- `write_prepared(prepared, path, *, overwrite=False) -> metadata`
- `PreparedExport.metadata` returns a detached small dictionary;
  `PreparedExport.close()` removes the private staged file after success/cancel.

Both export entry points require the literal boolean `include_reference=True`
before reading any asset. There is no implicit approval, parameter-only fallback
or reference-image substitution. A future UI must first explain that the export
contains the entire owned sample photograph, ask for explicit inclusion, and
pass the response. Selecting a scope or a source recipe is not this consent.

The private envelope is exactly:

- `schema: "lrt.semantic-colour-preset.v1"`
- `intent`: the checked portable intent above.
- `reference_resource`: `{included: true, asset_id, bytes, chunks}`; `chunks`
  describes each ordered part with exactly `{bytes, sha256}`.
- `chunks`: engine-private immutable, contiguous, 1-D uint8 arrays. These arrays
  must never be serialized to native/UI status, receipts or operation payloads.

The resource is the **existing** `reference_color_assets` NPZ bundle, byte for
byte, obtained through `A.bundle`, not a new RGB format, JPEG, proxy, RGB8 array
or recompressed image. Existing canvas resource admission is reused before
building. The authentic full-float RGB values and authenticity/provenance mask
are retained, together with the original reference metadata. This includes the
owned reference's provenance, not the source target photograph's identity.

Chunks are at most 7,000,000 bytes each, at most 40 chunks, and at most
`A.MAX_BYTES` (256 MiB) in aggregate. Both each chunk SHA-256 and the aggregate
ordered SHA-256 must match the manifest and `intent.reference.asset_id`.
Mutable array input is snapshotted into immutable bytes-backed arrays. No list,
float or object-array coercion is accepted.

`check` and `load_file` check transport integrity only. `hydrate` must be called
before target use: it delegates to `A.hydrate`, including the existing `A.load`
validation of exact NPZ entries, NPY headers/dtypes/dimensions, bounded raw
expansion, finite full-float pixels, authentic mask, metadata, source identity
and render digest. Neither a correct file hash nor a matching residual bypasses
authentic image validation. A corrupt pre-existing cache is an explicit error,
not permission to infer, substitute or re-open a different photograph.

## Disk export and the UI boundary

The `.lrtcolour` file is a bounded standard `ZIP_STORED` transport container with
`manifest.json` and `reference/00.bin` … `reference/39.bin` as necessary. The
parts concatenate to the original NPZ; they are not separate decoded images.
Manifest JSON is at most 64 KiB. Disk input is admitted as a bounded regular
file, using the existing preset-store fd admission pattern, plus `O_NOFOLLOW`
where supported. No ZIP member is extracted to a filesystem path. Duplicate
JSON keys, duplicate entries, unknown/path-traversal members, encrypted or
compressed outer entries, missing parts and inconsistent lengths/hashes are
refused. The inner authentic NPZ retains its existing compression and validator.

Preparation creates a private staged disk artifact. Only its small metadata is
sent to the mounted export UI:

- Schema, `reference_included: true`, exact `reference_bytes` and
  `reference_sha256`.
- Exact total `file_bytes` and `file_sha256`.
- `quality_acceptance: "UNRUN"`.

No photo bytes, chunk arrays or private staging path appear in that metadata.
`write_prepared` copies and hashes the staged bytes again before publication,
rejecting mutation since preparation. Publication uses a same-directory
fsynced temporary file and no-clobber link unless the caller has explicitly
authorized `overwrite=True`. Parent-directory sync and uncertainty reports
reuse `preset_store`'s existing storage semantics. The export owner must obtain
destination/overwrite permission, handle reported commit uncertainty and always
release the private prepared artifact. This low-level module does not own authorization or token lifecycle;
`semantic_colour_workflow` and its mounted panel supply those boundaries.

The existing 256 KiB generic text-preset format remains unchanged. Resource
exports must not be tunneled through that text JSON or native command envelope.

## Source-only acceptance matrix

`engine/tests/test_semantic_colour_portable.py` contains synthetic fixtures for:

- Exact portable fields, canonical ordering, source baseline subtraction,
  independent per-target baselines and preservation of target bindings/masks.
- Deleted-group absence, disabled-state intent and strict missing-class refusal.
- Required committed review/global group, mismatched reference/support, local
  modes, orphan masks, wrong class mask IDs and disabled manual mask objects.
- All native difference-bound families, non-finite/bool/oversized integers,
  unknown fields/groups, duplicate groups and non-integer versions.
- Whole-target refusal for impossible offsets, native-compatible intentional
  curve reversals, and refusal of already edited or wrong-mode/reference fits.
- Explicit full-reference inclusion, chunk/full digests and size integrity,
  immutable byte snapshots, and refusal of non-image bytes despite valid hashes.
- Exact full-float synthetic reference/provenance-mask round-trip through real
  `A.save`, bundle, disk export, import, hydrate and load, including negative
  values, HDR values and signed-zero bits.
- Small metadata, staged tampering, no-clobber/explicit overwrite and malformed
  outer archives.

None of these tests has been executed in this implementation session. Static
AST/source review is not a test pass. Qoder still owns runtime execution, native
regression, packaging and actual UI/photographic acceptance.
