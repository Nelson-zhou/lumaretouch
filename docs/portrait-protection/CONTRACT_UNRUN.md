# Bounded P0 portrait protection — authored, unrun

This work implements a bounded deterministic pixel operation, not a learned
blemish recognizer or validated identity-preservation model. It does not close
L6/M8 acceptance. No test, build, typecheck, product import, inference, install,
package download or photographic quality review was run.

## State / scope

`_portrait_protection` is a strict `bounded-small-outlier-v1` recipe. Enabled and
strength are independent of legacy skin smoothing. Strength 0 / disabled bypass
blemish correction exactly. Identity protection defaults on. Automatic-mask
analysis and diagnostic overlay default off; feather is integer source pixels
0..256, applied inward only. Zero is a hard support boundary. Normalized explicit
protected rectangles always veto processing, even if heuristic identity
protection is switched off. Rectangles apply in original source coordinates,
not cropped/flipped/warped canvas coordinates.

Only the current original photo with exactly one real MediaPipe face may first
capture evidence. No largest-face selection, synthetic/template substitute,
merged body-skin substitute, generative repair, or automatic new inference occurs.
Existing analysis workflow must first populate actual face_skin/landmarks/model
digests. A frozen same-source observation can replay after cache clearing or
reopen, independently of the live precompute cache. The stored model hashes and
algorithm version are preserved; the masks are a bounded resampled observation,
not newly inferred full-resolution semantics.

## Actual consumers

The existing skin smoothing stage is gated by the automatic protection support
when analysis is on. The independent blemish stage applies only small admitted
outlier components inside face-skin/anatomy, with annular same-face source donors,
per-channel correction <= .12 times strength, component-size/foreign-boundary
refusal and default dark-pigment veto. Explicit protected boxes win. There is no
blanket blur. Overlay is diagnostic proxy-only; export never installs it. Original
view bypasses the pipeline as before. Full-resolution export prepares one field
from actual repaired source then slices it for tiles; RGB16 stays float32, never
an RGB8 intermediate. Proxy preview may differ from full-source accurate preview
because sampling changes the observations; quality parity is UNRUN.

The field is recomputed rather than cached, avoiding stale source/repair/parameter
reuse. A conservative dynamic budget is checked before full-source allocation.
History, document state, project encode/decode, export snapshot inventory, native16
neutral classification and full export consume the same recipe. Exact source
hash + dimensions + captured file stamp reject cross-source replay.

## Limits and intentionally open scope

- Dark marks are only a conservative ambiguity veto. Scars, light tattoos, red
  birthmarks, makeup, acne and natural pigmentation cannot be reliably
  distinguished by this algorithm. Human before/after review is required.
- User-protected regions are rectangles, not claimed brush/anatomy recognition.
- Portrait preset/batch transfer is explicitly refused: old shared smoothing
  strength is no longer falsely advertised as independent blemish processing.
  Source-bound evidence cannot be transplanted to another photo. Thus preset /
  batch original contract coverage remains partial.
- New P0 activation on derived composite sources is refused rather than reusing
  original-photo anatomy. Creative capture remains fail-closed for active effects.
- Automatic mask analysis here controls a real protection mask; it does not run a
  new model or create a new semantic segmentation on enabling.
- Unknown transaction outcome requires readback/reload, never blind command replay.
- All original human/image regression, neutral thresholds, save/reopen behavior,
  tile/native16 parity, cancellation latency and real quality remain UNRUN.

## Review hardening (source-only)

The diagnostic tint is composed only on a copied RGBA image at final shared-memory
delivery, never on canonical render tensors, scope taps, analysis inputs or clean
frame buffers. Coverage follows source deformation, manual liquify, optical green
control geometry (not photometric gains), crop/rotation and final canvas reflection.
Original comparison does not receive tint.

Current loaded-document identity must be nonempty. Frozen analysis retains the
canonical face instance when available; replay checks its enabled state and exact
landmark digest against the current document graph. Legacy disabled/added manual
face ledger ambiguity refuses this P0 operation instead of matching nearby boxes.
Disabling an owner suspends retained processing (visible reason) while export
refuses; it does not silently reactivate a false positive. Explicit neutral reset
discards frozen evidence, allowing a later deliberate activation to bind newly
reviewed analysis. Receipt readback exits dispatch before preview/capture invalidation.
