# Existing eye makeup enhancement: original current-photo implementation

Status: AUTHORED / UNRUN. Baseline given to this lane:
`b655c75a456e620b8ee937ed49756aeff7f9dd88`. This lane has not used Git/GitHub,
executed/imported the product, compiled Rust, run tests/typecheck/build, installed,
downloaded models, performed inference or run a photographic comparison.
Only source reading, authoring and stdlib AST/JSON/hash/source checks are performed.

## Exact feature semantics

The 2026-10-23 original mapping TSV, rows 239–242, was cross-checked against
https://www.pixcakeai.com/guide/32471 read 2026-10-24, headings 眼妆增强 and its
three subheadings. The live guide says each has independent left/right unlinking;
overall goes from fading to enhancing and the other controls adjust saturation,
brightness and dimensionality. Four separate exact control IDs are preserved:

- `LNX-REF-PC-32471-C-ee9394fa95`: existing eye-makeup enhancement/fading.
- `LNX-REF-PC-32471-C-707956d003`: eye-makeup saturation.
- `LNX-REF-PC-32471-C-0985fdcfb9`: eye-makeup brightness.
- `LNX-REF-PC-32471-C-e3b5569011`: eye-makeup structure/dimensionality.

These are not iris makeup, eye brightness, eye-light material, eyeliner, lashes,
new eyeshadow patterns or generic exposure. No official numeric range, algorithm,
asset or appearance equivalence is implied. Internal [-1,1], UI [-100,100], gains,
thresholds and all original source-processing decisions are product policy.

## Method and boundaries

See `core/eye_makeup_enhance/README.md` for actual equations and ABI, and
`THIRD_PARTY.md` for primary technique sources and licence decisions. Oklab and
two-scale texture-preserving adjustment were examined before implementation;
subsequent source review documents the integral/normalized-box specialization.
Existing brow_enhance, lip_makeup and lip_texture families plus canonical support
and decoration-review owners were inspected, not rewritten or aliased.

The operation requires explicit current-photo, current-FaceRef visible makeup
polygons. This is user evidence, not automatic cosmetic identification. Authentic
retained MediaPipe landmarks place conservative periocular boundaries. Actual
face-skin/known-occluder observation, both eye globes, expanded lash-line guards,
brows, mouth, opposite-side mid-face and every other retained face box veto unsafe
pixels. Long lashes and unrecognized occluders still require explicit user exclusion.
Severe asymmetry/profile, clipped geometry, tiny eye, poor support and over-budget
source/geometry are refused. No extrapolated geometry or hidden skin is created.

Amount requires two independently reviewed, disjoint nearby bare-skin regions.
They must agree in measured colour and illumination. Negative amount is a bounded
reduction of estimated low-frequency makeup contrast, not ground-truth skin
recovery or complete removal. Without both references, saturation/brightness/
structure can still be used on reviewed actual makeup; amount fails explicitly.

Each side solves from the same original effective-source float32 RGB; not a
previous effect, retouched proxy, per-tile source or borrowed face. A single frozen
finite readonly LocalEffect delta is produced. Full-resolution export recomputes
anatomy, rasterized normalized vectors and source field, then only crops that field
for tiles. Existing headroom composition preserves one delta direction rather than
independent RGB clipping. Unsupported alpha and HDR must be rejected by the source
owner before conversion; the native/layer boundary rejects non-RGB and out-of-range
values too. PNG16 low bits must reach float32 directly, never through the PNG8
review display. Review PNG8 is only a bounded displayed crop.

## State, ownership and safety

`lnx.eye_makeup_enhance.v1` persists only `{version:1,amount,saturation,brightness,structure}`,
where each control is `{linked:boolean,left:number,right:number}`. Linked sides
must match atomically. Relink requires an explicit chosen common value; no copying
or averaging. Zero returns no layer and requires no model/native/support. A reset
does not erase review, other controls, local materials, source or analysis.

`eye_makeup_enhance_visibility` is a unique source-owned support kind in the
existing immutable people support bank. Draft polygons are session-only until
confirmed; confirmed records persist and reopen under the same exact FaceRef,
original dimensions and landmark digest. Presets/transfer never carry source
polygons, samples or support consent. Missing target-owned review is a refusal.
History owns graph pointers; immutable bank records are append-only and retained
for undo/reopen. Reanalysis or creative-source change invalidates old proof.

Current-photo host/UI deliberately restrict editing to the selected face's
independent target. Shared-source documents are refused by `require_transition` /
`require_unaliased`; no decoration/eye-bag alias authority is borrowed. A future
multi-document confirmation flow would need separate authority and tests.

Source review binds exact document/revision/association/target, source, FaceRef,
landmark digest, actual PNG SHA-256 and reference request ID. UI hashes displayed
PNG bytes and checks decode dimensions before enabling confirmation. Every
polygon change resets explicit consent. Four independent affirmative statements
cover makeup visibility, occlusion, ownership and feature exclusion. Clean-skin
references have their own affirmative statement. Request callbacks use latest
functions while invalidation depends only on real source/owner data, not wrapper
function identities. Uncertain requests use the existing query path, never replay.

## Validation status

Static stdlib AST parsing of authored Python modules was performed. JSON fixtures
and owned hashes are checked at freeze. This is syntax/source evidence only.
The Rust/Python/TypeScript fixtures and full acceptance matrix under `fixtures/`
are AUTHORED_UNRUN. No native availability, Rust compilation, TypeScript type
correctness, live source loading, numerical invariants, cancellation timing,
texture fidelity, preview/export parity, PNG16 quality, performance, browser
interaction or photographic acceptance has been established. This lane alone
cannot claim the parent application is integrated or runnable.
