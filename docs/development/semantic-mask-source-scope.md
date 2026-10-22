# PC-32454 semantic-source slice (2026-10-22)

Status: implementation written, not executed or accepted. No build, typecheck,
tests, application run, new weights, or downloads in this slice.

## Frozen requirement mapping

Checked `handbook-traceability.json` controls PC-32454:1–9 and :16 against the
supplied handbook section 局部调色 and AI package 功能需求验收映射.json plus
图片交互细节补充.md. The screenshot evidence explicitly does not establish the
algorithms of smart/free/quick AI selection.

| Control | Honest coverage / remaining work |
|---|---|
| 1 主体蒙版 | Partial portrait categories only. Not generic subjects or individual person instances. |
| 2 宠物蒙版 | Not supplied by the six-class model. Requires a pet-aware source or explicitly prompted selection; generic prompted masks alone do not classify pets. |
| 3 背景蒙版 | Partial portrait-background class 0, not sky/grass/water/building semantic classes or generic object-aware background. |
| 4 自定义蒙版 | Retained recipe container supplied by the composable-mask slice. |
| 5 AI选区 | Container; semantic-category selection does not implement every child mode. |
| 6 智能选区 | Not implemented by six-class segmentation. Requires a genuinely promptable image selector and UI. |
| 7 自由选区 | Not implemented by these sources; needs its own retained free-selection interaction, not an AI label on a manual brush. |
| 8 快速选区 | Not implemented by these sources; requires defined interactive selection behaviour. |
| 9 边缘调整 | Existing recipe feather is not full smoothing/expand/shrink edge editing. |
| 16 智能主体 | Only the explicitly named union of known portrait categories. No generic-subject claim. |

No requirement status is promoted to complete by this document.

## Implemented source contract

`semantic_sources.py` validates existing six-class outputs, copies runtime-owned
buffers, retains class 0 background, 1 hair, 2 body_skin, 3 face_skin, 4 clothes,
skin = 2+3, and portrait_parts = 1+2+3+4. Class 5 others is not relabelled as
person or background. All planes cover the entire image, not the selected face.
478 face landmarks are geometry, not person-instance segmentation.

`FacePrecompute.semantic_model_sha256` identifies the actual segmentation graph.
The loader reads at most 64 MiB plus a sentinel byte, rejects empty/oversized
assets, hashes the immutable bytes and gives those same bytes to the official
[BaseOptions model_asset_buffer API](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/BaseOptions).
It never hashes one file and then asks native code to reopen a potentially
replaced path. Synthetic/template/older producers default to no identity; model
identity is preserved by face selection. Saved semantic bindings must use this
actual identity rather than a manifest hash or the selected face box.

`face.py` retains these planes in `FacePrecompute.masks`. Existing skin/clothes
processing is preserved: probability aggregation, resize to requested image
shape, then conservative edit weight max(2p−1,0). Labels explicitly say portrait
model/category. Missing inference is not replaced with inverse skin, an ellipse,
or a whole-frame mask. The existing backend still requires detected face geometry
before segmentation, so no-face inputs remain unavailable in this slice.

The composable-mask owner integrates `kind=semantic, channel=<stable name>` with
editor, undo, project state and export. Dependency absence must suspend the whole
consumer, including a missing subtraction operand. Valid all-zero probabilities
mean an empty selection, not an unavailable source. Export resamples the actual
model field to the output grid; it must not claim new full-resolution model detail.

## Separate next-model proposal, not shipped

Choose one image-only SAM 2.1 Hiera Tiny adapter for retained positive/negative
click and box prompts; no video tracking or model marketplace. Official
[SAM 2 repository](https://github.com/facebookresearch/sam2) supplies image
prediction and Apache-2.0 licensing. The official
[checkpoint page](https://huggingface.co/facebook/sam2.1-hiera-tiny/blob/main/sam2.1_hiera_tiny.pt)
publishes SHA256
`7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`.
This is published evidence, not a locally verified download.

Integrate with `docs/model-licenses/models.json`, its existing staged-weight
hash/size/license gate, and `engine/src/lumaretouch_engine/data/`. Pin both the
upstream code/config and checkpoint revision, archive licensing, fetch only this
asset and verify bytes before enabling. Do not run an implicit auto-download on
photo open. Existing MediaPipe model-directory override must not become a
silent fallback to different SAM weights.

Use `SAM2ImagePredictor.set_image` on immutable source RGB, then `predict` with
point coordinates, foreground/background labels and XYXY box prompts. Retain
normalized prompts, source digest, model/config identity and selected candidate;
recompute at export, with cancellation and stale-result guards. Keep model
inference in its supported Torch implementation; use existing Rust for bounded
composition/raster work. CPU float32 and CUDA are distinct visible device modes;
measure resource/latency limits before promises. This proposal is not an
implementation or a claim of acceptable CPU performance. SAM masks have no pet
class semantics and do not by themselves finish automatic pet/subject controls.
