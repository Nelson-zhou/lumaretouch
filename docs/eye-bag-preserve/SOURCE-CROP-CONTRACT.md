# Native-spatial source eye crops

AUTHORED / UNRUN. This closes a source-inspection usability gap of
`LNX-REF-PC-32464-C-e5fac5fdcf`; it is not another algorithm or complete automatic
ridge-preservation acceptance. The original solver and the v2 Rust protection
core are unchanged.

## Coordinates and precision

A crop is a rectangular slice of the actual full-resolution, orientation-normalized
working source, after committed repair replay but before portrait effects and
geometry. A rectangle `[x, y, width, height]` uses integer source pixel edges.
Its PNG dimensions equal its rectangle dimensions, with no resize or proxy
promotion. A screen point at crop fractions `(u, v)` becomes whole-source
`((x + u*width)/source_width, (y + v*height)/source_height)`. Brush radii and
persisted vectors remain in the existing whole-source domain. Crop coordinates
never become a separate mask or asset owner.

The original decoder retains genuine RGB16/ICC16 where supported, and the
immutable derived source retains its existing float boundary. The crop PNG is
explicitly display-only sRGB RGB8. Native spatial sampling is not a promise of
lossless 16-bit screen inspection, HDR, alpha support or export equality.
100% means one image pixel per CSS pixel; device/browser scaling remains
separate. Enlargement above 100% does not create image detail.

## Ownership and transport

`eye_bag_reference` retains its whole-frame locator and adds bounded crop
metadata. A separate read-only `eye_bag_source_image` page retrieves one eye
under the exact reference token, image hash and source/repair/analysis snapshot.
The engine rechecks that snapshot, and the native/UI layers check the page's
shape and bytes before painting. Each painted eye must have its own loaded
crop. Retained source vectors do not count as having inspected the current crop.

Paging avoids embedding two full crop PNGs in the existing 8 MiB receipt.
Each eye is bounded to 2048 pixels per edge; both together to 4,000,000 pixels.
Each PNG is bounded to 4 MiB. An oversized source/crop or unavailable actual
source refuses explicitly instead of resizing or borrowing a thumbnail.
Original decode uses its existing separate admission. Repair replay maps one
operation weight at a time and admits 128 MiB fixed plus 128 bytes per full-frame
pixel and operation-local scratch: 384 bytes per expanded solver ROI for healing
and source patches, or 8 bytes per clone ROI with bounded tile scratch in the
fixed reserve. A 24 MP base is 3,206,217,728 bytes before local ROI work, so a small
repair is not categorically excluded by the existing 4 GB maximum. Available
memory can still lower admission; these are static estimates, not measured RSS
or a promise that arbitrary 24 MP stacks fit. Solver order and context are not
reduced to meet a budget.

The existing whole mixed-portrait before/after and support-image acknowledgment
still governs publication. The support overlay retains its unrepaired analysis
source locator background; its geometry is authoritative, not repaired photometry.
Source crops do not replace that review, create a
second history owner or permit blind retries of uncertain confirmations.

## Primary implementation references

- [Pillow Image API](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.crop)
  defines rectangular crop edges. This implementation uses actual array slices,
  not a resampling operation. Documentation consulted; no code copied.
- [MDN Canvas transform](https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/transform)
  specifies multiplication of the current affine transform. The editor composes
  source scaling and crop translation explicitly. Documentation consulted; no
  code copied.
- Existing decode/ICC, immutable creative-source and repair replay contracts are
  reused, without new model weights or third-party code. Existing licenses and
  notices remain applicable.

## Unaccepted and remaining

Automatic anatomical ridge detection, active preset/batch/cohort transfer,
shared-source affected-set review and arbitrary recovery painting remain
separate gaps. Crop display does not establish anatomy or visibility by itself.
The crop helper exposes cancellation checkpoints, but the current reference
command does not wire a user cancellation callback to them. Full-frame decode,
ICC, individual repair kernels and PNG encoding retain their non-interruptible
call boundaries. No end-to-end user cancellation or measured memory/performance
claim is made. All actual decode, native, UI, numerical, history, export and photograph
acceptance is UNRUN.
