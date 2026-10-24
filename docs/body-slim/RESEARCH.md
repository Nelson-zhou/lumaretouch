# Whole-body width: independent research and implementation boundary

Research date: 2026-10-24. Exact requirement: LNX-REF-PC-32473-C-bc54b9eb3c (瘦身).
Baseline revision supplied by parent: b655c75a456e620b8ee937ed49756aeff7f9dd88.
Status: AUTHORED / UNRUN, isolated family interfaces pending shared integration. Not photographic, performance, ABI or release acceptance.

## Requirement evidence

- The baseline manual, full-body section, distinguishes slimming, height, small head, waist and leg tools. The frozen audit marked B02 missing because no independent whole-body width operation existed. The exact original mapping is control bc54b9eb3c / PC-32473 / 瘦身 / P1.
- Official desktop help: https://www.pixcakeai.com/guide/32473 . Direct fetch timed out; the web search index returned that exact official page, updated 2026-09-17, and its slimming subsection. It describes one whole-body shape control with left wider/right narrower. It separately describes AI shaping, small head, waist and leg controls. Neither an algorithm nor this implementation's numeric limits are disclosed there.
- Corroborating official page: https://www.pixcakeai.com/guide/202670 (2026-06-15). It gives the same direction. It is not substituted for the desktop requirement identity.
- No proprietary code, model, image, private API, UI asset or training data was copied. Official behavioral evidence is not license to reuse their assets.

## Mature methods considered, not silently imported

1. Schaefer, McPhail and Warren, Image Deformation Using Moving Least Squares (SIGGRAPH/TOG 2006): https://doi.org/10.1145/1141911.1141920 ; author-hosted paper https://people.engr.tamu.edu/schaefer/research/mls.pdf . The primary paper describes affine/similarity/rigid MLS driven by points or segments. Those are useful interactive deformation primitives, but do not establish actual instance ownership, exact compact background support or injectivity for this application. We therefore use a narrower original, analytically bounded horizontal field. No paper code/assets were copied.
2. Floater, Mean Value Coordinates (2003): https://www.sciencedirect.com/science/article/pii/S0167839603000025 . Polygon/cage coordinates are relevant mature interpolation research. They still need independently established silhouette ownership and deformation constraints. No implementation from the paper was copied or installed.
3. MediaPipe Pose Landmarker primary guide: https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker . It provides body landmarks and optional pose segmentation. This existing repository's actual33 acquisition is reused only as observed landmarks. We do NOT treat joints, their bounding box, optional segmentation or detector count as proof of a complete single person's silhouette. Its primary source license is Apache-2.0: https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE . Existing reviewed manifest/acquisition pins and notices remain untouched. No inference/download/install performed.
4. SAM 2's primary repository describes prompted image/video segmentation: https://github.com/facebookresearch/sam2 . Its core LICENSE is Apache-2.0: https://github.com/facebookresearch/sam2/blob/main/LICENSE ; repository also has third-party license obligations. Prompted segmentation is useful future candidate evidence, not a guarantee of identity, contour completeness, hair detail or occlusion ownership. No SAM code, checkpoints or new dependency are added by this family. Existing arm SAM behavior is unchanged.

## Original bounded choice

The user must trace the complete actual visible silhouette, not a box or generated joint hull. Store 8–128 simple polygon vertices with the exact source/BodyRef/pose digest, explicit current confirmed FaceRef and full face evidence digest. All 33 actual points must be visible, inside the polygon, and compatible with the deliberately limited upright/near-frontal posture. The face rectangle must lie inside without crossing a concave contour edge. The outer rectangular collar must strictly contain the measured silhouette with sufficient room.

The polygon's true extrema measure complete-person width and define a common whole-person horizontal scale, including complete hair/head, torso, arms/hands, legs and feet. Background gaps within that measured envelope and the explicitly reviewed collar deform as disclosed. This is not a claim that every background pixel stays fixed. The exact compact collar exterior is identity. Signed amount a in [-1,1], zero default, width factor 1-0.08*a and all numeric safety limits are original project policies, not copied commercial parameters.

The native field produces only inverse displacements. It composes with the existing body/face common map, whose one original-source sampler remains the sole image resampling stage. No old numeric core changed. Input is opaque SDR RGB8/RGB16/finite normalized float32 via the existing common pipeline; alpha/HDR/RAW values outside supported contracts must be refused, never silently flattened, downgraded or clipped.

## Explicit limitations

- Manual-assistance 2D implementation, not automatic AI shaping or commercial quality equivalence.
- Single-person source only. Every other retained body or foreign face, including disabled/unresolved entries, blocks this family. A missing/truncated detector run blocks it. A manual source-wide single-person confirmation is still required because detector completeness is not claimed.
- Complete visible head/hair, hands and feet are required. Crops, occlusion, crossings, contacts/held objects, strong tilt, rotation, perspective foreshortening, incomplete/ambiguous outline or insufficient collar are refused. No hidden anatomy completion.
- Width uniformity deliberately changes head aspect along with the rest of the person. Height remains unchanged. This is not an independent small-head, waist-width, leg-width, posture smoothing, AI body-shaping, 3D or generative edit.
- No real-photo suitability, detector recall, segmentation quality, latency, memory/performance target or preservation guarantee has been accepted. Source checks and mathematical reasoning are not image tests.
