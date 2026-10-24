# Skin whitening and rosiness: source-only, partial, UNRUN

Baseline: `d43f7831dd8a26e30d44bd575787069c9cdac2d6`.

## Exact requirements and scope

- `LNX-REF-PC-32465-C-d82f09f52f`, 肤色美白: whole-body skin brightness and
  whitening toward a cool-white appearance.
- `LNX-REF-PC-32465-C-60936d5259`, 皮肤红润: increased whole-body skin rosiness.

[Official desktop skin guide](https://www.pixcakeai.com/guide/32465), updated
2026-05-26, checked 2026-10-24. The supplied portrait audit identifies both as
distinct missing skin controls, not generic local grading. Official slider ranges
and proprietary algorithms are not disclosed.

These are separate from exposure, signed temperature/tint, blush makeup, skin
translucence, smoothing, blemish removal and skin unification. No health judgment
is inferred from skin colour. Both requirements remain **partial**: measured face
skin and explicitly reviewed visible body skin are supported by the source path,
but automatic person-instance body segmentation is not supplied.

## Algorithm and ownership contract

`lnx.skin_finish.v1` has independent `[0,1]` whitening and rosiness controls,
neutral zero. These project units are not claimed to match proprietary sliders.
The original Rust operator uses a restrained monotone lightness lift plus
cool-white chroma changes for whitening, and a luminance-gated red-direction
chroma adjustment for rosiness. It does not spatially blur, flatten, synthesize,
or replace texture. Details, formula bounds and numerical limitations are in
`core/skin_finish/README.md`. The existing D65 Lab colour-space conventions are
not CSS D50 Lab or proprietary-colour conformance.

Existing temperature/tint is composed first, then this separate native operator,
each using its own admitted coverage. A single final source-domain delta enters
the existing `skin_colour` stage and one joint body/face geometric warp. Independent
original-source deltas are not blindly added to simulate sequential colour work.
Colour-only projects retain their prior operation, body consent and native ABI.

The real face-skin producer, measured landmarks and conservative neighbour/feature
exclusions remain authoritative. `skin_finish_body_visibility` is a separate
immutable support authorization, binding the same source/FaceRef/BodyRef/person
evidence with new explicit manual review. A previous skin-colour body attachment
does not enable whitening or rosiness. No review vectors or semantic arrays are
copied between people or images. Other owners' manual body regions are reserved
across both families; arbitrary face order cannot decide overlapping ownership.

## Workflow and persistence

New unsigned controls use the existing people graph, resolver, command receipts,
project/virtual-copy ownership and undo history. Both-zero recovery does not
require the new native core. Reference, full-source before/after candidate and
confirmation remain distinct, privately staged steps, with exact operation-family
tags to prevent cross-family receipt adoption. There is no new history owner.

The current real original or immutable derived source drives preview, review and
full-resolution export. PNG16 input retains the existing genuine decode/export
contract. Semantic confidence may be resampled from its producer grid; this is
not fresh full-resolution segmentation. Display PNGs are not replacement source
pixels, reusable edit masks or persistent history bitmaps.

Presets carry only whitening/rosiness scalars. Explicit face-map and confirmed-person
batch preparation uses each target's own support and body bank, with separate
finish coverage disclosure. Missing body authorization is face-only, not inherited
whole-body coverage. Stale active authorization refuses. Generic derived presets
and unadapted persistent-association review flows retain their existing guards.

## Verification and remaining limitations

All fixtures are **AUTHORED / UNRUN**. Static AST/JSON/hash/source checks are not
runtime, numerical, photographic, memory, latency, package or UI acceptance.
No product imports, local tests, compiler/typechecker/build, inference, downloads,
installation or Git writes are performed in this slice.

There is no automatic multi-person body ownership, complete occluder segmentation,
skin-tone standardization, AI blemish repair or texture invention. Manual ownership
can be mistaken, and coarse semantic edges can miss fine skin regions. Native
gamut reduction may reduce saturation; varying coverage and composed effects do
not promise a globally unchanged contrast ordering. Real portraits across lighting
and skin tones, combined colour/finish effects, undo/reopen, source changes,
interrupted receipts, body reassociation, batch and export need independent
runtime validation. Existing opaque SDR bounds remain; HDR and alpha are not
silently clipped or flattened into a support claim.

## Integration map and next validation gates

- `core/skin_finish` and `skin_finish_native.py`: separate original GPL Rust ABI,
  strict float32 SDR boundary, private buffers, resource/cancellation admission;
  `packaging/build-skin-finish.sh` and stage script carry that core and license.
- `skin_finish_state.py`, `people_algorithms.py`, registry and server capability:
  exact unsigned versioned leaves, native availability rather than fake fallback.
- `skin_colour_people.py`, `people_render_runtime.py`, `people_owned_inputs.py`
  and `people_engine_runtime.py`: independent coverage, sequential native work,
  original/derived preview and full-source export before the shared geometry.
- `skin_colour_body_support.py`, `skin_colour_body_host.py`, action routing,
  `people_support_assets.py` and `people_project.py`: separate finish descriptor,
  actual target analysis/body links, private real-image comparison, receipt fences,
  append-only immutable support and historical validation of both families.
- `skin_finish_scope.py`, `people_scope.py`, workflow/scope registries and transfer
  review: only scalar intent moves, with independently resolved target coverage.
- `ui/src/skinFinish`, the two exact `RetouchPanel` leaves, shared parameterized
  body panel, people DTO/workflow/native admission and transfer disclosure:
  source-bound values, explicit manual body review, zero recovery and uncertainty.

Primary mathematical sources and license distinctions are recorded in the core
README. These are standard colour-space tools plus original product coefficients,
not evidence that whitening/rosiness photograph quality has passed acceptance.
The first execution gates are native compilation/fixtures, engine fixtures,
TypeScript/native build, source-family receipt isolation and genuine photo review.
Full automatic body ownership, skin translucence (`7b8b5262ee`), palette
(`2472d3ea69`), unification and blemish-removal requirements remain separate work;
none is counted as implemented by these two controls.
