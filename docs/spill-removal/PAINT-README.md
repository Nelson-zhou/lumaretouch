# Direct source-owned spill erase/restore: authored, UNRUN

Baseline: `3eac16c976fcfab2d1855356774a385399b78e2a`.
Requirement: `LNX-REF-PC-32475-C-4bc238dfa1`, under the spill feature
`LNX-REF-PC-32475-C-e999ab085a`. This closes the earlier source-work gap of
requiring a separate local-mask editor merely to draw spill exclusions. It does
not establish full handbook or photographic acceptance.

## Source, not output coordinates

The dedicated read-only `id_spill_paint_source` route freezes the current effective
source identity, complete edit/people identity, document and recipe revision.
It returns a display-only image of the untransformed source and the actual saved
coverage raster. No crop, rotation, perspective, face/body deformation, repair,
replacement background or retouch output is presented as an untransformed source.
The existing generic mask and fringe canvases are deliberately not reused:
their displayed coordinates can include projection or output transforms.

The immutable creative asset is the source for a returned document. Its physical
original remains provenance, not substitute pixels. Original decoding and derived
encoding retain the existing full-source working-space contracts. Unsupported
alpha/HDR is refused, not flattened or clipped to make painting appear available.
A shared `full_source_working` helper makes source locator and full candidate
review apply the same RGB16 source-ICC to working-sRGB conversion. Existing
RGB8 decoded working pixels are not converted a second time. PNG IHDR depth
is detected explicitly. The subsequent [original PNG16 source slice](../png16-source/README.md)
connects genuine decoding and export rather than accidentally using Pillow RGB8.
Genuine PNG16 creative-layer/background-asset import support remains unchanged.
This is source wiring, not numerical, photographic or runtime acceptance.

The source image is reduced only for display, to a longest side of 512 pixels;
true source dimensions remain in the proof. PNG bytes are never image assets,
edit state or exported masks. This locator is not a 100% inspection surface.

The painting surface uses the true source aspect ratio. Points are normalized
against the complete image rectangle, not viewport pixels or a letterboxed
container. Radius is measured relative to the smaller true source dimension;
its two normalized axes therefore preserve a circular source-space brush on
non-square photos. A changed source, document, revision, edit/people identity,
view geometry or interrupted pointer gesture cannot silently rebind a stroke.

## Durable vector semantics

Legacy coverage v1 remains unchanged. Direct painting creates a v2 coverage
binding with the same exact source ownership and independently reviewed vector
recipe. If no manual coverage existed, an internal canonical leading full object
represents coverage=1. It is not a subject matte or evidence of contamination.
An erase therefore works on the first stroke rather than subtracting from zero.
When a manual mask already exists, its ordered source-owned vectors are retained.

The existing original Rust local-mask raster remains authoritative:

- Erase uses `max(current - dab, 0)`.
- Restore uses `max(current, dab)`, not cumulative source-over painting.
- Repeated partial-strength restore does not accumulate above that dab strength.
- Both only restrict independently estimated correction confidence. Restoring a
  region cannot force uncertain pixels to change or alter foreground alpha.

The new route accepts bounded brush intent, never client-generated mask pixels,
a foreign source binding, a full-image object or an arbitrary mask recipe.
Limits include 63 new strokes, 1024 points per stroke, 8192 aggregate retained
points, 64 total retained objects, existing full-source raster work admission,
and the unchanged 64 KiB request cap. Earlier limits can reject a long draft;
the product must say so instead of silently dropping points or downsampling a mask.

## Review and history

Source capture and brush drafts are read-only. The source token authorizes
preparing a candidate only while the captured full identity still matches. A
new capture supersedes the old token; captures expire after five minutes. The draft is appended to the retained
coverage independently, without modifying local-mask objects or any other photo.

The existing full-source before/after render is still required after painting.
The final result is not inferred from a brush outline or a browser approximation.
Only the separate one-use, explicitly reviewed apply token commits the candidate
through the existing single history owner. Undo/redo, dormant persistence, package
handling and per-target scalar transfer retain target-owned vectors; vectors are
not copied across images. Pre-send refusal and uncertain send outcomes remain
distinct, with no blind apply retry.

## Remaining limits and verification

All fixtures and source changes are AUTHORED / UNRUN. No product imports,
execution, inference, build/compiler/typecheck, tests or image-quality assessment
were performed. Validate pointer/zoom behavior, PNG integrity, portrait/landscape
radius geometry, stale-source rejection, RGB16/derived display, coverage replay,
undo/reopen and preview/export parity in local QA.

Per-target visual batch review was not part of this painting slice. The later
[source-only visual continuation](TRANSFER-README.md) adds bounded target pairs
and explicit approval without copying masks. Deep opaque reflections, same-colour foreground ambiguity,
finite solver limitations and all numerical/photographic acceptance from the
[parent implementation](README.md) remain explicit.
