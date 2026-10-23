# Original-shadow scalar transfer: UNRUN UI checks

Source-only fixtures are authored in transferModel.unrun.test.ts,
transferBatch.unrun.test.ts and transferPreset.unrun.test.ts. No product imports,
Node execution, typecheck, browser interaction or photo evaluation was run.

- Batch: every eligible target loads both exact hashed PNGs and explicitly
  confirms its own pair. Missing/reordered acknowledgments, target identity or
  source mismatch, missing dependency key and changed blend must block commit.
- Preset: direct apply without frozen target review must refuse. Changed photo,
  selected preset, token or context must invalidate the old review.
- Review zero strength and disabling too. Never transfer lit-floor samples,
  subject support, retention masks, background assets or AI claims.
- Whole-ID and spill scalar combination is refused. At most eight reviewed
  targets, 256-pixel edge and 150000-byte PNG per image remain bounded.
- Verify closing/reopening the review, browser-image failure, stale payload,
  document switching, read timeout and uncertain mutation delivery. No blind
  resend, no cached image falsely declared seen.
- Verify native shadowReviewAck transport and batch hook second-argument
  forwarding, independent of spill acknowledgments.
- Uniform-floor method, dark/reflective/textured floor ambiguity, source mask
  precision and wider alpha/HDR limitations still apply. A thumbnail review
  is not full-resolution numerical or photographic acceptance.
