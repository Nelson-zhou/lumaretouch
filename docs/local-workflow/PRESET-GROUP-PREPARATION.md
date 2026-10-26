# Explicit fresh-original group preparation

Status: **source integration / UNRUN**. No build, typecheck, test, inference,
product runtime, device, photographic-quality or performance acceptance was run.

## User path

Select one to eight fresh originals and a compatible saved scalar preset, then
choose **开始准备所选新原图并整组审核**. This is an explicit analysis action,
not a read-only preflight and not unattended approval. Existing prepared originals
retain their separate read-only review action. The selected targets must have
neutral complete recipes and empty undo/redo. The project must be clean, a distinct
editor photo must be loaded, and all physical source SHA-256 identities must differ.
The count/resource limits are implementation bounds, not throughput measurements.

Preparation uses the serialized engine dispatcher to call the genuine
`load_image` for each exact retained document. Every load establishes a new load ID;
only then is a new `SkinPreparation` created. Its existing explicit MediaPipe skin
analysis, single genuine face validation, retained binding, and document-slice
cancellation remain authoritative. No mask, landmark, source graph, history bank or
old load ID is copied from another photo. Canonical import activation classifies
fresh independent imports; the coordinator does not manufacture graph ownership.

After each success, ordinary `_remember_current` parks that target. After all
preparations, the original editor is loaded through the same canonical path with
the original proxy budget. Its exact recipe, undo/redo, document revision, source,
portrait owner identity and source-local portrait slice/analysis/cursor/target/
landmark evidence must match. Shared graph revisions are not rolled back. Only
after that restoration does the existing group owner freeze and render **all**
candidates against the final shared context. No earlier review proof survives a
later preparation.

## Failure and recovery

- Each selected member gets `prepared`, `failed` or `not_started` in original order.
- The first failure stops later preparation. A known exact current attempt may
  use `SkinPreparation.restore`; previously parked successes stay prepared.
  This is a disclosed partial result, not an atomic rollback of the whole group.
- Known partial + verified original-editor restoration settles the preparation
  boundary but creates no candidate group and applies no preset. The user may
  explicitly select the successful subset for read-only review; nothing is skipped
  or approved automatically.
- Failed canonical load, changed source/owner, recovery taint, unknown analysis,
  failed cancellation or failed editor restoration stays unknown and locked. No
  code clears existing project recovery taint or rewinds fences.
- Each preparation request is claimed before the first load and retained in a
  bounded session-only receipt map (64 entries; no eviction/retry that could
  re-execute analysis). Exact retries return the prior result. Changed-payload ID
  reuse cannot become a no-write success. Restart has no automatic resume.
- Native receipts bind exact target order and preset identity. UI retains the
  original request during expected real-load events and queries that request only
  after timeout/remount. Missing/unknown results do not enable editing or retries.
- A late editor-status event may conservatively discard candidate presentation;
  recovery is a new **read-only** group review, never repeating preparation or
  reusing earlier acceptance.

There is no mid-analysis cancellation endpoint in this synchronous bounded slice.
Closing the subsequent review declines preset application but retains the neutral
preparations; it does not undo successful analyses. Only a failed current attempt
uses the exact existing cancellation owner. A missing preparation result must be
queried, not treated as cancelled.

The preparation boundary has a private, engine-owner-supplied restoration outcome.
A known restored partial advances recovery revision without falsely tainting a
settled project; unknown results retain ordinary taint. JSON fields cannot supply
that private proof. Saving/exporting and actual visual acceptance remain separate.

## Design reference and authored scenarios

The official darktable copy/paste documentation was re-read on 2026-10-25:
https://darktable-org.github.io/dtdocs/en/module-reference/utility-modules/shared/copy-paste/
Its selected-module/group-action pattern and exclusion of unsafe mask copying
inform this bounded interaction; this implementation does not copy its code or
claim comparable automatic processing, quality or performance.

Authored fixtures/scenarios are **UNRUN**: serial load order/new IDs, complete
preparation before freeze, editor-state restoration, known middle-target failure,
partial retention, source/recovery drift, unknown refusal, same-request replay,
changed-payload claim, exact native receipt identities, missing restoration fields,
expected load-event UI transitions, and existing explicit one-group approval.
