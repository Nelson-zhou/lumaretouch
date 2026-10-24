# 小头 · 完整头发与头部 · UI source-only slice

Requirement: `LNX-REF-PC-32473-C-dc1b0ba40a`. Operation: `lnx.head_size.v1`.

## Authored scope

- An independent whole-head/hair workflow, not a face-size or waist-control rename.
- Positive-only `{version:1, amount:0..1}` intent: zero is neutral, local shrink is capped by the native contract at 8%.
- Actual full-frame canonical-source preview with verified source hash, dimensions, EXIF-normalized orientation and decoded-to-original coordinate mapping.
- Empty initial geometry. A user must select a complete head/hair rectangle, a strictly larger background transition rectangle and an explicit interior pivot. Canvas selection and original-source pixel input are both provided.
- All ten independent confirmations start unchecked and clear after geometry changes. Source/graph/pose/face/association changes clear the draft. Existing geometry can only be restored through an explicit button for this operation's currently reviewed support; confirmations are never restored.
- Actual pose observations 0–12 and engine-owned current face association are required. Every actual head point and the entire factual face rectangle must fit strictly inside the complete head plateau. The outer transition must remain above both actual shoulders.
- Mirrors source-pixel guards: at least 32 pixels per head dimension, at least 16 pixels on every transition side, at least 1 pixel from image boundaries, and actual shoulder width/tilt/depth guards. No inferred hairline, generated centre, exclusion holes, cropping or long-hair omission.
- Independent source review, neutral reset and disable remain available when the protocol exists without the native kernel. Nonzero amounts and enable are gated. The exact native receipt decides whether each command was actually rendered; an unapplied retained review is labeled as such.
- One mutation send per identity, latest-unsent slider coalescing, graph/source fences, original-ID query-only recovery and exact receipt/publication matching. No client-side deformation fallback or separate history owner.
- Parent-owned native/App/body-tools routing; these modules export `HeadSizeWorkspace`, `useHeadSizeWorkflow` and `HeadSizeOwner`.

## Explicitly not completed or claimed

No runtime imports, typecheck, build, test runner, native rendering, inference, model download, photographic review, UI browser acceptance or Git publication were performed for this slice. All `*.unrun.test.ts` files are authored fixtures only.

Long hair reaching shoulders/clothing, contacts, occlusion, cropped heads or insufficient clear transition are refusals, not reasons to silently omit hair. Preset, synchronization and batch migration routes are not exposed by this UI. Local parameter intent alone is not a reviewed target route.

## Deferred acceptance

When execution is explicitly authorized, verify the exact source/native envelope, source image load errors, complete-hair manual review, long-hair/contact refusals, direct pixel input, source/graph drift, lower-core absence, repeated drag coalescing, document switching, lost outer/inner receipts, close/reopen recovery and render publication identity. Then perform real portrait naturalness and Linux app acceptance. Authored fixtures are not evidence those stages passed.
