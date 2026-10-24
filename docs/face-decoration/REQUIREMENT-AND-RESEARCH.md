# Face decoration: original source-local materials

Status: source work in progress; every numerical, UI, runtime and photographic
acceptance remains **UNRUN**. This is not an automatic skin-segmentation claim.

## Exact requirement

`LNX-REF-PC-32471-C-dd14134407`, P1, `局部妆容/脸部装饰`.
The supplied `功能需求验收映射.json` entry has no dedicated acceptance case;
its related `PORTRAIT-010` is not evidence that this control passed. The supplied
handbook `manual-text.txt` lines 541–545 specifies five freckle and three mole
materials. The [official makeup guide](https://www.pixcakeai.com/guide/32471),
read on 2026-10-24, independently confirms those counts and a strength control.
It does not publish a numerical range, algorithm, original material licence,
pixel-identical rendering contract or automatic occlusion guarantees.

One new operation is proposed, not eight new algorithms. The eight versioned
designs are original Lumaretouch marks, not copies of commercial thumbnails or
source materials. Adding decorations does not remove existing freckles, moles
or makeup and does not implement the separate makeup-reduction requirement.

## Mature technique and licence boundaries

* [MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
  describes measured face landmarks and facial effects. The already pinned
  project analysis supplies the actual face observation. Landmark availability
  alone is not visibility, instance skin segmentation or anatomical certainty.
  The [upstream code licence](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE)
  is Apache-2.0; existing model/code provenance remains independently required.
  No new weights, runtime, model download or inferred person identity is added.
* [GIMP brushes](https://docs.gimp.org/3.0/en/gimp-concepts-brushes.html)
  demonstrates the mature separation between mark shape, coverage and colour.
  This implementation uses original analytic marks instead of importing GIMP
  brush assets or code. GIMP documentation and artwork are not redistributed.
* [W3C compositing](https://www.w3.org/TR/compositing-1/), the 2024 Candidate
  Recommendation Draft, distinguishes coverage/compositing from blend functions.
  It is a mathematical design reference, not a claim of CSS renderer identity.
  The page identifies the W3C permissive document licence. No prose or code is
  copied into the renderer.

New implementation and original catalogue use GPL-3.0-or-later, consistent
with this repository. No proprietary textures, photos, face meshes, competing
product assets or third-party brush packs are extracted or shipped.

## Proposed source contract

`lnx.face_decoration.v1` carries only version, original pattern identifier and
strength. Strength zero is exact neutral and must not require native loading,
semantic inference or review support. Active rendering requires current verified
face observation, actual effective original/derived source pixels, measured skin
and known exclusions, plus decoration-specific painted visible-skin ownership.
The same source vectors are rasterized at the requested render resolution.

The source-local frame and marks are separate from blush geometry: the existing
blush renderer excludes the nose corridor and assumes bilateral cheek coverage,
which is unsuitable for across-nose freckles or a single beauty mark. Own
geometry must protect eyes, lips, brows, nostrils, neighbouring faces and source
edges, while allowing only actually reviewed visible skin. No complete semantic
occlusion or 3D wrapping claim follows from those conservative checks.

Marks are evaluated by a separate bounded Rust float32 kernel with source-pixel
coverage integration, immutable input and a separate contribution buffer.
Current portrait source admission remains opaque SDR working-sRGB. This does
not introduce alpha/HDR support or quantize PNG16 master pixels to RGB8.
Preview images are display evidence only, never master masks or rendered output.

Only scalar intent may transfer. Every target must rebuild its own coordinate
field and validate its own reviewed source support. No donor face coordinates,
mask, recovery vectors, pixels or analysis may be copied. Existing shared-owner,
cohort, unknown-receipt and dormant-history restrictions must not be bypassed
just to expose a new pattern selector.
