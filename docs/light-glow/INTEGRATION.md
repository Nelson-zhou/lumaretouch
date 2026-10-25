# Light-glow integration ports

The isolated core is AUTHORED / UNRUN. These are integration obligations and
stable interfaces, not claims that host/UI/native work has executed successfully.
Existing creative asset ownership, full-edited-source capture and immutable
derived return are retained; there is no new asset store or undo owner.

## Scalar recipe

Exactly these JSON fields, no extras, finite numbers without coercion:

    {
      "version": 1,
      "operation_id": "lnx.light_glow.v1",
      "math_identity": 65537,
      "mode": "black_mist" | "white_mist" | "glow",
      "strength": 0..1,
      "radius_px": integer 0..512,
      "threshold": 0..1,
      "exposure_ev": -4..4,
      "scattering": 0..1,
      "tint": {"hue_deg": -180..180, "saturation": -1..1, "lightness": -1..1}
    }

No preset id is embedded in the numerical recipe. Buttons expand the local
values in presets.json; edited values remain authoritative, and the UI can
derive a matching preset or display Custom. Mode changes must use the corresponding
declared default or preserve explicitly explained values, not guess vendor values.
All ranges/preset values are Lumaretouch calibration, not official disclosures.

## Required ports and ownership

1. **Capability:** load the packaged native library with exact ABI/math and struct
   size checks. Its presence is not quality/latency acceptance. No successful
   source-copy fallback when unavailable.
2. **Current full edited source:** use the existing
   `creative_document_base.capture_current_asset` architecture and common export
   source pipeline, not the displayed PNG, unedited original or arbitrary path.
   Keep any bounded supported capture routes; unsupported ones reject explicitly
   rather than losing edits. Bind document id, epoch, revision, canonical content
   hash, dimensions/orientation and source identity. Validate **every** source
   pixel is SDR before work, preserving original RGB16 precision. This core does
   not accept signed/HDR creative buffers or silently tone-map them.
3. **Job and tile driver:** freeze source/recipe; admit capture, retained source,
   full output, full coverage, transient region/tile/native scratch and freeze
   copies before allocation. For each 256×256-or-smaller output tile, ask the
   native planner and copy its exact original-grid region. Never sample already
   written output. Keep full result private until every tile succeeds. Native
   cancellation is read/compute-only; no callback can commit host state.
4. **Review:** produce before/after displays from the same full source and finished
   full result, and a green diagnostic derived from actual coverage. Display
   reduction is presentation-only. Carry session/request identity, source owner,
   recipe hash, before/after hashes, native math and immutable candidate token.
   Invalidate candidates when source, revision, controls or owner changes.
5. **Apply:** after matching current source/candidate and explicit review, use the
   existing immutable creative-derived return transaction, preserving the original
   edits. For a new-image-only first slice, label it that way; do not imply a
   retained editable effect layer or whole Apply parity. Reuse commit readback,
   correlated receipts and query-only uncertain-outcome handling; never rerender
   or duplicate an uncertain write. Do not create a second undo stack.
6. **Batch/preset/persistence:** each selected target needs its own full current
   source and effect computation. Copy scalar intent only, never another source's
   halo, coverage or output. Reopening/editable recipes requires deliberate host
   persistence; a baked derived image alone is not an editable effect recipe.

The current creative asset format supports premultiplied float32 signed HDR;
that is a broader contract than this SDR-only core. Existing photo-return guards
may also limit the integrated path to opaque images. Preserve these distinctions.
`require_photo_return` and normal export remain authoritative for publication.

## Native adapter map

Library filename on the current Linux packaging route: `liblrt_light_glow.so`.
Exact struct/function declarations are in core/light_glow/light_glow.h. Planned
source modules use the independent `light_glow_*` prefix and `ui/src/lightGlow/`.
This core delivery does not edit registries, packaging scripts or central UI.

Missing math or changed ABI must preserve saved intent and fail closed. Replacing
a verified module between process lifetimes is supported by the contract; loading
arbitrary shared libraries or live hot-unload is not a feature of this module.
