# Required verification, not yet executed

The owner reserved execution/testing for the local reviewer. These are source
review/acceptance cases, not test results. Use only generated synthetic images or
images for which the user has rights. Do not add photographs to the source tree.

## Integration and honest boundaries

1. Mount the management panel through a memoized native port. An empty catalog
   must show zero user samples and no seeded image cards. Failed first read must
   show an error, not silently replace a real catalog with the empty fixture.
2. Confirm imports and metadata are durable after closing/reopening the app.
   Verify only the user-selected library root is touched and no network traffic
   is required for these controls.
3. Omit the capture callback: capture is disabled and explicitly says no
   original-resolution host renderer exists. There is no screenshot fallback.
4. Open reference mode without a callback: no choice can be applied. With a
   callback, receive stable source/hash/asset identity once per explicit click,
   never a thumbnail URL, never automatic color matching.

## Group and sample management

5. Create/rename groups with Chinese, whitespace, emoji, 120-character boundary,
   empty input and control characters. Invalid names must not submit. The fixed
   ungrouped item cannot be renamed/deleted.
6. Delete a group containing active and archived samples. Confirm both move to
   ungrouped without losing files or changing deleted_at. Cancel the confirmation
   and verify no mutation occurs.
7. Import image files and folders through the native picker. Cancel the picker;
   paths must not be guessed and the catalog must not change. Verify duplicate,
   corrupt, unsupported, too-large, symlink and inaccessible inputs have truthful
   outcomes with original names/indexes, including repeated basenames.
8. Check exactly 1000 and 1001 files per request, folder expansion beyond the cap,
   1999/2000 active items, partial success, storage exhaustion and cancellation
   after several successful files. UI must not silently truncate requests.
9. Search by name/group/format/size; select multiple cards, move them, rename a
   sample, and page across more than 48 cards. Check one selection in reference
   mode, retained selections across pages in management mode, and selection
   clearing when changing group/search/mode.
10. Drag samples and groups in both directions, including adjacent cards. Repeat
    using keyboard-focusable movement buttons. Within the displayed metadata page and search/group filters, hidden
    sample positions must be retained and each complete reorder payload contain
    every active sample ID exactly once. Disabled boundary buttons must not read
    missing neighbors. The fixed group must not move.
11. Remove several samples after confirmation. Their files and shared reference
    bundles remain. Restore without loss; archived samples cannot be selected as
    references. Restoration above capacity is blocked. No permanent-delete,
    empty-trash, or resource-reclaim action is exposed.

## Identity, quality and interruption

12. JPEG/PNG/TIFF/WebP originals must remain byte-for-byte intact. Reference-unsafe
    formats must show the reason and refuse picking rather than reducing bit
    depth. Thumbnails are display-only and failure leaves metadata usable.
13. First reference selection materializes once, receives a small durable receipt,
    then fetches a fresh header and first metadata page at that revision or newer. A second immediate click must not trigger another action.
    Check selected sample ID and full source identity agree with the catalog.
14. Capture must freeze the current original-resolution pipeline output. Compare
    dimensions, float precision, source content hash and state identity, not the
    on-screen preview. Navigate to another document, edit the source, or change
    its file during freeze; reject before persistence. Capture a duplicate active
    or archived result; show its true existing status, not a new-save success.
15. Cancel capture before commit and after commit. Only pre-commit cancellation
    guarantees no new row; post-commit cancellation reports the saved row and
    leaves recoverable trash as the user's explicit next action.
16. Close while loading thumbnails, choosing paths, selecting a reference,
    importing and capturing. Reopen before old calls settle. No old callback may
    choose a reference for the new document or install stale state; reconciliation
    must occur before new writes. Test complete unmount/remount in the host too.
17. Inject known no-apply stale/CAS/busy/validation failures, malformed receipts,
    transport rejection and post-rename/fsync uncertainty. Never retry a write
    automatically or report failure as rollback. Unknown mutations must block
    writes/select until current-state review. Inspect any detached backend task
    before acknowledging. Check lower-revision snapshots cannot overwrite newer
    ones and malformed snapshots cannot blank the catalog.
18. Repeated clicks, quick page/group changes, changed port/root, React StrictMode
    setup/cleanup replay, and current-document change during capture/reference
    selection must not create duplicates or apply old replies.

## Accessibility and layout

19. Complete create/rename/import/select/move/order/remove/restore flows with the
    keyboard. Check focus outlines, labels, radio/checkbox behavior, screen-reader
    live status/error announcements, counts and disabled explanations.
20. Review narrow retouch-panel width, large dialog width, long Unicode names,
    large metadata/hashes, very large outcome lists, reduced-motion settings and
    high zoom. Verify all controls remain visible and no photo is distorted.


## Revision-pinned backend pagination

21. Populate more than 48 rows, including enough trash and long names/notes that a
    whole-catalog response would exceed IPC size. Header must contain no sample
    metadata. Every page is at most 48 rows; no reduced active/trash/catalog limits.
    Traverse all pages and account for every matching ID exactly once. Header
    total/active/trash/group counts must remain independent of current page size.
22. Select rows on pages 1, 2 and 3, go back and forward, then refresh the header.
    All explicitly selected IDs and metadata remain selected. Perform one bulk
    move/remove/restore and verify every intended off-page ID is included. Only
    intentional view/query/mode/root changes, explicit clear or confirmed completed
    mutations clear selection; paging alone never clears it.
23. Mutate the catalog from another client between page reads. Old cursor/revision
    must fail with stale_page; show explicit Refresh rather than stitching old and
    new pages, automatic retry, skipping rows or resetting selection silently.
24. Reuse a cursor with another view, group, search or limit. Reject its canonical
    query mismatch. Inject an incorrect offset, repeated cursor, empty continuing
    page, short nonfinal page or missing end cursor; reject rather than truncate.
25. Mutation, select and capture receipts must not include full snapshots. Verify
    reference materialization returns a canonical reference and capture returns
    reference plus proof/archived status without needing any full metadata list.
26. Reject or cancel the header/page refresh after a successful mutation. Retain
    the truthful completed-write message and per-file outcomes, disable further
    writes pending explicit refresh, and never classify that read failure as a
    rollback or resubmit the mutation. Test post-commit import cancellation: only
    later files stop, completed results remain visible in the receipt.
27. Confirm cursor history contains only cursors and the UI retains only the
    current metadata page plus deliberately selected off-page rows. Thumbnails
    remain separate/lazy for visible cards; browsing must not accumulate an
    unbounded metadata/thumbnail cache.


## Storage-policy disclosure

28. Put unrelated and unindexed NPZ resources in the shared cache through the
    authorized local review setup. Verify the header and panel count the entire
    shared cache separately from owned originals/thumbnails/staging; the displayed
    sum must agree. Do not attribute unrelated shared usage to this library alone.
29. Set a nondefault LRT_SAMPLE_LIBRARY_MAX_BYTES and verify its admission policy
    is displayed without a fixed 16 GiB promise. Existing usage above that policy
    must remain inspectable with an honest warning, not disappear as invalid data.
30. Verify both filesystems' reported free space, including when both paths share
    a filesystem. Do not sum the readings or claim reserved space/global quota.
    Concurrent cache-writer changes and low disk space must retain their real
    admission/failure behavior; the UI never automatically reclaims resources.

31. Close the panel during a pending write whose eventual result is unknown, then
    reopen using the same port. The uncertainty banner must be visible, writes
    remain gated, and acknowledgment stays disabled until a fresh coherent header
    and page have been read. Explicit acknowledgment must not retry the write.


## Native/App integration (not executed)

32. With a capable live engine and no open image, open the empty library from the
    topbar. Import/manage remains available; capture is unavailable. Older engines
    show disabled, explained launchers rather than sending unsupported commands.
33. Browse 48 thumbnails, close, reopen and change pages. Native reservations never
    exceed six active requests, and every consumed terminal receipt is released.
34. Lose enqueue/status/release responses separately. Never resend a request.
    Release failure must preserve successful mutation receipts. Cancellation while
    sending waits for submission acknowledgment and then requests cancellation;
    it must still await the actual terminal outcome.
35. Let a write hit the transport deadline while still pending. Refresh must check
    its retained ID and block acknowledgment until a valid terminal receipt; unavailable remains blocked; after a coherent fresh read, only manual acknowledgment
    unlocks writes. Never infer rollback from a timeout or unavailable mailbox.
36. Choose a sample: verify the App owner stores a frozen stable identity, displays
    its card, and executes neither old same-scene correction nor another color
    operator. Clear it explicitly, move the selected sample to trash, or switch
    document targets and verify selection is cleared. A late result cannot attach
    to a new document even when canonical context is still loading.
37. Confirm App doc.document_id is matched to context.load_id, not canonical
    context.document_id. Confirm status.doc_rev/load/edit-queue changes request canonical context rather
    than being sent as capture revision. Navigate or edit during capture and check
    native cancellation/backend guards plus truthful terminal handling.
38. Check PC-32452 retains preset/LUT controls and uncovered disabled baseline
    leaves. Only manual import/capture duplicates are hidden; opening this panel
    must not advertise the entire AI style-matching family as complete.
39. Check keyboard opening/closing, Escape, initial focus and return focus. Closing
    hides the persistent panel owner; pending work is not discarded or reset.

40. Delay the initial native invocation beyond its acknowledgment timeout, so its
    first status is unavailable. Verify the host cancels this nonterminal unknown
    write and native tombstones the unseen ID before any delayed admission. Lose
    that cancel reply too: refreshing must retry only cancel/status and must not
    unlock review without a confirmed barrier and valid terminal status. A terminal returned by cancel must
    retain the real committed success or known-not-applied failure. The original
    mutation is never resent, and unavailable is never called a rollback.
