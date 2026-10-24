# Face-skin gloss: source implementation, acceptance UNRUN

Baseline `ef886aab12b99c58a7a1b3e05dbc23323e7ca4a4`.

## Exact requirement and nonduplication

`LNX-REF-PC-32465-C-1eed7cf9a9`, 皮肤质感/光泽度, is the sole requirement in
this slice. The [official skin guide](https://www.pixcakeai.com/guide/32465),
updated 2026-05-26 and read 2026-10-24, specifies adjustment of existing facial
skin highlights, suppressing in one direction and strengthening in the other.
The supplied requirement mapping has this exact path, without a feature-specific
acceptance case. Related module cases do not prove implementation or acceptance.

`lnx.skin_gloss.v1` has exactly `{version:1, amount:-1..1}`, with zero neutral.
This product scale is original, not a commercial numerical-equivalence claim.
Whitening/rosiness and temperature/tint are separate pointwise colour operations.
Hair gloss, lipstick textures and eye highlights are not face-skin gloss.

No texture (`1c80d411ce`), clarity (`46e0c819b6`), matte/satin/water presets
(`80f7de9fa2`, `af15645758`, `04ca6ff5c3`), oil/sweat removal, skin translucence,
body treatment or synthetic relighting is counted by this implementation.
The audit's broader skin-texture package remains incomplete.

## Source and anatomy contract

Only the current immutable original or genuinely derived effective source can
provide highlight evidence. Evidence is measured from original-stage pixels,
never from a previous slider result or the colour/whitening intermediate.
The correction consumes that intermediate in the established ordered skin stage,
not a second independently original-based additive effect. The final single delta
enters the existing common body/face deformation once.

Here original-stage reference means the established pre-skin effect source in
the canonical render, including correctly replayed repair work when present. It
does not bypass earlier nondestructive repair history to read a different bitmap.

Actual face-skin semantic observation, exact source/FaceRef, measured landmarks,
feature exclusions, all other-face exclusions and unresolved-neighbour box vetoes
remain required. Merged skin or a face rectangle cannot substitute for evidence.
Body-support descriptors do not extend gloss. Local statistics and edit support
are restricted to this independently owned facial skin; unrelated image pixels
cannot provide the diffuse reference. Semantic resampling is not new full-source
segmentation, and the existing six-class model is not complete occlusion handling.

The native boundary is encoded working-sRGB float32 SDR. Estimation and neutral
light correction operate in linear light internally. The reference and current
image share an exact grid; neighborhood radius comes from measured face scale,
not viewport or tile size. Genuine source halo must be supplied before cropping
the final effect. Export recomputes from full-resolution source, not an enlarged
preview mask/delta. Existing PNG16 decoding remains intact; no RGB8 replacement,
HDR clipping or alpha flattening is introduced.

## Primary technique evidence and reuse limits

The operation is an original bounded appearance edit, not physical recovery of
diffuse albedo or a calibrated specular component. Exact equations, coefficients,
resources and ABI are documented in `core/skin_gloss/README.md`.

- [Tan and Ikeuchi's author results](https://tanrobby.github.io/research/separation/results.html)
  document wrong-illuminant and near-achromatic failures and exclusion of saturated
  pixels. Its linked implementation license was not established; no code is used.
- [Liu et al., CVPR 2015](https://www.cv-foundation.org/openaccess/content_cvpr_2015/papers/Liu_Saturation-Preserving_Specular_Reflection_2015_CVPR_paper.pdf)
  describes the under-constrained separation problem and hue/saturation ambiguity.
  It motivates conservative bounds, not a claim to implement that optimizer.
- [Yang, Wang and Ahuja's institutional publication record](https://experts.illinois.edu/en/publications/real-time-specular-highlight-removal-using-bilateral-filtering/)
  describes locally smooth diffuse-chromaticity estimation. The full paper could
  not be fetched in research; no complete-paper or code-license claim is made.

No external code, paper prose, image, model or dataset is vendored. Original local
math and boundary patterns follow the project's GPL-3.0-or-later convention.
Commercial documentation supplies semantics, not an implementation license.

## Limits and independent acceptance gates

Missing or ambiguous observable highlight evidence produces unchanged pixels,
not invented highlights or whole-face exposure. A single image cannot reliably
separate pale skin, makeup, colored/mixed illumination, diffuse bright patches,
glasses, pores and specular reflection in every case. Clipped texture cannot be
recovered. Conservative thresholds may miss real broad or weak highlights.

All fixtures are AUTHORED / UNRUN. Source/AST/JSON/hash checks are not imports,
compilation, tests, inference, photo acceptance, memory or performance validation.
Required later checks include signed direction, neutral/protected-bit identity,
original-reference independence, no pore/noise amplification, neighbor isolation,
source changes, original/derived RGB16 preview/export, undo/reopen, per-target
scalar transfer, cancellation, memory bounds and diverse real-portrait review.

## Integration map

- `core/skin_gloss`, `skin_gloss_native.py`, `skin_gloss_state.py`: independent
  source-reference/current-image ABI, exact signed scalar and actual availability.
- `skin_colour_people.py` and `people_render_runtime.py`: face-only admission,
  original reference, measured processing scale, ordered correction in the one
  existing source effect and full-source work before the common geometric map.
- `people_algorithms.py`, `creative_derived_effects.py` and `server.py`: exact
  canonical operation and derived-source admission, no broad guard exemption.
- `skin_gloss_scope.py`, `people_scope.py`, `scope.py`, `workflow_ports.py`:
  scalar-only preset transport, target-owned analysis and strict canonical replay.
  Existing explicit/confirmed people-transfer planners validate each candidate
  through the real full-source renderer. They do not copy highlight fields.
  Generic derived preset admission remains unchanged and guarded.
- `ui/src/skinGloss`, the exact `RetouchPanel` leaf, native readiness DTO, people
  and preset labels: signed control, effective selected-face readback, explicit
  write-target provenance, pending/uncertain fences and zero recovery.
- `packaging/build-skin-gloss.sh` and the stage script: build source and GPL
  notice inclusion only; no build or install was run during this work.

No new persistent highlight bitmap, body authorization, source replacement,
history owner or alternate geometry pipeline is introduced. The original file
remains untouched; source-owned transient estimates are recomputed for each
actual target and render extent.
