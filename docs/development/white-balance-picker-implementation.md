# White-balance neutral eyedropper integration

Implementation is connected, not a claim of runtime or photographic acceptance.
This change was edited and statically compared only: no product launch, tests,
build, type check, or GPU run was performed. Earlier foundation CI results are
historical evidence for those revisions, not verification of this integration.

## Reuse and source comparison

Scope maps to the packaged specification `ui/src/spec/refine.json`, feature
`PC-32455`, subcontrol `白平衡/白平衡吸管` (alongside `白平衡/色温` and
`白平衡/色调`). The frozen neutral-point interaction implements that subcontrol,
not adjacent AI/automatic WB, multi-photo matching, levels/curves/HSL eyedroppers.
The source lists no numeric picker policy, so the bounded-region thresholds are
explicit project decisions, not fabricated handbook requirements. Independent
Word-original limitations remain as recorded in the acceptance source inventory.
The UI uses a labelled frozen input view rather than the generic colour readout.
The development package's source-reuse requirement is met through these concrete
existing owners, not another detached sampler or new general capture framework:

- `color_action_sampling.py`: existing pre-WB stage, linear decode before crop /
  rotation / fixed-proxy projection, coverage and source-risk projection, warm
  prefix and resource admission. Preview uses re-encoded projected linear input;
  picking obtains 1–121 device-sliced linear samples under that same recipe.
- `core/white_balance/picker.rs` and `white_balance_pick_math.py`: unchanged bounded
  Rust scalar authority, policy `proxy-linear-neutral-v1`. No Python fallback,
  display-RGB inverse or UI-authored gain is introduced.
- `source_patch_capture.py`, `source_patch_capture_host.rs`, `source_patch_api.rs`:
  source comparison for private LRCP publication, epoch/document/capture/ticket/
  generation binding, copy lease, delivered-then-presented state, and one-shot
  native redemption. Writer and private reader gain only a fixed WB purpose;
  source-patch defaults and packet layout remain unchanged.
- `white_balance_controller.py`, `white_balance_recipe.py`, existing exposure
  transaction and history: selected gains replace `picked_gains`; no independent
  save/export state. Manual temperature/tint, selected algorithm, reference white,
  exposure and tone are preserved. Clear neutral correction restores only picked
  gains; the existing full WB reset still clears manual shifts as before.
- Existing source-patch capture UI and WB terminal receipt workflow inform the
  frozen preview, cancellation and original-request-only result query. Queue
  acceptance is never treated as an edit result.

Official/community comparisons already recorded in
`white-balance-picker-foundation.md` remain the mathematical/design references:

- darktable global picker versus module-space picker:
  https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/darkroom/global-color-picker/
- darktable white-balance coefficients and their distinction from Kelvin/tint:
  https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/white-balance/
- GIMP explicit sampling source and averaging:
  https://docs.gimp.org/3.0/en/gimp-tool-levels.html

Those references motivate explicit source space and coefficient semantics. Our
Y-preserving replacement, clipping rejection and frame-binding protocol are the
project's own policy, not a claim of copying darktable's coefficients or UX.

## Ownership and failure contract

The engine captures only after its current warm preview prerequisites and memory
admission. The labelled view is immutable in a private capture directory, never
the mutable output SHM. A presented acknowledgment requires successful native
copy delivery. The native pick receives only the captured ticket and bounded
region; producer generation and runtime recipe identity come from its own proof.
The engine rechecks load identity, runtime recipe version, projection and presented
eligibility and computes Rust gains before advancing the mutation fence. Edits,
load/history changes, inspection and engine termination invalidate captures.

The existing exposure transaction applies the resulting options, renders and
rolls back on failure; dispatcher history completes before the terminal WB result.
Pick receipts carry document/capture/ticket identity and before/after/history
proof, with native preservation checks. Unknown results are queried using the
original request ID, never re-submitted. Request deduplication is bounded memory,
not durable exactly-once storage across engine restarts.

The selection must be genuinely neutral, sufficiently bright and unclipped. This
is proxy working-stage saturation detection, not RAW sensor clipping detection.
Late exposure clipping or creative grading can change final output neutrality.
Crop padding, clipped contributions, too-dark samples and excessive gains reject
explicitly; no silent clamp, algorithm switch or manual-control reset occurs.

## Remaining acceptance

Desktop interaction, cancellation races, native/engine restart cases, visual
colour quality on representative portraits and GPU/resource behaviour need
runtime acceptance. No such acceptance is implied by static integration.

## Cross-tool copy overlap bound

WB and source-patch each retain their own single native copy lease. Cancellation
invalidates eligibility but does not release an in-flight reader's buffer budget:
its RAII owner survives the blocking job and awaiting delivery, and drops the
buffer before ending that exact lease. Switching tools can temporarily leave one
old reader and one new reader alive. There is no shared cross-purpose allocator
or assertion that the application has only one capture allocation.

The native packet ceiling is 128 MiB payload plus 128-byte header per purpose,
so the two native readers together are bounded by 256 MiB plus 256 bytes. The
current engine action projection separately caps source proxy pixels at 8 Mi,
which normally makes each RGBA payload at most 32 MiB. These are packet/read
bounds, not whole-application peak memory guarantees: engine projection tensors,
private-file pages, IPC/UI buffers and canvas copies are additional. Existing
per-capture host headroom admission remains conservative planning, not a shared
reservation or measurement of concurrent process memory.
