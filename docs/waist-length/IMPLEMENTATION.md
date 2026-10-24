# Explicitly marked waist length

Baseline: `4a1bbd3ba830b0da5b27c7d07d61a7d17823cf4d`.
Exact requirement: **LNX-REF-PC-32473-C-5d33f285bb**, 腰部长度.
Operation: `lnx.waist_length.v1`. Status: **PARTIAL, AUTHORED / UNRUN**.
No numerical, binary, UI, photograph or release acceptance is claimed.

## Requirement and primary evidence

The original AI package mapping and frozen `ui/src/spec/refine.json` distinguish
waist length from upper-body length (`f1662d2dec`) and waist width. The official
[mobile body-shaping guide](https://www.pixcakeai.com/guide/125979), retrieved
2026-10-24, separately describes waist length at lines144–146: left shortens,
right lengthens. This corroborates direction only, not numerical calibration or
parity with the desktop product. The exact
[desktop guide](https://www.pixcakeai.com/guide/32473) timed out during retrieval;
that is a research limitation, not a claim that the product lacks the control.

[MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)
provides estimated pose landmarks. Its 33-point layout has shoulder and hip
landmarks, not upper/lower waist endpoints. This implementation therefore never
interpolates those points and calls them measured waist anatomy. Four explicit
source-canvas markers designate visible upper-left/right and lower-left/right
waist endpoints. Left/right here means source-image sides, not inferred anatomical
sides. User review cannot turn an occluded, clothing-hidden or uncertain boundary
into detector evidence. Such cases must be refused or left unapplied.

## Distinct operation and source evidence

The marked upper pair sets the start of the length transition; the lower pair
sets its fixed end. The full upper trunk, head and associated face above the upper
waist translate together. Shoulders and hips only check that the marked waist is
inside an upright observed torso; they do not determine its endpoints. Hips and
pixels below the lower waist stay fixed. Thus the observed waist span changes,
not shoulder-to-hip scaling relabelled as waist length. Arms crossing the marked
waist follow the same local deformation, not a rigid-arm guarantee.

Every manual marker, complete head/hair and arm box, background transition and
visibility/ownership confirmation is operation-specific and bound to the immutable
source, exact BodyRef, pose digest and current explicitly associated own face.
No automatic waist detection, 3D measurement, semantic segmentation, hidden-body
reconstruction or learned cosmetic model is claimed. Misplaced human markers
remain a real risk. The source canvas is a bounded reference thumbnail with full-source coordinate mapping, not a 100% pixel inspection image; manual source-pixel entry is provided, but photographic placement precision is still unverified. Foreign retained faces/bodies and ambiguous ownership refuse.

The original Rust compact-support displacement uses a sufficient analytic
invertibility bound and bounded inverse iteration. These source-level mathematical
arguments do not establish floating-point numerical acceptance. See
[the numerical contract](NUMERICAL-CONTRACT.md). The separate waist ABI and native
availability gate prevent substitution by torso length or another installed
algorithm. Source review and neutral/disable/status reconciliation remain
available when the numerical extension is absent.

## Canonical integration and historical compatibility

The shared body bank, immutable support assets, body/person association graph,
canonical host lock/publication receipts and document history remain the only
owners. New active waist intent selects body order8; neutral/disabled waist intent
preserves all earlier frozen order identities. The common body/face inverse chain
and single source sampler remain authoritative. There is no extra waist image
resampling pass, preview bitmap promoted to full-source output, or new project
format replacing the existing bank.

Original RGB8/RGB16 and supported immutable derived RGB float sources use existing
source transport and export reconstruction. Preview coordinates are conjugated
from the same full-source field rather than redefining waist strength at proxy
resolution. Existing alpha/HDR restrictions remain; no clipping or flattening is
introduced to claim support. The original encoded source remains untouched.

## Scope deliberately still open

- Direct source marking, recipe edits, review, history and canonical rendering are
  authored, not runtime-tested or photographically accepted.
- End-user waist scalar preset/batch transfer is not registered in this slice.
  It requires its own target-local marked waist evidence and actual per-target
  before/after review; a private helper is not that user workflow. The existing
  torso transfer scope is not reused under a waist label.
- Strong perspective, bent/cropped/occluded or uncertain waist anatomy, body
  contacts, inadequate source clearance and ambiguous people remain unsupported.
- Automatic vendor AI equivalence, general body reconstruction, broader HDR/alpha
  pipeline and photographic quality are not complete.

## Licensing and methods

This is original project GPL-3.0-or-later source, reusing the project's own compact
field technique with distinct manual waist semantics. The
[ITK inverse displacement reference](https://docs.itk.org/projects/doxygen/en/latest/classitk_1_1InvertDisplacementFieldImageFilter.html)
and [OpenCV inverse mapping documentation](https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html)
are primary technique references, not copied implementations. Existing MediaPipe
model acquisition/license provenance remains unchanged. No models, code packages
or weights were downloaded, installed or executed for this slice.
