# Dedicated eye-bag v2 effect recovery

AUTHORED / UNRUN. This closes a source workflow seam, not another correction
algorithm, automatic anatomical segmentation or photographic acceptance.
Requirement `LNX-REF-PC-32464-C-e5fac5fdcf` remains partial.

## Contribution, not original-photo mixing

The existing `eye_bag_preserve` LocalEffect carries a distinct source-frame delta.
The existing per-face recovery compositor multiplies only that delta by
`1 - recovery_weight` before the common geometry sampler. Weight one removes
this operation's contribution at that source position; weight zero leaves it
unchanged. Other portrait contributions, color processing and later geometry
remain enabled. This does not promise that a final pixel equals the untouched
original photo, nor remove legacy eye-detail or unrelated dark-circle effects.

The recovery mask is a separate immutable vector record with its own target,
source digest, exact FaceRef, measured landmark digest and source dimensions.
It is not the visible-ridge preservation mask, and is never copied from another
face or image. Existing source-sized rasterization and one-pass geometry apply;
no proxy bitmap is promoted to a full-resolution mask. Existing uint8 recovery
coverage precision is retained rather than silently claiming float mask fidelity.

## Review and publication

The new target uses actual complete source-resolution canonical before/after
renders, followed by bounded RGB8 display reduction. Other recovery targets keep
their prior proxy review contract. Full-source rendering does not turn the display
reduction into a native-pixel inspection view or an HDR/alpha pipeline.

Brush input remains in the established verified source-capture workspace with
its inverse-geometry coordinate mapping. The separate native eye crop editor
continues to edit ridge preservation; it is not substituted for this capture.
The new recovery target requires an explicit confirmation after the exact images
have loaded and been acknowledged. A viewed-only comparison cannot commit.

Source, repair stack, graph, immutable support and current document ownership
must still match when acknowledging and preparing the transaction. Shared-source
aliases require the separate complete affected-set route in `RECOVERY-ALIAS.md`;
the legacy single-photo route does not authorize them. Dormant/unavailable-input
restrictions remain. The canonical
people owner publishes the vector reference in the ordinary history; old asset
bytes remain for undo/project replay. Existing original request receipts and
unknown-write query/reload fences are unchanged; cancellation/reconciliation is
not effect recovery and cannot authorize this mutation.

## Primary practice and licensing

[GIMP's layer-effect UI specification](https://developer.gimp.org/core/specifications/layer-effects-ui/)
describes an effect-specific grayscale mask controlling only that effect's
application. It is a design reference, not proof of this implementation's
correctness or of identical pixel semantics. The developer document is marked
CC BY-SA 4.0. No text, implementation or assets were copied; this slice reuses
this repository's existing recovery compositor and pinned correction solver.
No new model, weights or third-party source was downloaded or installed.

## Remaining limits

- Manual ridge evidence is not automatic anatomical detection.
- The recovery painting locator remains a bounded capture, not native eye-crop
  editing; full-source comparison is reduced for display.
- Existing full-source memory/codec and opaque SDR admission limits apply.
- Ending this recovery workspace discards its unpublished review authority; it
  does not claim to interrupt an in-flight full render. The separate read-job
  cancellation protocol does not cover generic recovery preview commands.
- Recovery-vector preset/batch/cohort transfer across independent sources is not
  enabled. Shared-source aliases have a distinct complete-image review and scoped
  history route, not donor-vector transfer or generic permission to edit siblings.
- Numerical, photographic, UI, native, export, history and restart acceptance
  are all UNRUN. No tests, build, typecheck, product imports or inference ran.
