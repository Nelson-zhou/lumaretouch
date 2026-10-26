# Existing pick review: evidence repair v3 — SOURCE ONLY / UNRUN

Date: 2026-10-25. Requirement: `workflow:230984` (AI挑图), original `LNX-PICK-001`,
frozen acceptance `PICK-001`. This is not `workflow:230903` (cloud client delivery).
Existing `picks.py` / `server.cmd_pick` / App filmstrip already supported local
similarity, proxy detail, brightness endpoints, FaceMesh eyelid clues and manual
flags. No missing whole module was invented. No new model, package, queue or
history ledger is introduced; no file deletion, auto-rejection or source editing.

## Actual repair

* Old `dhash64` scaled to long-edge 9 while retaining aspect ratio; output was not
  9 columns × 8 rows (a square could produce 72 comparisons). The fixed-grid
  area resampler now yields precisely 64 comparisons for all aspect ratios.
  A 1e-9 comparison tolerance suppresses floating point constant-field noise.
* Algorithm v3 changes its fingerprint. Reuse requires matching fingerprint,
  measurement algorithm, decoder-budget parameter, sensitivity settings,
  configured model directory and source stat tuple `(dev, ino, size, mtime_ns,
  ctime_ns)`. Stat is a best-effort local change fence, not a file-content digest
  or an atomic filesystem snapshot. Backend/model changes in-place still require
  explicit force rerun; this patch does not claim model weight hashing.
* Target paths are captured when indices are resolved, not looked up anew on
  each worker iteration. Removed/changed sources are excluded before grouping.
  Cached compatible members get recomputed group badges as well as new members;
  a final whole-group source fence clears all badges if a member changed during
  publication. Each valid-contrast measurement contributes once to the median (not twice for
  fresh rows). Raw numeric precision is retained across cache reuse.
* UI exposes actual original/decoded dimensions, metric edge, complete notes,
  and eye-unavailable state. Pixel clues explicitly concern decoded previews and
  the long-edge-160 derivative. RAW embedded previews remain identified.
  Proxy brightness endpoints do not prove sensor clipping. Rank no longer says
  best photo or suggests keep; it only orders proxy readings for manual review.
  Existing `blur`/`underexposed` wire keys remain for compatibility but their
  displayed labels/reasons are proxy-only. No flags/ratings are auto-written.

## Primary research / license decision

* darktable's official [import/review workflow](https://darktable-org.github.io/dtdocs/en/overview/workflow/import-review/)
  and [star ratings](https://docs.darktable.org/usermanual/development/en/lighttable/digital-asset-management/star-color/)
  ground the explicit human review and reversible ratings approach. No darktable
  code was copied or linked.
* [ImageHash upstream](https://github.com/JohannesBuchner/imagehash/blob/master/imagehash/__init__.py)
  uses fixed-size horizontal dHash; its [BSD-2-Clause license](https://github.com/JohannesBuchner/imagehash/blob/master/LICENSE)
  was inspected. No code copied or dependency added: this patch uses the existing
  NumPy owner and an independently implemented fractional-area grid. It does not
  claim byte-equivalence to Pillow/ImageHash's resampler or hash bit order.
* [OpenCV Laplace tutorial](https://docs.opencv.org/3.3.0/d5/db5/tutorial_laplace_operator.html)
  describes image derivatives, not a universal perceptual focus classifier. No
  OpenCV code/runtime added; the existing NumPy derivative remains in place.
* [MediaPipe face landmarker](https://developers.google.cn/edge/mediapipe/solutions/vision/face_landmarker)
  and [official blendshape model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf)
  describe per-image landmarks/expressions, not identity recognition. Existing
  FaceMesh owner/license is reused; no new model is installed or inferred here.

## Not claimed / next authorized validation

No build, tests, typecheck, application startup, inference, install or real-image
measurement was executed. Only source reading, editing and Python AST parsing.
`test_pick_evidence_v3_unrun.py` is authored, **not run**. Old v2 golden hashes,
calibration and historical ADR benchmark numbers are not v3 acceptance evidence.
New dHash sensitivity thresholds require real-image recalibration. Real photos,
eye-closure accuracy, false positives, repeatability and speed remain UNRUN.

Original-resolution/face-region focus metric is not added: existing picker decode
is deliberately budgeted and may use camera previews; treating it as source
quality would be false. Full-source capture and suitable focus calibration are a
separate bounded task, not silently replaced by another preview metric.
No scene/aesthetic classifier, front-face preference, selected-count optimization,
laugh/large-group exemption, person identity or cross-photo recognition is claimed.
Concurrent external source writes remain a best-effort stat fence; no original
or mark mutation is authorized by a suggestion. Same-path virtual copies share
source-level clues, not independent graph-output quality judgments.

Authored validation plan: fixed 64 bits on square/portrait/panorama/thin images;
flat fields; cache version/scale/sensitivity/model-directory/file replacement;
cache precision; no `keep`/auto-delete; unavailable eyes; source changes between
capture/group/publish; source reorder/removal; partial rerun updates all group
members; stop/retry; existing manual flags remain untouched; inspect original at
100% before deciding. Tests/runtime approval belongs to the later validator.
