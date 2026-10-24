# Eye-bag ridge protection UI and native contract

AUTHORED / UNRUN. No imports, tests, product execution, build, typecheck, inference,
download or Git write was performed for this slice. Static reading is not a pass.

- The v2 operation is independent from historical enhance.v1 eye_bags and from
  eye-light support. Existing values stay unchanged unless the user explicitly
  checks replacement and confirms the frozen candidate. No automatic ridge
  segmentation is claimed. Source-bound support is never copied across sources.
- Per-eye pointer strokes use source pixel-edge coordinates and source-pixel
  radius. Erase, undo-one-stroke, clear-eye, 1–32x zoom and actual drag-pan are
  present. A thumbnail zoom cannot restore absent image detail, so the user is
  told to stop when the ridge is not discernible. Canceled capture drops its
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
