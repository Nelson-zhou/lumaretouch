# Prompted AI selection: connected implementation, not acceptance

Written 2026-10-22. This package was developed under a code-only instruction.
No application launch, model installation, checkpoint download, inference,
build, typecheck, regression suite, quality evaluation, or hardware benchmark
was executed. In particular, the published checkpoint SHA256 is not a claim
that its bytes were downloaded or locally checked during development.

## Frozen requirement scope

`handbook-traceability.json` identifies PC-32454:5 as 自定义蒙版/AI选区 and
PC-32454:6 as its 智能选区 child. The frozen screenshots establish controls,
not their proprietary algorithms. This implementation chooses genuine local
positive/negative point and XYXY box prompting, not a manual brush renamed AI.

The package does **not** complete automatic pet classification, generic automatic
subject selection, sky/grass/water/building categories, free selection, quick
selection, or full edge expand/shrink/smoothing. PC-32454:2, :7, :8, :9 and :16
are not promoted to complete. No independent-acceptance statuses are changed.

## One retained mask stack

- `kind=prompted` lives in the same canonical local-mask stack as brush, gradient,
  range and MediaPipe category objects. Its `selection` retains normalized
  prompts, selected candidate, inference device, input digest and actual loaded
  checkpoint/config/code identity. Global `semantic_owner` remains MediaPipe-only.
- A transient lowering maps prompted objects to private float fields for the
  existing bounded Rust compositor. It never persists a proxy raster, adds a
  second mask/history stack, or aliases a semantic pet/person class.
- Name, opacity, feather, enablement, order and deletion use existing reviewed
  mutation receipts, undo/redo, document state and project serialization. A client
  cannot insert or rewrite prompted provenance via an ordinary upsert.
- Missing active input suspends the whole consumer, including subtract and
  intersect. Disabled objects require no optional model. No fallback to full
  image, inverse skin, guessed geometry, or another checkpoint is supplied.

## Review before apply

The normal source-input capture must first be displayed. The AI dialog then
shows the canonical **uncropped/unrotated** original source, explicitly not the
edited photo. Positive/negative clicks and a rectangle use this image's actual
contained image bounds. Each prompt change invalidates the previous candidate.

The engine owns previews, not the UI. Results have a unique preview ID and all
existing capture/document/recipe proof fields. Candidate presentation is
acknowledged after the mask canvas paints; Apply waits for that specific server
acknowledgement. Only explicit `accept_prompted` redeems the reviewed engine
candidate into the canonical edit/history path. Late results, changed photos,
source replacement, cancelled captures and changed recipe revisions cannot apply.

The preview is an owned offline subprocess, bounded by 64 MP source, 4 GiB input
file, 64 clicks, 2048-long-edge SAM adapter input, 1024-long-edge displayed image,
8 MiB result and 180-second wall deadline. Cancellation kills and reaps only the
owned worker. A conservative available-RAM admission reserves source buffers
plus 2 GiB; this is not a measured minimum or performance claim. At most eight
prompted objects may be enabled. Reduced cache fields are bounded and disposable.

## Full-quality export

Prompt inference reads the same immutable file and a canonical full decode:
RGB8 for an 8-bit photograph; true RGB16 for RAW/high-bit-depth input, with the
existing working-sRGB ICC conversion. Only the SAM adapter makes an RGB8 copy.
Its bounded input digest therefore does not depend on whether the requested
output is JPEG8 or TIFF16. Neither processing nor export is replaced with that
copy. An export/inspection regenerates enabled candidates, verifies identities,
and resamples the actual model field to the source grid before ordinary local
composition. Resampling is not new full-resolution model detail.

CPU FP32 and the explicitly requested Torch GPU path are supported in code.
CUDA and ROCm are reported from actual Torch runtime identity; absence fails
visibly rather than silently changing device. CUDA-only connected-component
hole/sprinkle postprocessing and model compilation are disabled. No CPU/GPU
latency, GPU memory requirement or quality promise has been established.

## Explicit optional installation

The AI panel offers installation/status/progress/cancellation. Only Install
starts the native-shell helper with fixed module arguments and the selected
engine interpreter. It accepts no photograph path. The image engine and its
children keep their existing enforced network denial; it is never weakened for
model installation. Photo open and status reads never download anything.

SAM, its optional dependencies and pinned build tools go into an isolated
optional target; the selected engine Torch/torchvision/NumPy/Pillow are not
replaced. The official pinned checkpoint is streamed with an exact byte ceiling
and SHA256 gate, then the directory is published atomically. Failed/cancelled
staging is removed. A pre-existing invalid installation is reported, not silently
deleted or adopted. Inference re-verifies actual checkpoint/config bytes and
loads those same immutable buffers, avoiding hash-then-reopen races.

See [official provenance and pinned identities](../model-licenses/sam2.1-hiera-tiny-provenance.md).
The registry tier is `fetched`, not `bundled`; staged release-weight gates remain
unchanged. Optional absence does not prevent base installation or startup.
