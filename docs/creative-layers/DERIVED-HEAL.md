# M14 reviewed deterministic healing

Status: source implementation only. Baseline
`4965dbf60233e7da9c8274b15a543817b7cefeeb`. Fixtures are authored, UNRUN. No
application/model execution, imports, tests, build or typecheck was performed.

## Requirement and honest operator boundary

Handbook manual-text lines 630–633 and
`LNX-REF-PC-32482-C-7fd32754e9` distinguish spot healing from source-patch and
clone. This slice connects a donor-free reviewed brush to the existing
multiscale normalized-convolution fill and anisotropic diffusion solver.
It is deterministic, not generative AI or LaMa. Complex large repairs still
require visual evaluation and may need manual refinement. The patch and clone
operators remain separate. M14/history tracing remains
`LNX-REF-WF-127932-a9c143a25d` / `LNX-REF-WF-127932-c7783ea5fb`.

## Real user and source path

The heal UI freezes the actual repair-input frame (immutable source plus preceding
repairs), waits for its presentation acknowledgement, and collects normalized
points, brush diameter, hardness and opacity. Pixels in the displayed capture
are only review imagery, never the persisted repair definition. Crop/rotation
and padding are validated through the exact captured inverse geometry.

The existing registered `source_patch` native IPC has a separate exact
`kind=heal_vector` variant. Native validation checks the new
`heal_vector_protocol` capability before redeeming the capture lease. It accepts
no original pathname, RGB pixels, source binding or caller-generated revision.
The engine receives the redeemed epoch/document/capture proof through the same
ordered edit queue. Existing patch calls retain their polygon/offset variant.
No new main.rs command or external executor was introduced.

The controller validates exact envelopes, copies the immutable source/stack/
pixel proof, and commits through the existing atomic repair and history owner.
A lost reply queries only the original request; it does not resubmit the stroke.
A zero-opacity operation is no-change. Source switches, pointer loss, blur and
cancelled unsubmitted gestures cannot apply a stale stroke. The UI clearly
separates this brush from clone sampling and generative repair.

## Durable vector and full-resolution contract

New `RepairOp.kind=heal_vector` owns exact `heal-vector-v1` parameters:
normalized source-space points and ellipse axes, hardness/opacity, captured
reference grid and the complete existing solver parameters. The reference grid
makes the fixed context padding's scale explicit. Full replay scales that
padding rather than treating proxy pixels as full-resolution pixels; grow is
dimensionless. Smooth/refine counts and kappa retain the existing defaults.

Coverage is float-rasterized from vectors independently at proxy and full output
resolution. The retained uint8 coverage is diagnostic/history metadata, not the
export definition. The same ordered replay and source/active/redo validation
introduced in DERIVED-REPAIRS apply to this family. Legacy unbound RLE heal remains
original-only and is not allowed to masquerade as a source-owned derived recipe.

Capture and execution both validate the expanded solver crop (maximum 16 MP) and
current memory estimate: full output plus local masks, pyramid/diffusion buffers
and transfers. Known infeasible full-size edits refuse before proxy commitment.
Context is not silently shrunk, resampled down or clipped to fit. Memory changes
can still cause a later explicit refusal. Ordinary-image performance and budget
acceptance remain unmeasured.

Canonical export preserves verified float32/divisor1 derived input and original
RGB8/RGB16 branches, then verifies actual replay output before portrait/body
consumers. Undo/redo, project/recovery/package and fresh-current creative output
keep the same source-owned records and existing history owner. No rendered
bitmap is embedded in each history frame.

## Integration map

UI: healBrush workflow/panel/overlay -> App-scoped capture coordination -> Viewer
reviewed frame -> normalized gesture. Existing ordinary heal launches route to
this reviewed path, not the unfenced RLE submission.
Native: source_patch_api exact variant -> existing redeemed capture/epoch queue.
Engine: source_patch_capture -> heal_vector_geometry -> source_patch_controller.
Persistence: repair_record -> creative_derived_repairs -> existing project/history.
Replay: repair_replay -> ops/heal_vector -> existing deterministic inpaint solver.
Export: prior canonical repair float proof/output proof and people consumers.

## Remaining boundaries and verification

Generic legacy `inpaint` RLE commands remain blocked on derived sources; the new
reviewed vector route closes the user-facing deterministic heal path instead.
This is not approval of legacy per-repair undo/redo transport; the UI uses unified
document history. Global recovery still depends on unadapted smoothing/fabric/
background operators. Shared transfer still needs target-owned source, analysis
and identity review. Alpha/HDR photo return remains refused, never silently
flattened or clipped. M14 and the 32 AI functions are not complete.

UNRUN fixtures cover exact IPC variants and capability fences, presentation,
uncertain receipt handling, source/crop changes, lost pointer state, normalized
replay, scaled context, memory refusal, no-op identity, source-bound active/redo
persistence and canonical float input. Only static source/AST/JSON/whitespace/hash
checks are completed. Local build, interaction, quality, precision, latency and
preview/export parity remain required acceptance work.

[GIMP's healing documentation](https://docs.gimp.org/3.0/en/gimp-tool-heal.html)
distinguishes destination-aware healing from direct cloning. Our operator is the
existing internal deterministic solver, not a copied GIMP algorithm or claimed
quality equivalent. No third-party code/model was downloaded or copied; existing
licence notices remain unchanged.
