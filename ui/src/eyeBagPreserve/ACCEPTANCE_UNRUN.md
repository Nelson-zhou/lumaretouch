# Eye-bag ridge protection UI and native contract

AUTHORED / UNRUN. No imports, tests, product execution, build, typecheck, inference,
download or Git write was performed for this slice. Static reading is not a pass.

- The v2 operation is independent from historical enhance.v1 eye_bags and from
  eye-light support. Existing values stay unchanged unless the user explicitly
  checks replacement and confirms the frozen candidate. No automatic ridge
  segmentation is claimed. Source-bound support is never copied across sources.
- Per-eye pointer strokes use source pixel-edge coordinates and source-pixel
  radius. Erase, undo-one-stroke, clear-eye, 0.25–32x zoom and actual drag-pan are
  present. Painting uses lazily fetched native-spatial eye crops, not the retained
  full-frame locator thumbnail. Each crop is SHA-256 checked, PNG-header checked
  and naturally decoded before its eye can be marked reviewed. 100% means one
  source pixel per CSS pixel, not physical device pixel; RGB8 is display-only,
  not a claim of 16-bit photometric inspection. Zoom never invents detail. Canceled capture drops its
  partial stroke; each pointer gesture remains independent.
- Default feather is 0, opacity is 1. Common canonical box feather semantics
  remain unchanged, with explicit disclosure that full-protection pixels can
  disappear. The dedicated engine admission must reject all-feather/tiny masks.
  Drawing canvas colors are geometric drafts, not authoritative coverage.
- The actual source-grid support raster has its own compact PNG and declared
  canonical/decoded extent. The UI verifies byte hashes and natural dimensions,
  displays cyan full coverage versus amber partial coverage, and requires this
  image plus actual complete mixed-portrait before/after images to load before
  acknowledgment. The ACK binds all three PNG hashes and the frozen review hash.
- Read-only reference/preview/image calls reuse the people mailbox with exact
  eye_bag_request echoes, not capture invalidation or mutation recovery fences.
  Confirmation retains the captured review until receipt validation, even after
  navigation/unmount. Unknown outcomes remain query-only, never auto-replayed.
- Positive previews require explicit visible, unoccluded, person-owned manual
  support. Unreviewed sides do not change. Amount 0 uses the established safe
  people patch and does not require native/image support. It preserves the
  preservation setting and follows existing history/alias guards.

Pending acceptance: native compilation; TS typecheck; all authored fixtures;
real mixed-portrait source painting and source-switch/repair staleness;
full/partial-core exactness at real decode and export resolutions; image decode
failure, duplicate actions, slow/unknown receipts; undo/redo and project reopen;
alias/dormant sibling refusal; legacy replacement and preserve0/1 quality review.

Native-crop acceptance still UNRUN: original PNG16/ICC and derived float inputs,
committed-repair changes, crop-edge corner/center mapping, per-eye lazy paging,
slow/stale reference replies, both-eye visited gating, natural PNG mismatch,
image/hash corruption, zoom/pan and pointer cancellation. Crops use integer
source edges, max 2048 per side and 4,000,000 combined pixels; no resize fallback.
Each paged PNG is at most 4 MiB. Full-source decode and host cache bounds remain
explicit and are not a measured all-resolution/performance guarantee.

## Read cancellation and session recovery (AUTHORED / UNRUN)

- A cancellation request keeps the original read pending until its exact terminal
  receipt. Codecs and an individual solver call may still be running. A known
  completed read is discarded without claiming it stopped early.
- Native retained read-only proof can release a terminal read or an ended/changed
  engine authority; it cannot release confirmation writes, missing ownership or
  an uncertain live write. Confirmation remains query-only.
- Late read/send/refresh callbacks must not revive a released candidate or lock.
- Closing and reopening the panel retains bounded recipe/vector drafts in the
  existing app-lifetime people workflow for the same exact binding. Images,
  tokens and visibility acknowledgments are not retained as authority. Fresh
  source reads and per-eye review are required. Explicit discard clears the slot.
- App/process restart draft persistence is not implemented. A lost native mailbox
  is not permission to infer a confirmation outcome or resend a write.
- Cancellation/recovery and incomplete-draft fixtures are authored only, not run.
