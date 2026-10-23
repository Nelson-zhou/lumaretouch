# Placeable eye-light material slice: SOURCE ONLY / UNRUN

Original isolated baseline: `30494a6e`. Shared integration baseline:
`e43795633d9336c507b6158ea7495b13b3a6370a`. The isolated slice and canonical host integration are authored in source, but
have not been imported, compiled, executed, tested,
typechecked or photographed. It is not a completed eye family, iris editor, gaze
correction, eye-contact feature, or recovery of original illumination.

## Exact requirement trace

All IDs use prefix `LNX-REF-PC-32470-C-`:

| Suffix | Baseline control | Authored source | Verification |
|---|---|---|---|
| b26336005c | 眼神光 | two original procedural material choices | UNRUN |
| 1ea8023b43 | 程度 | strength, independent additive delta | UNRUN |
| 50dce1838b | 垂直位置 | eye-local translation | UNRUN |
| 9811052624 | 水平位置 | eye-local translation | UNRUN |
| 6280743410 | 旋转 | -100..100 → -180..180 degrees | UNRUN |
| 127642672f | 水平翻转 | material-local horizontal reflection | UNRUN |

Evidence: supplied `manual-text.txt` lines 533–540 and supplied
`AI开发资料包/功能需求验收映射.json` lines 3347–3436. Related module case
PORTRAIT-009 is NOT dedicated evidence for these six controls. Official
https://www.pixcakeai.com/guide/32470 was attempted 2026-10-23 and inaccessible.
No claim of proprietary asset, numerical or visual parity.

## Source-supported versus local design

Baseline supports position -100..100 default 0 and rotation -100..100 default
0 mapping to ±180 degrees. Strength 0..100 default 0, two asset shapes, size,
opacity gain, translations of one measured iris radius at endpoints, positive
vertical image-down, material size and soft edges are ORIGINAL LOCAL
DESIGN, not undocumented official behavior. Both pattern functions are authored
here using arithmetic, with an asymmetric intensity ramp so flipping has a
visible purpose; no downloaded artwork or copied texture. Their source is
GPL-3.0-or-later with the project. They are artistic approximations, not
physically based corneal reflections.

Primary practice verified 2026-10-23:
- GIMP's official mask docs describe opacity controlled per layer region:
  https://docs.gimp.org/3.0/en/gimp-layer-mask-add.html
- GIMP's community-authored tutorial hosted by the project:
  https://www.gimp.org/tutorials/Layer_Masks/ (page opened but no extractable
  body, so not substantive evidence beyond the official mask documentation).
- darktable color-pipeline documentation URLs were inaccessible; do not count
  those as verified or infer a color-space contract for this application.

## Conservative admission

Real 478-point MediaPipe geometry must include observed iris landmarks, 16-point
visible eyelid boundary, source hash, model hash, face hash, person ID and source
revision. Anatomical eye sides are explicit. A separate per-eye visibility mask
must be reviewed against that exact binding, carry a review ID, and explicitly
report no occlusion. The authored EyeLightSupportEditor acquires original-image brush review;
eye_light_support rasterizes its immutable vectors through local_mask_recipe.
The host must not set `reviewed=True` automatically merely because landmarks exist.
Closed, tiny, severely foreshortened, out-of-image or inconsistent iris geometry
fails. Requested double-eye operation is atomic: one rejected eye rejects the
proposal, instead of silently changing one side. Each pixel is gated by the
actual eyelid polygon, measured iris disk, reviewed visible mask and recovery
mask. Eyelid or hidden eye anatomy is never synthesized. Min iris radius 2 px,
width 14 px, aperture 4 px and 0.12 width ratio are local conservative thresholds
requiring photo QA, not universal anatomical guarantees.

## Precision and non-destructive behavior

Rust computes float32 linear-light additive deltas, without source resampling,
8-bit conversion, source clamping or tone mapping. Python composite returns a
new float32 array, preserving out-of-mask pixels and HDR values. RGB16 decode
is an explicit profile-aware host callback; 65535 normalization is not claimed
to decode an encoded transfer curve. Source hashing prevents applying a delta
to a changed source or another person. Export must recompute from the original
full-resolution linear source and full-resolution reviewed masks, never upscale
a preview delta. This is an eye-light-only contribution, separate from existing
`catchlight_left` / `catchlight_right` existing-highlight enhancement.

## Validation status and remaining limits

Only Python AST, JSON parsing, source inspection and SHA-256 enumeration are
permitted in this task. All authored Rust/Python/TS tests are UNRUN. No Rust
binary is bundled. Missing native core fails explicitly; no fallback changes
algorithm. The reviewer and controls are mounted in source; existing people receipts, graph,
immutable support store, history, project, preview/export and recovery paths are
wired as described in INTEGRATION.md. None have runtime verification.
No independent session/history owner is present. PeopleGraphOwner and the
existing transaction/history owner must capture recipe and support pointers. Existing valid same-source review vectors can survive project reload through
the canonical support store; per-target batch needs fresh target review. Numeric outputs, compilation, responsive UI, memory bounds,
quality across skin tones and glasses, full-size export, tile continuity,
project recovery and real-image benchmark acceptance remain unverified.

## Independent and linked eye controls

Recipe schema 2 persists every material control independently for left and right
eyes. Linking explicitly copies the currently selected reference eye to both
sides; all linked changes publish atomically. Unlinking keeps each side intact.
An explicit schema-1 recipe migration preserves original both/left/right intent.
These mechanics implement the baseline left/right-unlock metadata; visual
acceptance and cross-face inheritance edge cases remain UNRUN.
