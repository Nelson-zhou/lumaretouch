# Skin reference matching UI acceptance: AUTHORED / UNRUN

No tests, typecheck, build, product launch, image inference, browser interaction or photograph acceptance were executed for this change. Model fixtures are authored only; their one-pixel PNG is not evidence of matching quality.

## Required interactive acceptance before release

1. Open an original photograph with at least three verified faces. With no people cursor or with another editing scope selected, load the catalog. Verify the real immutable source, all measured boxes and their numbered labels correspond to the exact source. No face avatar or placeholder may stand in for source pixels.
2. Start with no donor, no targets and blank amount. Explicitly choose donor A and targets B/C; donor cannot also be checked as target. Change donor, targets or amount and verify source-ownership confirmation and candidate acknowledgement reset. Blank, zero, negative, nonfinite and over-100 amounts must be rejected.
3. Verify the source image SHA-256, actual browser dimensions and visible presentation all gate the ownership checkbox. A hidden tab, failed image, stale catalog, foreign source proof or substituted face measurement cannot authorize preview.
4. Generate a preview. Inspect complete mixed before/after photos containing prior adjustments, repairs and current geometry, not isolated skin swatches. Both image sides need byte verification, natural dimensions and visible presentation before the separate manual acknowledgement enables confirm. Merely loading images must never check the box.
5. Change the current source, document revision, graph revision, association revision or face measurement while a read is delayed. The delayed result must be discarded. Change only the people editing cursor without changing fences; the envelope must still target all_people/current asset, never retarget donor selection.
6. Hide the tab after viewing/acknowledging. On return, source ownership and final ACK are unset; missing viewed sides must be revisited. Changing draft values, abandoning the candidate, reload or unmount must never reuse an acknowledgement.
7. Replace saved targets B/C with C only and another donor. The UI must disclose B's removal, render the complete replacement candidate and leave other operation families untouched. The native report must exactly match the captured bank, donor, target set and per-target amounts/support.
8. Interrupt catalog, preview, image, confirm and clear individually. While the owner is uncertain, only query the exact original request; do not issue a new request or mutation. Test known rejection, late successful response, payload release, document navigation, duplicate click and response to an old ID.
9. Confirm and clear must use existing photograph history. Verify undo/redo from the existing owner and reload persist the same match/support relation. No second panel history, transport queue or root command may appear.
10. Clear a saved match while the native extension is unavailable. Protocol availability permits catalog/read and safe clear; the catalog capability gates new preview. Confirm no automatic-brightest reference, body matching, fallback tint or cross-photo alias modification is advertised or applied.

## Authored model coverage

The unrun model fixture covers positive strength, explicit unique target set, source ownership flag, all_people binding without a selected cursor, exact echo and request fences, current report shape, missing/foreign image bytes, visual dimensions, candidate and post-publication revisions, substituted donor/bank/support, native-report ordering independence, released reads and safe clear.

The unrun guard/owner fixture additionally covers missing catalog admission, missing image sides, cursor independence, changed-source fences, read/frame and failed-write smuggling, released-content non-authority, post-write refresh fencing, read-only completion without refresh, malformed original receipt recovery without resending, and late old-document read disposal.
