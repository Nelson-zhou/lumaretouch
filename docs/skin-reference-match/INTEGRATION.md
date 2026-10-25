# Current-photo integration and remaining scope

Source-authored only. Numerical, native ABI, GUI, project reopen, undo/redo,
export, resource usage and photographic acceptance are **UNRUN**.

The following records the preserved face-only v1 integration. The separately
consented body extension is now source-connected through [BODY-INTEGRATION.md](BODY-INTEGRATION.md);
it reuses the same solver without changing old face recipes. Both remain partial
and all runtime acceptance is UNRUN.

## Requirement and independent module

Preserved requirement `control:PC-32465:19` describes automatic brightest-face
reference and face/body colour plus brightness matching. This slice is explicitly
**partial**: select one measured same-photo reference face and separately reviewed
target faces. It does not implement automatic reference ranking, body-instance
matching, learned segmentation, or a full vendor-equivalent AI feature. The lost
original hashed requirement identifier is not invented.

The isolated `lnx.skin_reference_match.v1` Rust core has versioned fit/apply ABI,
Python validation/composition adapters, append-only target-owned relation metadata,
and its own UI review model. Host capability version is independent of optional
native availability, so unavailable-core diagnosis and neutral clear remain
reachable. This is statically registered modular code, not hot plugin loading.
Existing algorithms and their relative ordering are preserved.

## Actual source and rendering

`skin_reference_match_inputs` captures the authenticated immutable effective source
through `portrait_fit_source`, including original PNG16/ICC16/RAW16 decoding.
Original export fit is independent of requested output bit depth. Derived sources
use canonical opaque SDR float32 pixels, never the original-file analysis/pixels.
Frozen export metadata contains source identity and original path/stamp when
applicable, not raw pixel arrays, fitted coefficients or callbacks.

`people_render_runtime` fits at full native source dimensions, then reconstructs
owned application coverage on the actual display/export grid. Measured semantic
support remains measured support, not new full-resolution inference. The original
reference and every foreign face are protected from this operator. The compositor
changes current pixels immediately before the existing body-to-own-face stage,
then shares the unchanged common geometry and subsequent colour pipeline. It does
not restore donor RGB or flatten other edits. Per-target immutable full-source
statistics and source-bound weights are transient, not portable recipe assets.

The source and family budgets remain enforced. Common portrait preparation still
has its existing face/memory limits even where the catalog can describe more
faces. No blanket 24 MP, maximum-target throughput, GPU parity or bounded-latency
claim follows from source review. Decode/solver kernel cancellation is not exposed
as a new UI stop guarantee in this slice. Display images are reduced RGB8 PNGs,
not precision inspection or final output. Alpha/HDR stay explicitly unsupported.

## Review, publication and persistence

The existing people command owner routes five dedicated actions: catalog,
preview, image, confirm and clear. All use an explicit all-people *photo identity*
envelope, independent of the selected editing cursor; relation recipes themselves
are face-owned. Catalog shows actual source pixels and measured face boxes.
Preview builds the complete mixed candidate with privately staged support, not a
single-operation overlay. Exact before/after pages and image ACK bind publication
to document, source, repair, full recipe, analysis and support-bank proofs.

Confirmation atomically replaces the complete prior target set for this operation,
uses the existing graph/support publication and history owner, and preserves
non-portrait state. Native receipt validation and UI frozen review validation are
independent boundaries. No automatic ACK or mutation retry is introduced.
Reopen checks current and historical support closure; unknown outcomes retain the
existing edit fence and original-request query behavior. This family does not
implement a dedicated verified workspace-retirement protocol: an unresolved
write may require full application restart and reopening the last known saved
project; merely reopening a document is not proof that the old write failed.
Clear removes this operation's
scalar intent and pointers while immutable support remains available to history.

Generic preset/batch/cohort and shared-source alias activation remain refused,
not silently copied or treated as reviewed. No donor sample/mask/fit copying.
Reference-face exclusion applies to this operator only; other existing portrait
operations can still change that face. Automatic brightest selection, target
bodies, dedicated transfers, alias review and effect-recovery painting remain
separate unfinished user paths, not accepted functionality or new algorithms.

## Static review findings corrected before freeze

An independent source audit found that a disabled target's unchanged retained box
was incorrectly treated as changed neighboring anatomy, blocking another active
target. The protection signature now excludes neighbor enablement, while active
reference/target validity and target reactivation remain separately checked.
The authored two-target disable fixture remains UNRUN. Explicit confirm/clear
commands now have request-specific history groups so separate reviewed commits
are not intentionally coalesced as a slider gesture. This is source inspection,
not demonstrated undo behavior.
