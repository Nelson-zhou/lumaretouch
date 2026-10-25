# Hair chromatic unification core v1

Status: AUTHORED / UNRUN. Original GPL-3.0-or-later source only. No native build,
unit test, integration import, visual acceptance, inference or performance run has
been performed. The sibling `hair_colour` palette/gloss implementation is not
modified or used as a substitute.

## Requirement and deliberate scope

Requirement `LNX-REF-PC-32472-C-fb2fe59a22`, control `PC-32472:13`, comes from
[PixCake's official hair adjustment guide](https://www.pixcakeai.com/guide/32472).
The inspected guide specifies bidirectional unification: left references the hair
ends; right references the roots. The sign contract is therefore negative = tips,
positive = roots, zero = identity. The guide does not specify a numerical method,
reference statistics, or target extent. This implementation is original and does
not claim vendor algorithm, targeting, quality, or learned-AI parity.

V1 measures one manually reviewed person's selected root or tip samples from the
immutable, genuine float32 working-sRGB source. A robust measured chromatic field,
not source RGB and not an additive RGB delta, is subsequently applied to the
CURRENT-stage pixels. The caller supplies a reviewed own-person target mask that
EXCLUDES every selected-reference sample pixel. Other reviewed hair is eligible;
background, face, scalp, other people and selected reference are excluded upstream.
The numerical core cannot recognize a person, hair, roots, tips, or manual approval.
Its validation establishes numerical consistency, not semantic correctness.

This is intentionally chromatic unification, not hair recoloring by palette. It
preserves current linear-sRGB luminance at each pixel (subject to float32 rounding),
including existing luminance texture. It does not reconstruct strands, fill gaps,
blur, change brightness, smooth hair geometry, or remove gray hair. A difference
that is only brightness can remain unchanged. Chromatic variation may be reduced;
"preserve detail" means retained luminance/spatial structure, not every color detail.

## Two independent stages

1. `lrt_hair_unification_measure_v1`: full-source scan, immutable RGB and aligned
   hair/root/tip masks. Root/tip masks are already intersected with reviewed hair
   support and any real semantic confidence. The selected sign chooses the only
   reference measured. The opposite mask may be empty but must still be valid.
2. `lrt_hair_unification_compose_v1`: bounded contiguous CURRENT-stage RGB tile,
   effective target coverage tile, selected reference and the same sign. No halo,
   image neighborhood or original RGB replacement is involved. Tiles have source
   coordinates; a one-row tile is valid. Full-source statistics are never computed
   independently per tile, so the mathematical operator has no tile seams.

The host owns evidence/source/person/transform/grid IDs, freshness, immutable mask
ownership, reference caching, cancellation sequencing, and rejection of stale
results. Recompute after source, root/tip marks, coverage or sign changes. It must
not reuse a reference between people, rasters, color spaces or transformed grids.
Amount magnitude may change with the same reference; sign may not.

If composed after existing `hair_colour`, the pipeline is an ordered artistic
combination: this field acts on palette-modified current pixels while retaining
current luminance. A pre-palette source reference does not promise exact reference
RGB or restoration of original color. Protected sample pixels are protected from
THIS operator, not from preceding effects.

## Availability and refusal

The host must recognize zero before evidence lookup or native loading. Native zero
compose also ignores mask/reference values and copies input bits exactly, including
negative zero and NaN payloads, after structural/budget/cancellation checks. Native
zero measure returns a neutral metadata record that cannot be used for an active
compose. Active invalid or unsupported inputs are refused, not silently clipped or
substituted by the old palette module.

Unreliable selected samples, excessive chromatic dispersion, ambiguous overlapping
root/tip marks, nonfinite/out-of-SDR samples, insufficient budgets, bad tile bounds,
wrong-sign references, output aliases and cancellation return explicit errors.
Every nonzero native return preserves every output byte. Very dark and clipped
highlight samples receive little/no weight; selected evidence without enough
reliable support is refused. These thresholds are conservative original engineering
choices, not calibrated photo-quality acceptance.

## Files

- `core/hair_unification/lib.rs`: dependency-free numerical and C-ABI implementation.
- `core/hair_unification/hair_unification.h`: frozen v1 ABI and status codes.
- `core/hair_unification/Cargo.toml`: isolated rlib/cdylib source package.
- `core/hair_unification/build_hair_unification.sh`: authored, unrun build recipe.
- `core/hair_unification/tests.rs`: authored, unrun native acceptance assertions.

No shared dispatcher, existing core, packaging, product registry or old hair-color
file is modified by this numerical-family work.
