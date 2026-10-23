# Guided black/white fringe repair, source implementation v1

Baseline: `5c8e7019181974b4a30fc9071f1a0f1c850ef913`.
Status: SOURCE IMPLEMENTATION; build, runtime, numerical, photo-quality,
performance, packaging and acceptance checks are all UNRUN.

## Exact handbook scope

Official behavior was checked against the supplied handbook lines 705–710 and
[PixCake's feature guide](https://www.pixcakeai.com/guide/AlCcjw85ql), read
2026-10-23. Requirement prefix `LNX-REF-PC-AlCcjw85ql-C-`:

- `6d78bc490e`: real feature entry from the manual-tools feature row.
- `f4f0ead111`: entering prepares an enabled candidate, without changing saved
  state until reviewed Apply. Old projects/new documents remain disabled.
- `2173a021fd`: strength; 0–100 with initial 50 is this implementation's product
  choice, not an official disclosed numeric default or model compatibility claim.
- `8dbd34ce2a`: additive brush restores eligible processing coverage.
- `c205301c9f`: eraser excludes/attenuates eligible coverage.
- `eb7a67cd87`: explicit Update renders changed coverage/strength, followed by
  actual before/after presentation and a single history-owned Apply.

The official guide also requires presets and batch synchronization. Those copy
enabled/strength intent only and recalculate each target. They deliberately reset
target manual coverage rather than copying another person's image mask. Batch
undo restores the complete previous target coverage and source binding.

## What the operator actually does

The original Rust kernel compares the edited image to a co-registered pre-colour
guide, tests directional profiles at multiple scales and corrects newly introduced
achromatic dark/bright lobes. It retains original center texture, requires a
monotone source edge and tangential corroboration, and bounds the correction.
This is not lens chromatic-aberration correction, matte morphology, foreground
erosion, generic edge smoothing, a neural model or copied proprietary code.

The guide is the actual repaired effective source, following exactly the installed
face/body warp, manual warp, optical sampling coordinates and crop/rotation. It
does not carry smoothing, replacement background or subsequent colour edits. Both
rasters must use the same working encoding and optical interpolation domain.
The full-source float pipeline applies repair after photo detail, before intentional
grain and final monochrome. Delivery resize/sharpen follows the source-sized edit.

Coverage begins eligible over the valid image. Erase removes eligibility; add
restores it. Neither forces a change where the detector has no evidence of a halo.
The visible overlay is eligibility, not a semantic foreground or detected-edge mask.
Strokes address the edited post-optics/pre-crop destination canvas, not anatomical
coordinates. Crop/rotation is inverted at full-source pixel centers; deformation
is not inverted or used to copy source segmentation. Upstream edits invalidate the
open review. Persisted destination coverage stays in that declared coordinate
system and is evaluated against fresh pixels on subsequent renders.

## Honest limitations

- Baked-in halos already present in the guide are not reliably distinguishable
  from real hair/rim light. This guided v1 does NOT establish full official
  photographic feature acceptance or general blind halo restoration.
- New geometry, thin edge structures, saturated/chromatic contamination and
  changed background statistics can produce intentional false negatives. A brush
  does not turn these into guaranteed repairs. Real photographs remain untested.
- Rust supports bounded finite signed/HDR floats without clipping, but the wider
  returned-source retouch pipeline still refuses unsupported alpha/HDR. This is
  not an alpha/HDR end-to-end completion claim. Integer delivery retains its
  existing explicit quantization/output policy.
- Review images are downsampled from the real full-source rendering, not 100%
  candidate inspection. The saved result can use the existing original-size
  inspector and global Undo. No proxy mask is promoted into a full-source mask.
- Native receipts survive a webview remount within the application process.
  Genuine unknown commits remain locked/query-only; no blind retry or invented
  checkpoint recovery. Disk-durable receipt recovery is not implemented here.
- Source caps and memory admission can refuse a job. No throughput or ordinary
  24 MP performance claim is made without the separately authorized local tests.

## Integration map

- `core/fringe_repair`: standalone original Rust cdylib, exact header and UNRUN
  numerical/ABI fixtures. See [kernel contract](KERNEL.md).
- `fringe_repair_state/project/scope`: bounded vector intent, strict optional v23
  project field, disabled legacy defaults, parameter-only transfer and full undo.
- `fringe_repair_geometry/render/native`: full-resolution ellipse replay, guide
  construction, source provenance, bounded Rust tiles and full-frame publication.
- `export.py`, `photo_grain_runtime.py`, `photo_grain_export.py`, `full_quality.py`,
  `inspection_worker.py`: one canonical preview/export/inspection path. Geometry
  and original/derived decode proofs are retained, including RGB16 source handling.
- `fringe_repair_review/controller/host`: engine-owned session baseline, fresh
  complete-session strokes, exact presentation proof and one history transaction.
- Native `fringe_repair_*`: epoch/source/proof validation, audit bootstrap,
  admission generation and original receipt retention. No unrelated undo owner.
- `ui/src/fringeRepair`: actual image/canvas, explicit Update, shown-proof Apply,
  pending-query controls and capped stroke intent. App owns lifecycle, not the
  collapsible tool row. Ctrl/Meta+Shift+M is our Linux/client shortcut choice.
- `packaging/stage-engine.sh`: explicit package-time native compilation and source
  notice inclusion only. It was edited, not executed.

## Primary technique references and licensing

[He, Sun and Tang's guided-filter project](https://people.csail.mit.edu/kaiming/eccv10/index.html)
describes an edge-aware local-linear primitive; it is not claimed as a complete
halo detector. [Farbman et al.'s paper](https://www.microsoft.com/en-us/research/wp-content/uploads/2008/08/Farbman-EPD-small-SG08.pdf)
discusses decomposition-induced ringing and the ambiguity of edge preservation.
These informed the failure analysis, not code reuse or quality certification.
No external source code, model or license-incompatible engine was downloaded or
copied. Existing project license and existing brush-core notices remain applicable.
