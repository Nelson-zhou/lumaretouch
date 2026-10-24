# Face-skin texture and sharpening: source only, partial, UNRUN

Baseline `55e0b2540d2975e95322336a8165719352d53939`.

## Exact semantics and actual gap

- `LNX-REF-PC-32465-C-1c80d411ce`, 皮肤质感/纹理度: reduce/increase skin texture.
- `LNX-REF-PC-32465-C-46e0c819b6`, 皮肤质感/清晰度: skin sharpening, not coarse
  photographic local contrast.

The [official PC32465 guide](https://www.pixcakeai.com/guide/32465), updated
2026-05-26 and read 2026-10-24, does not disclose ranges, frequency boundaries or
algorithms. Unlike its explicitly facial gloss description, these two paragraphs
do not establish a face/body coverage guarantee. This implementation is explicitly
measured-face-only; broader body coverage remains incomplete. The surrounding
skin-texture presets/family are not counted as accepted.

There were already related mathematical primitives, not these dedicated workflows:
`ops/guided.py` scales its finest RGB residual inside legacy four-band smoothing;
that UI explicitly does not follow selected-person/group scope. `extended_tone`
has global texture and coarse clarity; `photo_detail` supplies whole-image
sharpening. Neither constitutes this per-FaceRef recipe and anatomy-owned source
path. This work does not claim to invent multiscale filtering or replace those
existing operations.

## Primary methods and licenses

- [Max Wendt, Adobe ACR Texture](https://blog.adobe.com/en/publish/2019/05/14/from-the-acr-team-introducing-the-texture-control)
  distinguishes middle-frequency texture from finest-detail sharpening and warns
  that noise may occupy the middle bands. This informs band separation only;
  Adobe Clarity is not the requested skin-sharpening semantics.
- [darktable contrast equalizer](https://docs.darktable.org/usermanual/4.6/en/module-reference/processing-modules/contrast-equalizer/)
  describes independent luminance bands and warns of noise, halos and gradient
  reversals. Edge-aware processing is not an unconditional quality guarantee.
- [He, Sun and Tang's author project](https://people.csail.mit.edu/kaiming/eccv10/index.html)
  describes local-linear guided filtering. Support-normalized source log-luminance
  decomposition, gates and bounds here are original adaptations, not an unchanged
  reproduction of that algorithm.

No proprietary coefficients, external code, paper prose, image, model or dataset
is copied or vendored. Original code follows GPL-3.0-or-later, with the project
license staged beside the core. Public descriptions are not software reuse grants.

## Operation, ownership and numerical scope

`lnx.skin_texture.v1` accepts exactly
`{version:1, texture:-1..1, clarity:0..1}`, neutral zero. These ranges and band
choices are original product design, not commercial equivalence.

Actual effective source, face-skin observation, retained 478-point landmarks,
feature exclusions, other-face exclusions and unresolved-neighbour vetoes are
required. No merged skin, rectangle or body review is promoted to face authority.
Per-target neighborhoods are scaled from measured anatomy and computed from real
source context, not a viewport-sized cache or enlarged proxy residual. Earlier
canonical repair replay is retained in the pre-skin source reference.

The Rust operator uses source-owned, mask-normalized two-scale log-luminance
decomposition. Texture adjusts a medium residual; clarity boosts a finer one.
Source reference determines bands/gates independently of sliders and earlier
skin colour edits. Correction acts on the ordered current colour → finish →
gloss intermediate, not an edited copy that replaces it. These filter responses
overlap and are not claimed to be orthogonal Fourier bands. Exact equations,
radius/halo, resource limits and ABI are in `core/skin_texture/README.md`.

Encoded working-sRGB float32 SDR is the boundary. Core correction uses a bounded
common linear-RGB gain, with no channel clipping, implicit RGB8 conversion, alpha
flattening or HDR acceptance. Core guarantees apply to its private input/output,
not arbitrary combinations with every other pipeline effect.

## Actual pipeline headroom correction

Prepared skin effects remain one source-domain delta before the common warp.
The actual pipeline input at this stage may already differ after smoothing,
fabric and light work. Previously `people_pipeline.source_effect` channel-clipped
that sum, so an unclipped native core did not establish end-to-end unclipped
composition. This slice changes only the skin stage to use
`people_skin_composition.apply`.

It chooses one feasible scalar per pixel against the actual upstream RGB
headroom, preserving the prepared encoded-RGB displacement direction. It does
not independently clip channels. A fully feasible vector is unchanged; limited
vectors receive a small numerical interior margin. Zero components keep original
bits, blocked vectors may have no effect, and invalid active upstream pixels
refuse rather than silently clip HDR. Other portrait stages retain their existing
behavior. This does not promise perceptual hue preservation, exact native contrast
ratios after other effects, or photographic equivalence to the prior clipping.

The helper runs on the existing Torch device and adds pointwise temporary buffers
and validation synchronizations. No GPU/CPU latency, memory or quality acceptance
is inferred. Full-frame/tile equivalence is an authored, unrun contract.

## Persistence, transfer and remaining acceptance

The existing canonical people graph, command receipts, history and shared geometry
remain the only owners. Presets and confirmed/explicit people transfer carry only
the two scalar values. Every target uses its own support, source pixels and scale
through the actual full-source renderer; no detail or analysis field is copied.
Generic derived preset admission remains guarded. Original and derived source
paths and genuine PNG16 decoding/export remain shared with existing rendering.

The UI reports selected-face effective values separately from the chosen write
scope, retains revision/ownership/pending/uncertain fences, and allows explicit
zero recovery without native readiness or valid active anatomy. No body review,
AI blemish removal, texture synthesis or recovery of missing detail is implied.

All fixtures are AUTHORED / UNRUN. Required independent checks include native
compilation, Python/TypeScript/native UI tests, frequency responses, strong edges,
halos, noise/pores/JPEG artifacts, diverse skin tones, support boundaries, source
replacement, original/derived/PNG16 preview/export, per-target transfers, undo,
headroom interaction with smoothing/light, cancellation and resource behavior.
Static AST/JSON/hash/source checks are not functional or photographic acceptance.

## Integration map and static release gate

- `core/skin_texture`, `skin_texture_native.py`, `skin_texture_state.py`: dependency-free
  Rust, checked ABI/snapshots, strict scalar intent and honest readiness.
- `people_algorithms.py`, `people_render_runtime.py`, `skin_colour_people.py`:
  existing canonical graph resolution and one ordered, source-domain skin effect.
  Geometry remains owned by the common portrait warp, not a new texture warp.
- `people_pipeline.py`, `people_skin_composition.py`: actual upstream skin-vector
  feasibility only. Other stages' behavior is deliberately unchanged.
- `creative_derived_effects.py`: the exact new operation is admitted to its genuine
  effective-source consumer. No original-image analysis substitution or broad
  generic-derived-preset guard removal.
- `skin_texture_scope.py`, `people_scope.py`, `scope.py`, `workflow_ports.py`:
  scalar capture/replay, strict target rendering and canonical rollback. Existing
  confirmed and explicit people mappings reach target candidate validation and
  full rendering; source detail fields cannot be portable preset data.
- `ui/src/skinTexture`, `RetouchPanel.tsx`, native/people/preset labels: exact two
  leaf controls and existing request/history ownership, not a second document.
- `packaging/build-skin-texture.sh`, `stage-engine.sh`: offline native build recipe
  and staged Rust source/header/license. These scripts were not run here.

Static release checks cover Python AST parsing without imports, registry JSON and
core TOML parsing, whitespace, file hashes and source review. App/main/server
ceilings stay unchanged. None of these checks establishes that Rust compiles,
TypeScript typechecks, the application launches, the model observes real skin,
24 MP work fits the available machine, or real photographs improve. The frozen
manifest records exact source bytes; acceptance still belongs to later authorized
build, numerical, integration and representative-photo testing.
