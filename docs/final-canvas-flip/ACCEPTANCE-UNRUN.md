# Qoder/local acceptance — NOT RUN

Run only in the separately authorized local test environment. Explicitly build/package
the Rust library first; never use the neutral/missing-native case as evidence that
active reflection works. Preserve all fixture originals and hash them before/after.

## Exact primitives (authored Python + Rust cases)
- Asymmetric odd 11×7 and 5×3 samples; H, V, H+V, neither; singleton axes; twice same
  reflection returns identical bits. u8, u16, f32 ±0/NaN payload/HDR, existing f64 crop.
- Noncontiguous input; output cannot alias source/cache. Neutral object identity
  with unavailable native. Invalid booleans/null/fields; ABI mismatch; memory refusal.

## Complete ordinary vertical slice
- Real asymmetric photo: each actual PC-32478:21/22 button and crop modal control;
  no CSS-only reflection. Noncentral crop, 90° and 17° rotation. Original compare stays
  original and releasing compare restores flip. History H then V gives two steps;
  undo/redo each step, neutral old history and redo after another edit.
- Save/reopen/switch docs and linked copies, active/inactive named versions, both
  history directions; original hash/mtime stable. v23 existing fringe/creative/hair/
  virtual-copy and skin-reference face/body support/history files reopen; malformed old identities still reject. v24 file rejected
  by old v23 binary rather than silently opening neutral. Package roundtrip.
- Missing native, allocation failure, interrupted render and failed rollback: no partial
  recipe/history/dirty publication, explicit reload fence if rollback unknown. Rapid
  H/H/V clicks, stale revision, switch/load/history before queued click; no cross-doc edit.
- Receipt UI: queue ACK alone cannot unlock either crop/spec control. Lost/late result,
  engine restart, panel unmount/remount, mismatched ID/document/revision/desired state,
  duplicate JSON keys and first-terminal retention: pending/unknown remains query-only;
  failed native admission/stale/render/rollback reasons are visible.
  Offline engine, another guarded owner, full/closed queue: fresh request receives
  native `not_sent`, clears only its pending UI and exact recovery fence; same-ID replay
  must never convert a previously queued unknown into not_sent. Transport loss AFTER
  enqueue stays unknown. New engine or later verified project reopen + idle queue
  exposes explicit "abandon old wait"; old outcome remains unknown, no resend, and a
  fresh click works. Failed/synthetic open, old open racing before enqueue, timeout,
  same-engine photo switch and nonidle queue must not unlock. Specifically buffer an
  earlier queued project's open event until after flip enqueue: after that event and
  flip command_done are received, the first idle unknown query must anchor at the
  already-seen open, require ANOTHER verified reset, and never unlock from enqueue-time
  generation. Native mailbox loss after sessionStorage restore reserves the old ID and
  requires its own idle-query/reset proof, not fabricated non-delivery. A same request
  ID already owned by exposure/custom edits must remain pending after flip not_sent;
  the other owner's real terminal must still reach and settle its own fence. Exact same-ID replay
  does not add history; same-ID changed payload rejects. No automatic resend/toggle.
- Recovery: stale/native refusal and proved rollback preserve previous autosave eligibility;
  one applied edit increments committed revision once; exact receipt replay does not.
  Failed rollback or partially advanced fence remains unknown and blocks save/export.
  No unrelated/raw ACK or wrong-event receipt can settle the native recovery fence.

## Pixel routing parity (authored export matrix plus real-source checks)
- RGB8, true PNG16, TIFF16 and supported RAW: final canvas equals exact reflection of
  the same fully processed canvas; integer export uses no extra 8-bit roundtrip.
- Crop+rotation+nonneutral grain, fringe, colour editor/range view, extended tone,
  reference/semantic colour, masks and anatomy. Verify full-source callback replaces
  result before one reflection, never zero/two. Existing processing-domain masks and
  landmarks are unchanged and are not relabelled anatomical left/right.
- 17° geometry with scale 1/2, sharpen off/on, neutral detail and active grading/selective:
  finishing input must be normalized f32 (not f64 or an 8-bit detour); RGB16 stays RGB16.
- Scale 1 and 2/4 and sharpen, writer resize and watermarks: source processing/reflection
  precedes delivery resampling and watermark stays correctly oriented. Nonaligned
  crop at source/delivery scale may explicitly refuse under the existing rounding guard.
- Full-quality ROI on opposite edges after H/V and full candidate review show identical
  reflected areas. `reference_color_engine` gets unflipped processing source evidence.
- Neutral before/after upgrade presentation and candidate hashes match; active flip
  changes final geometry hash; original presentation hash does not change.

## No coordinate misapplication
- While active, try newly opened AND already-open/stale source patch, clone/heal,
  local masks, liquify/protection, recovery, WB, colour/ID/editor pickers, fringe paint,
  ID spill/shadow paint, portrait crop, raw mask/light/face placement and guide moves.
  Backend must refuse with explanation and no edit; UI must not imply valid sampling.
- Existing saved coordinate recipes continue rendering identically in processing
  space then reflect. Closing flip re-enables capture without clearing any recipe.
- Creative capture with active flip must explicitly refuse before bake; neutral capture
  must still pass strict snapshot/spec inventory and prior optimized eligibility.

Record exact source revision, native ABI/build, CPU/GPU backend, source hashes, byte
comparisons, project roundtrip artifacts and UI interruption results. Static parse or
an authored test file is not runtime evidence; all cases above remain UNRUN here.
